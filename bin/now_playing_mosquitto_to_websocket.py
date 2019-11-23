#!/usr/bin/env python
#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Listen to a mosquitto topic and send it out over a websocket
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
import signal

import sys

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
    handler = logging.FileHandler(config.get("now_playing_mosquitto_to_websocket", "log_file"), mode='a')
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
  logger = custom_logger(config.get('now_playing_poke', 'logger_name'), options.logger_level, config, options.log_to_screen)
  logger.info("Hello world!")

#+
#Connect to mosquitto, the MQTT broker
#-
  mosquitto = mqtt.Client(client_id = "now_playingp_poke_%s" % uuid.uuid4(), clean_session=True)
  mosquitto.username_pw_set(username = config.get("mqtt", "username"), password = config.get("mqtt", "password"))
  mosquitto.on_connect = on_connect
  mosquitto.on_subscribe = on_subscribe
  mosquitto.on_message = on_message
  mosquitto.on_disconnect = on_disconnect
  mosquitto.connect("nostromo", 1883)
  mosquitto.loop_start()

#+
#Loop until we have connected
#-
  while not mosquitto.connected_flag:
    time.sleep(1)

    if mosquitto.mqtt_result == 0:
      logger.debug("Connected OK to mosquitto")
    else:
      logger.error("Bad mosquitto connection: %s"  % rc)
      sys.exit()

  mosquitto.subscribe(("now_playing",1))

#If we get a type 0 message then reset the timer
#Any other type we can ignore
#Keep sleeping for a second but check to see if we have a message if the track time ends + x seconds before the next message then send a generic message
#in fact we can connect to no_playing and send a timeout message
  track_finish = 0
  while True:
    time.sleep(0.5)

#+
#Has track expired?
#-
#    if now > track_finished:
#      print "Track has finished, we should force an update to metadata"
#+
#Do we have a message?
#-
    if mqtt.Client.message != '':
      now = datetime.datetime.now()
      if mqtt.Client.message.startswith('metadata'):
        type, title, artist, duration_in_seconds, track_started, sub_cat_id = mqtt.Client.message.split('^')
        logger.info("RDS data is... artist=%s, title=%s, other info is duration_in_seconds=%s" % (title, artist, duration_in_seconds))

        track_finish =  datetime.datetime.now() + datetime.timedelta(seconds = int(duration_in_seconds) + int(config.get("general", "skip_short_track_s")))
        track_finish =  float(track_started) + int(duration_in_seconds) + int(config.get("general", "skip_short_track_s"))
        logger.debug("Next metatdata update should happen before %s" % datetime.datetime.utcfromtimestamp(track_finish).strftime("%Y-%m-%d %H:%M:%S"))
      else:
        logger.info("RDS data is... '%s'" % (mqtt.Client.message))
        track_finish = 0
      mqtt.Client.message = ''
    else:
      if time.time() > track_finish and track_finish != 0:
        now = datetime.datetime.now()
        logger.debug("Oops!, we have over run and not got a message")
        poke_now_playing(config, logger)


#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#---------------------------------------------------------------------------
if __name__ == "__main__":
#    exit()
    main()
