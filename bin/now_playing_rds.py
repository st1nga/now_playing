#!/usr/bin/env python
#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Listen to now playing info, if from active studio forward to relevent places
#===========================================================================
# Modifications
#---------------------------------------------------------------------------

import MySQLdb
import redis

import configparser

#import tldextract

import paho.mqtt.client as mqtt
mqtt.Client.connected_flag = False
mqtt.Client.mqtt_result = 0
mqtt.Client.message = ''
mqtt.Client.logger = 0
mqtt.Client.published_flag = False

#import distutils

import uuid

import socket
import logging
import os
import sys
import time
import datetime
import signal

from optparse import OptionParser

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Stops nasty message going to stdout :-) Unrequired prettyfication
#---------------------------------------------------------------------------
def signal_handler(sig, frame):
  print("Exiting due to control-c")
  sys.exit(0)


#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#---------------------------------------------------------------------------
def custom_logger(name, logger_level, config, log_to_screen):
    '''Custom logging module'''

    logger_level = logger_level.upper()

    formatter = logging.Formatter(fmt='%(asctime)s %(name)s:%(process)-5d %(levelname)-8s %(lineno)-4d: %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    handler = logging.FileHandler(config.get("now_playing_rds", "log_file"), mode='a')
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
#connect to mosquitto MQTT
#---------------------------------------------------------------------------
def connect_to_mosquitto(logger, config):

  mosquitto = mqtt.Client(client_id = "now_playing_rds_%s" % uuid.uuid4(), clean_session=True)
  mosquitto.username_pw_set(username = config.get("mqtt", "username"), password = config.get("mqtt", "password"))
  mosquitto.on_connect = on_connect
  mosquitto.on_subscribe = on_subscribe
  mosquitto.on_message = on_message
  mosquitto.on_disconnect = on_disconnect
  mosquitto.on_publish = on_publish


  mosquitto.connect(config.get("mqtt", "host"), int(config.get("mqtt", "port")))
  mosquitto.loop_start()

#+
#Loop until we have connected
#-
  while not mqtt.Client.connected_flag:
    time.sleep(0.1)

  if mosquitto.mqtt_result == 0:
    logger.debug("Connected OK to mosquitto")
  else:
    logger.debug("Bad mosquitto connection: %s"  % rc)

  return mosquitto

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#on_publish callback for mosquitto
# Gets called once we have published (?maybe)
#---------------------------------------------------------------------------
def on_publish(client, userdata, mid):
  mqtt.Client.logger.debug("Message published")
  mqtt.Client.published_flag = True

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# on_connect callback for mosquitto
# Gets called once we have connected
#---------------------------------------------------------------------------
def on_connect(client, userdata, flags, rc):

  mqtt.Client.mqtt_result = rc

  if mqtt.Client.mqtt_result == 0:
    mqtt.Client.connected_flag = True
    mqtt.Client.logger.debug("Connected sucessfully to Mosquitto")
  else:
    mqtt.Client.logger.debug("Bad mosquitto connection: %s"  % rc)

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Called when we sucessfully subscribe to a topic
#---------------------------------------------------------------------------
def on_subscribe(client, userdata, mid, granted_qos):
  mqtt.Client.logger.debug("We have subscribed")

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Called when we receive a message from mqtt
#---------------------------------------------------------------------------
def on_message(client, userdata, message):
  mqtt.Client.logger.debug("Got a message '%s'" % str(message.payload.decode("utf-8")))
  mqtt.Client.message = str(message.payload.decode("utf-8"))

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# on_disconnect
#---------------------------------------------------------------------------
def on_disconnect(client, userdata, rc):
  mqtt.Client.logger.debug("Unexpected disconnection... Exiting")
  sys.exit(1)

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# We have now playing data for the active studio
#---------------------------------------------------------------------------
def now_playing(metadata, logger, config, db, rdis, mosquitto):

  track_expires = 0

  path, track_id, artist, title, album, album_cover, year, track_no, disc_no, bpm, rotation_name, rotation_id, \
    duration_in_seconds, song_type, subcat_id, genre_id, radiodj_ip, track_started = metadata.split('^')

  logger.debug("Of interest is... '%s' by '%s' it is %s seconds long" % (title, artist, duration_in_seconds))

  if int(duration_in_seconds) < int(config.get("now_playing_rds", "skip_short_track_s")):
    logger.debug("Track length is less than 10 seconds... Skipping the update")
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
    except MySQLdb.Error as err:
      logger.error("Error %d: %s" % (err.args[0], err.args[1]))
      logger.error("sql = '%s'" % sql)

    if int(song_type) == 0:
      metadata_to_send = "%s^%s^%s^%s^%s" % (title, artist, duration_in_seconds, track_started, subcat_id)
      track_expires = float(track_started) + int(duration_in_seconds) + int(config.get("now_playing_rds", "skip_short_track_s"))
    else:
#+
#Check if we have priority 0 override
#-
      sql = "select pd.metadata from presenters_diary pd, presenters p where pd.presenter_id = p.presenter_id and p.name = 'override'";
      try:
        c.execute(sql)
      except MySQLdb.Error as err:
        logger.error("Error %d: %s" % (err.args[0], err.args[1]))
        logger.error("sql = '%s'" % sql)
        sys.exit(1)

      if c.rowcount:
        metadata_to_send = c.fetchone()[0]
      else:
#+
#If active studio is sustaining service, then we only want to look at Rotation
#-
        if radiodj_ip == config.get("common", "sustaining_service"):
          sql = "select pd.metadata " \
                "from presenters_diary pd, presenters p, presenters_days pdays " \
               "where pd.presenter_id = p.presenter_id and pd.presenter_diary_id = pdays.presenter_diary_id and " \
                "now() between pd.start and pd.end and pdays.day = dayofweek(current_time()) and p.name = 'Rotation' " \
                "order by priority limit 1"
        else:
          sql = "select pd.metadata " \
                "from presenters_diary pd, presenters p, presenters_days pdays " \
                "where pd.presenter_id = p.presenter_id and pd.presenter_diary_id = pdays.presenter_diary_id and " \
                "now() between pd.start and pd.end and pdays.day = dayofweek(current_time()) " \
                "order by priority limit 1"

        try:
          c.execute(sql)
        except MySQLdb.Error as err:
          logger.error("Error %d: %s" % (err.args[0], err.args[1]))
          logger.error("sql = '%s'" % sql)
          sys.exit(1)

        if not c.rowcount:
          logger.error("No rows returned. sql = '%s'" % sql)
          metadata_to_send = "Coastfm^^^^"
        else:
          metadata_to_send = "%s^^^^" % c.fetchone()[0]
    
#+
#Get the metadata from redis
#-
    redis_metadata = rdis.get("%s.metatdata" % config.get("redis", "prefix"))
    redis_metadata = redis_metadata.decode('UTF-8')

    logger.debug("Got '%s' from redis" % redis_metadata)

    if (metadata_to_send == redis_metadata):
      logger.debug("New metadata is the same as the existing, ignoring")

    else:
#+
#Store the metadata into redis
#-
      rdis.set('coastfm.metatdata', metadata_to_send)
      logger.info("Updating metadata '%s' and it expires at '%s'" % (metadata_to_send, datetime.datetime.utcfromtimestamp(track_expires).strftime("%Y-%m-%d %H:%M:%S")))
      (result, mosquitto_id) = mosquitto.publish('now_playing_rds', metadata_to_send, qos=1, retain=True)
      while not mosquitto.published_flag:
        time.sleep(0.1)

      (result, mosquitto_id) = mosquitto.publish('now_playing_pi_feed', metadata, qos=1, retain=True)

  return track_expires, radiodj_ip

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#main Main MAIN
#---------------------------------------------------------------------------
def main():
  track_finish = 0
  
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
  logger = custom_logger(config.get('now_playing_rds', 'logger_name'), options.logger_level, config, options.log_to_screen)
  mqtt.Client.logger = logger
  logger.info("Hello world!")

#+
#Catch control-c
#-
  signal.signal(signal.SIGINT, signal_handler)

  mosquitto = connect_to_mosquitto(logger, config)

#+
#Subscribe to 'now_playing' topic
#-
  mosquitto.subscribe(("now_playing",1))
  
#+
#Connect to database
#-
  try:
    db = MySQLdb.connect(host = config.get("sql", "host"), user = config.get("sql", "username"), passwd = config.get("sql", "password"), db = config.get("sql", "database"))
  except MySQLdb.Error as err:
    logger.error("Error %d: %s" % (err.args[0], err.args[1]))
    sys.exit(1)

#+
#Connect to redis
#-
  rdis = redis.Redis(host = config.get("redis", "host"), port = config.get("redis", "port"), db = 0)

#+
#Loop forever
#-
  while True:
#+
#Wait for a connection
#-
    if mqtt.Client.message != '':
      track_finish, radiodj_ip = now_playing(mqtt.Client.message, logger, config, db, rdis, mosquitto)
      mqtt.Client.message = ''

      if track_finish != 0:
        logger.debug("metadata expires at %s" % datetime.datetime.utcfromtimestamp(track_finish).strftime("%Y-%m-%d %H:%M:%S"))

    if time.time() > track_finish and track_finish != 0:
      logger.debug("Oops!, we have over run and not got a message")
      now_playing("^^^^^^^^^^^^%s^7^^^%s^" % (config.get("now_playing_rds", "skip_short_track_s"), radiodj_ip), logger, config, db, rdis, mosquitto)
      track_finish = 0

    time.sleep(0.5)

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#---------------------------------------------------------------------------
if __name__ == "__main__":
#    exit()
    main()
