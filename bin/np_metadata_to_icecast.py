#!/usr/bin/env python
#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Listen to a mosquitto topic now_playing_rds
# Do a curl request to icecast server to update metadata
#===========================================================================
# Modifications
#---------------------------------------------------------------------------

import paho.mqtt.client as mqtt
mqtt.Client.connected_flag = False
mqtt.Client.mqtt_result = 0
mqtt.Client.message = ''
mqtt.Client.logger = 0
mqtt.Client.config = 0

import platform

import urllib.parse
import requests
import lxml.html

import time
import uuid
import datetime
import signal

import sys

import configparser
import logging
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
    handler = logging.FileHandler(config.get("np_metadata_to_icecast", "log_file"), mode='a')
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

  mosquitto = mqtt.Client(client_id = "np_metadata_to_icecast_%s" % uuid.uuid4(), clean_session=True)
  mosquitto.username_pw_set(username = config.get("mqtt", "username"), password = config.get("mqtt", "password"))
  mosquitto.on_connect = on_connect
  mosquitto.on_subscribe = on_subscribe
  mosquitto.on_message = on_message
  mosquitto.on_disconnect = on_disconnect
  mosquitto.connect(config.get("mqtt", "host"), int(config.get("mqtt", "port")))

  return mosquitto

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Called when we sucessfully connect to mqtt broker
#---------------------------------------------------------------------------
def on_connect(mosquitto, userdata, flags, rc):
  
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
  title, artist, duration_in_seconds, track_started, subcat_id = mqtt.Client.message.split('^')
  if artist == '':
    metadata = title
  else:
    metadata = "%s - %s" % (artist, title)

  metadata = urllib.parse.quote_plus(metadata)

#+
#send the metadata to the icecast server
#-
  url = mqtt.Client.config.get('np_metadata_to_icecast', 'url') % metadata
  mqtt.Client.logger.debug("URL = %s" % url)
  r = requests.get(url = url, auth=(mqtt.Client.config.get('np_metadata_to_icecast', 'username'), mqtt.Client.config.get('np_metadata_to_icecast', 'password')))
  mqtt.Client.logger.debug("status = '%s'" % r.status_code)

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
#Catch control-c
#-
  signal.signal(signal.SIGINT, signal_handler)

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
  config = configparser.ConfigParser()
  mqtt.Client.config = config
  config.read(options.config_file)

#+
#Setup custom logging
#-
  logger = custom_logger(config.get('np_metadata_to_icecast', 'logger_name'), options.logger_level, config, options.log_to_screen)
  mqtt.Client.logger = logger
  logger.info("Hello world! Python version = '%s'" % platform.python_version())

#+
#Connect to mosquitto, the MQTT broker
#-
  mosquitto = connect_to_mosquitto(logger, config)
  mosquitto.subscribe('now_playing_rds', 1)

#+
#Tell mosquitto to loop waiting for messages
#-
  mosquitto.loop_forever()

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#---------------------------------------------------------------------------
if __name__ == "__main__":
#    exit()
    main()
