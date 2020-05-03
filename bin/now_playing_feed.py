#!/home/coastfm/.pyenv/versions/3.8.0/bin/python3.8
#!/usr/bin/env python
#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Listen to now playing info, if from active studio forward to relevent places
#===========================================================================
# Modifications
# 02-May-2020 mikep
# Added a select to get some details rather than coming from the boilerplate
#---------------------------------------------------------------------------

import MySQLdb
#import mysql.connector

import configparser

import tldextract
import platform

import paho.mqtt.client as mqtt
mqtt.Client.connected_flag = False
mqtt.Client.mqtt_result = 0
mqtt.Client.published_flag = False

import distutils

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
  print("Exiting due to control-c")
  sys.exit(0)


#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Custom logging module
#---------------------------------------------------------------------------
def custom_logger(name, logger_level, config, log_to_screen):

  logger_level = logger_level.upper()

  formatter = logging.Formatter(fmt='%(asctime)s %(name)s:%(process)-5d %(levelname)-8s %(lineno)-4d: %(message)s',
                                datefmt='%Y-%m-%d %H:%M:%S')
  handler = logging.FileHandler(config.get("now_playing_feed", "log_file"), mode='a')
  handler.setFormatter(formatter)
  logger = logging.getLogger(name)
  logger.setLevel(logging.getLevelName(logger_level))
  logger.addHandler(handler)

  if log_to_screen == True:
    screen_handler = logging.StreamHandler(stream=sys.stdout)
    screen_handler.setFormatter(formatter)
    logger.addHandler(screen_handler)

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
#connect to mosquitto MQTT
#---------------------------------------------------------------------------
def connect_to_mosquitto(logger, config):

  mosquitto = mqtt.Client(client_id = "now_playing_feed%s" % uuid.uuid4(), clean_session=True)
  mosquitto.username_pw_set(username = config.get("mqtt", "username"), password = config.get("mqtt", "password"))
  mosquitto.on_connect = on_connect
  mosquitto.on_publish = on_publish
  mosquitto.connect(config.get("mqtt", "host"), int(config.get("mqtt", "port")))
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

  return mosquitto

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#publish_to_mosquitto MQTT
#---------------------------------------------------------------------------
def publish_to_mosquitto(mosquitto, topic, metadata_to_send, logger, config):

  (result, mosquitto_id) = mosquitto.publish(topic, metadata_to_send, qos=1, retain=True)

  while not mosquitto.published_flag:
    time.sleep(0.1)

  logger.debug("Metadata sent to mosquitto/%s. Result = %s" % (topic, result))

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# We have now playing data for the active studio
#---------------------------------------------------------------------------
def send_now_playing(logger, now_playing_data, db, config, radiodj_ip):

  logger.debug("In send_now_playing")
  c = db.cursor(MySQLdb.cursors.DictCursor)

  path, track_id, artist, title, album, album_cover, year, track_no, disc_no, bpm, rotation_name, rotation_id, \
    duration_in_seconds, song_type, subcat_id, genre_id = now_playing_data.split('^')

  sql = "select path,id,artist,title,album,album_art,year,track_no,disc_no,bpm,duration,song_type from songs where id=%s" % track_id
  logger.debug(sql)
  try:
    c.execute(sql)
  except MySQLdb.Error as err:
    logger.error("Error %d: %s" % (err.args[0], err.args[1]))
    sys.exit(1)

  row = c.fetchone()
  np_data = ("%s^%s^%s^%s^%s^%s^%s^%s^%s^%s^%s^%s^%s^%s^%s^%s" % \
    (row['path'], row['id'], row['artist'], row['title'], row['album'], \
     row['album_art'], row['year'], row['track_no'], row['disc_no'], row['bpm'], \
     rotation_name, rotation_id, row['duration'], row['song_type'], subcat_id, genre_id))
  logger.debug(np_data)
  logger.debug(now_playing_data)

#$path$^$track_id$^$artist$^$title$^$album$^$album_cover$^$year$^$track_no$^$disc_no$^$bpm$^$rotation_name$^$rotation_id$^$durationinSeconds$^$track-type$^$subcat-id$^$genre-id$

  logger.debug("We got: %s" % (now_playing_data))
  now_playing_data = "%s^%s^%s" % (now_playing_data, radiodj_ip, time.time())

  mosquitto = connect_to_mosquitto(logger, config)
  publish_to_mosquitto(mosquitto, 'now_playing', now_playing_data, logger, config)
  publish_to_mosquitto(mosquitto, 'traffic', now_playing_data, logger, config)
  mosquitto.disconnect()

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
      now_playing_data += recv_data.decode('UTF-8')
    else:
      break

  logger.debug("All data received")

#+
#Should have all the data
#Connect to DB
#-
  try:
    db = MySQLdb.connect(host = config.get("sql", "host"), user = config.get("sql", "username"), passwd = config.get("sql", "password"), db = config.get("sql", "database"))
  except MySQLdb.Error as err:
    logger.error("Error %d: %s" % (err.args[0], err.args[1]))
    sys.exit(1)

  c = db.cursor()

  sql = "select studio from active_studio order by id desc limit 1"
  try:
    c.execute(sql)
  except MySQLdb.Error as err:
    logger.error("Error %d: %s" % (err.args[0], err.args[1]))
    sys.exit(1)

  active_studio_row = c.fetchone()
  active_studio = active_studio_row[0]

  (radiodj_fqdn, junk, junk) = socket.gethostbyaddr(radiodj_ip)
  (radiodj_host, radiodj_domain, radiodj_suffix) = tldextract.extract(radiodj_fqdn)

#+
#Is the request coming from the local host or the active studio
#-
  if radiodj_host == active_studio:
    logger.debug("Connection from active studio!!!")
    send_now_playing(logger, now_playing_data.rstrip(), db, config, radiodj_ip)
  else:
    logger.debug("Compare This=%s:Active=%s" % (radiodj_host, active_studio))

  db.close()

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#main Main MAIN
#---------------------------------------------------------------------------
def main():
  
#+
#Parse the options passed
#-
  parser = OptionParser()
  parser.add_option("", "--logger-level", dest="logger_level",
    help="Log level: ERROR, WARNING, INFO, DEBUG [Default=%default]", default="INFO")

  parser.add_option("", "--log-to-screen", action="store_true", dest="log_to_screen",
    help="Output log message to screen [Default=%default]", default=False)

  (options, args) = parser.parse_args()

#+
#Load the config file
#-
  config = configparser.ConfigParser()
  config.read("/etc/now_playing.conf")

#+
#Setup custom logging
#-
  logger = custom_logger(config.get('now_playing_feed', 'logger_name'), options.logger_level, config, options.log_to_screen)
  logger.info("Hello world! Python version = '%s'" % platform.python_version())

#+
#Catch control-c
#-
  signal.signal(signal.SIGINT, signal_handler)

#bind to the now_playing port
  now_playing_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  now_playing_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

  try:
    now_playing_socket.bind((config.get("now_playing_feed", "listen_host"), int(config.get("now_playing_feed", "port"))))
  except socket.error as err:
    logger.error("Error %s:%d: %d: %s" % (config.get("now_playing_feed", "listen_host"), int(config.get("now_playing_feed", "port")), err.args[0], err.args[1]))
    sys.exit(1)

  now_playing_socket.listen(20)

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
