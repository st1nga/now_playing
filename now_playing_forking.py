#!/usr/bin/env python
#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Listen to now playing info, if from active studio forward to relevent places
#===========================================================================
# Modifications
#---------------------------------------------------------------------------

import MySQLdb
import redis

import ConfigParser

import tldextract

import paho.mqtt.client as mqtt
mqtt.Client.connected_flag = False
mqtt.Client.mqtt_result = 0
mqtt.Client.published_flag = False

import uuid

import socket
import logging
import os
import sys
import time
import signal

from optparse import OptionParser

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#---------------------------------------------------------------------------
def signal_handler(sig, frame):
  print "Exiting due to control-c"
  sys.exit(0)


#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#---------------------------------------------------------------------------
def custom_logger(name, logger_level, config):
    '''Custom logging module'''

    logger_level = logger_level.upper()

    formatter = logging.Formatter(fmt='%(asctime)s %(process)-5d %(levelname)-8s %(lineno)-4d: %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    handler = logging.FileHandler(config.get("general", "log_file"), mode='a')
    handler.setFormatter(formatter)
#    screen_handler = logging.StreamHandler(stream=sys.stdout)
#    screen_handler.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.setLevel(logging.getLevelName(logger_level))
    logger.addHandler(handler)
#    logger.addHandler(screen_handler)
    return logger

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# on_connect callback for mosquitto
# Gets called once we have connected
#---------------------------------------------------------------------------
def on_connect(client, userdata, flags, rc):

  client.mqtt_result = rc

  if rc==0:
    client.connected_flag = True

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#on_publish callback for mosquitto
# Gets called once we have published (?maybe)
#---------------------------------------------------------------------------
def on_publish(client, userdata, mid):
  client.published_flag = True

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#publish_to_mosquitto MQTT
#---------------------------------------------------------------------------
def publish_to_mosquitto(metadata_to_send, logger, config):

  mosquitto = mqtt.Client(client_id = "now_playing_%s" % uuid.uuid4(), clean_session=True)
  mosquitto.username_pw_set(username = config.get("mqtt", "username"), password = config.get("mqtt", "password"))
  mosquitto.on_connect = on_connect
  mosquitto.on_publish = on_publish
  mosquitto.connect(config.get("mqtt", "host"), config.get("mqtt", "port"))
  mosquitto.loop_start()

#+
#Loop until we have connected
#-
  while not mosquitto.connected_flag:
    time.sleep(0.1)

  if mosquitto.mqtt_result == 0:
    logger.debug("Connected OK to mosquitto")
  else:
    logger.debug("Bad mosquitto connection: %s"  % rc)

  (result, mosquitto_id) = mosquitto.publish("now_playing", metadata_to_send, qos=1, retain=True)
  logger.debug("mosquitto result = %s" % result)
  while not mosquitto.published_flag:
    time.sleep(0.1)

  logger.debug("Metatdata sent to mosquitto")
  mosquitto.disconnect()

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# We have now playing data for the active studio
#---------------------------------------------------------------------------
def send_now_playing(logger, now_playing_data, db, config):

  type, path, track_id, artist, title, album, album_cover, year, track_no, disc_no, bpm, rotation_name, rotation_id, \
    duration_in_seconds, track_type, subcat_id, genre_id = now_playing_data.split('^')

  logger.debug("Of interest is... '%s' by '%s' it is %s seconds long" % (title, artist, duration_in_seconds))

  if int(duration_in_seconds) < int(config("general", "skip_short_track_s"):
    logger.debug("Track length is less then 10 seconds... Skipping the update")
  else:
    c = db.cursor()
    c1 = db.cursor()

#+
#If at the top of the hour then lets delete the override
#-
    sql = "delete from presenters_diary where presenter_id = 4 and current_time() between concat(hour(now()), ':59:00') and concat(hour(now()), ':59:59')";
    try:
      c1.execute(sql)
      db.commit()
    except MySQLdb.Error, err:
      logger.error("Error %d: %s" % (err.args[0], err.args[1]))
      logger.error("sql = '%s'" % sql)

#+
#Lets get some data from the DB about the track
#-
    sql = "select s.song_type from songs s, song_type st where st.id = s.song_type and s.id = %s" % track_id
    try:
      c.execute(sql)
    except MySQLdb.Error, err:
      logger.error("Error %d: %s" % (err.args[0], err.args[1]))
      logger.error("sql = '%s'" % sql)
      sys.exit(1)
  
    song_type = c.fetchone()[0]

    if song_type == 0:
      metadata_to_send = "%s^%s^%s^%s^%s" % (type, title, artist, duration_in_seconds, song_type)
    else:
      sql = "select metadata from presenters_diary where enabled = 1 and now() between start and end and day in (dayofweek(current_time()), 0) order by priority limit 1"
      try:
        c.execute(sql)
      except MySQLdb.Error, err:
        logger.error("Error %d: %s" % (err.args[0], err.args[1]))
        sys.exit(1)

      if not c.rowcount:
        logger.error("No rows returned. sql = '%s'" % sql)
        metadata_to_send = "Coastfm"
      else:
        metadata_to_send = c.fetchone()[0]
    
#+
#Connect to redis
#-
    r = redis.Redis(host = config.get("redis", "host"), port = config.get("redis", "port"), db = 0)

#+
#Get the metadata from redis
#-
    redis_metadata = r.get("%s.metatdata" % config.get("redis", "prefix"))

    logger.debug("Got '%s' from redis" % redis_metadata)

    if (metadata_to_send == redis_metadata):
      logger.debug("New metadata is the same as the existing, ignoring")
    else:
#+
#Store the metadata into redis
#-
      r.set('coastfm.metatdata', metadata_to_send)

      logger.info("Sending metadata '%s'" % metadata_to_send)
      publish_to_mosquitto(metadata_to_send, logger, config)

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# This is the start of child process.
#---------------------------------------------------------------------------
def now_playing(radiodj_addr, now_playing_socket, radiodj, logger, config):

  (radiodj_ip, radiodj_port) = radiodj_addr

  (radiodj_fqdn, junk, junk) = socket.gethostbyaddr(radiodj_ip)

  logger.debug("Connection from '%s': fqdn = '%s'" % (radiodj_ip, radiodj_fqdn))

  (radiodj_host, radiodj_domain, radiodj_suffix) = tldextract.extract(radiodj_fqdn)

#+
#Read now playing data until no more available
#-
  now_playing_data = ""
  while True:
    recv_data = radiodj.recv(1024)
    if recv_data:
      now_playing_data += recv_data
    else:
      break

#+
#Should have all the data
#-
  logger.debug("We got: %s" % (now_playing_data))

#+
#Connect to DB
#-
  try:
    db = MySQLdb.connect(host = config.get("sql", "host"), user = config.get("sql", "username"), passwd = config.get("sql", "password"), db = config.get("sql", "database"))
  except MySQLdb.Error, err:
    logger.error("Error %d: %s" % (err.args[0], err.args[1]))
    sys.exit(1)

  c = db.cursor()

  sql = "select studio from active_studio order by id desc limit 1"
  try:
    c.execute(sql)
  except MySQLdb.Error, err:
    logger.error("Error %d: %s" % (err.args[0], err.args[1]))
    sys.exit(1)

  active_studio_row = c.fetchone()
  active_studio = active_studio_row[0]

  (radiodj_fqdn, junk, junk) = socket.gethostbyaddr(radiodj_ip)
  (radiodj_host, radiodj_domain, radiodj_suffix) = tldextract.extract(radiodj_fqdn)

  if radiodj_host == active_studio:
    logger.debug("Connection from active studio!!!")
    send_now_playing(logger, now_playing_data, db, config)

  db.close()

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#---------------------------------------------------------------------------
def main():
  
  listen_host = '0.0.0.0'

#+
#Parse the options passed
#-
  parser = OptionParser()
  parser.add_option("", "--logger-level", dest="logger_level",
    help="Log level: ERROR, WARNING, INFO, DEBUG [Default=%default]", default="INFO")

  (options, args) = parser.parse_args()

#+
#Load the config file
#-
  config = ConfigParser.ConfigParser()
  config.read("/etc/now_playing.conf")

#+
#Setup custom logging
#-
  logger = custom_logger('now_playing', options.logger_level, config)
  logger.info("Hello world!")

#+
#Catch control-c
#-
  signal.signal(signal.SIGINT, signal_handler)

#bind to the now_playing port
  now_playing_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  now_playing_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

  try:
    now_playing_socket.bind((listen_host, int(config.get("general", "port"))))
  except socket.error, err:
    logger.error("Error %s:%d: %d: %s" % (listen_host, int(config.get("general", "port")), err.args[0], err.args[1]))
    sys.exit(1)

  now_playing_socket.listen(10)

#+
#Loop forever
#-
  while True:
#+
#Wait for a connection
#-
    radiodj, addr = now_playing_socket.accept()

#+
#We should have a connection
#-
    child_pid = os.fork()
    if child_pid == 0:
      now_playing(addr, now_playing_socket, radiodj, logger, config)
      logger.debug("Exiting Child")
      sys.exit(0)

#+
#Tidy up the defunct children
#-
    os.wait3(os.WNOHANG)

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#---------------------------------------------------------------------------
if __name__ == "__main__":
#    exit()
    main()
