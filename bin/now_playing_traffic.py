#!/usr/bin/env python
#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Listen to the now_playing_traffic mqtt topic for a traffic update.
# Turnon/off RDS TA flag.
# Timeout after 90 seconds
#===========================================================================
# Modifications
#---------------------------------------------------------------------------

import paho.mqtt.client as mqtt
mqtt.Client.connected_flag = False
mqtt.Client.mqtt_result = 0
mqtt.Client.message = ''
mqtt.Client.logger = 0
mqtt.Client.published_flag = False

import time
import uuid
import datetime
import socket

import MySQLdb

import sys
import signal

import ConfigParser
import logging
from optparse import OptionParser

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Stops nasty message going to stdout :-) Unrequired prettyfication
#---------------------------------------------------------------------------
def signal_handler(sig, frame):
  print "Exiting due to control-c"
  sys.exit(0)

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#---------------------------------------------------------------------------
def custom_logger(name, logger_level, config, log_to_screen):
    '''Custom logging module'''

    logger_level = logger_level.upper()

    formatter = logging.Formatter(fmt='%(asctime)s %(name)s:%(process)-5d %(levelname)-8s %(lineno)-4d: %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    handler = logging.FileHandler(config.get("now_playing_traffic", "log_file"), mode='a')
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

  mosquitto = mqtt.Client(client_id = "now_playing_traffic_%s" % uuid.uuid4(), clean_session=True)
  mosquitto.username_pw_set(username = config.get("mqtt", "username"), password = config.get("mqtt", "password"))
  mosquitto.on_connect = on_connect
  mosquitto.on_subscribe = on_subscribe
  mosquitto.on_message = on_message
  mosquitto.on_disconnect = on_disconnect
  mosquitto.on_publish = on_publish
  mosquitto.connect(config.get("mqtt", "host"), config.get("mqtt", "port"))
  mosquitto.loop_start()

#+
#Loop until we have connected
#-
  while not mqtt.Client.connected_flag:
    time.sleep(0.1)

  return mosquitto

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Called when we sucessfully connect to mqtt broker
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
#on_publish callback for mosquitto
# Gets called once we have published (?maybe)
#---------------------------------------------------------------------------
def on_publish(client, userdata, mid):
  mqtt.Client.logger.debug("Message published")
  mqtt.Client.published_flag = True

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
  mqtt.Client.logger.debug("Unexpected disconnection")

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#MAIN Main main
#---------------------------------------------------------------------------
def main():

#+
#Parse the options passed
#-
  parser = OptionParser()
  parser.add_option("", "--logger-level", dest="logger_level",
    help="Log level: ERROR, WARNING, INFO, DEBUG [Default=%default]", default="INFO")

  parser.add_option("", "--config", dest="config_file",
    help="Config file [Default=%default]", default="/etc/now_playing.conf")

  parser.add_option("", "--log-to-screen", action="store_true", dest="log_to_screen",
    help="Output log message to screen [Default=%default]")

  (options, args) = parser.parse_args()

#+
#Load the config file
#-
  config = ConfigParser.ConfigParser()
  config.read(options.config_file)

#+
#Setup custom logging
#-
  logger = custom_logger(config.get('now_playing_traffic', 'logger_name'), options.logger_level, config, options.log_to_screen)
  logger.info("Hello world!")
  mqtt.Client.logger = logger

#+
#Catch control-c
#-
  signal.signal(signal.SIGINT, signal_handler)

#+
#Connect ans subscribe to mosquitto, the MQTT broker
#-
  mosquitto = connect_to_mosquitto(logger, config)
  mosquitto.subscribe(("traffic",1))

#+
#Connect to DB
#-
  try:
    db = MySQLdb.connect(host = config.get("sql", "host"), user = config.get("sql", "username"), passwd = config.get("sql", "password"), db = config.get("sql", "database"))
  except MySQLdb.Error, err:
    logger.error("Error %d: %s" % (err.args[0], err.args[1]))
    sys.exit(1)

  c = db.cursor()

#+
#Get the travel sub-category that we are looking for.
#-
  sql = "select id from subcategory where name = '%s'" % config.get('now_playing_traffic', 'traffic_sub_cat_name')
  try:
    c.execute(sql)
  except MySQLdb.Error, err:
    logger.error("Error %d: %s" % (err.args[0], err.args[1]))
    sys.exit(1)
  
  if c.rowcount:
    traffic_sub_cat_id = c.fetchone()[0]
  else:
    logger.error("Could not find a sub-category with the name of '%s', check config file" % config.get('now_playing_traffic', 'traffic_sub_cat_name'))

  logger.debug("For '%s' we got an ID of '%s'" % (config.get('now_playing_traffic', 'traffic_sub_cat_name'), traffic_sub_cat_id))

#+
#Looking for sub-cat 120 tracks and ignore all others
#loop endlessly checking to see if we have a sub-cat of 120 and then wait for a new message or a 90 second timeout
#-
  traffic_finish = 0
  traffic_flag = True

  while True:
    time.sleep(0.5)

    
    if mqtt.Client.message != '':
      path, track_id, artist, title, album, album_cover, year, track_no, disc_no, bpm, rotation_name, rotation_id, \
        duration_in_seconds, song_type, subcat_id, genre_id, radiodj_ip, track_started = mqtt.Client.message.split('^')

      if float(subcat_id) == traffic_sub_cat_id:
        logger.info("Turning on traffic flag")
        (result, mosquitto_id) = mosquitto.publish(config.get('now_playing_traffic', 'ta_flag'), True, qos=1, retain=True)
        while not mosquitto.published_flag:
          time.sleep(0.1)

        traffic_flag = True
        traffic_finish =  float(track_started) + int(config.get("now_playing_traffic", "max_traffic_time_s"))
        logger.debug("Next metatdata update should happen before %s" % datetime.datetime.utcfromtimestamp(traffic_finish).strftime("%Y-%m-%d %H:%M:%S"))
      else:
        logger.debug("Not a traffic event")
        traffic_finish = 0
        if traffic_flag == True:
          logger.info("Turning off traffic flag")
          traffic_flag = False
          (result, mosquitto_id) = mosquitto.publish(config.get('now_playing_traffic', 'ta_flag'), False, qos=1, retain=True)
          while not mosquitto.published_flag:
            time.sleep(0.1)

    else:
      if time.time() > traffic_finish and traffic_finish != 0:
        logger.debug("Oops!, we have over run, clear traffic flag")
        traffic_finish = 0
        logger.info("Turning off traffic flag")
        traffic_flag = False
        (result, mosquitto_id) = mosquitto.publish(config.get('now_playing_traffic', 'ta_flag'), False, qos=1, retain=True)
        while not mosquitto.published_flag:
          time.sleep(0.1)

    mqtt.Client.message = ''


#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#---------------------------------------------------------------------------
if __name__ == "__main__":
#    exit()
    main()
