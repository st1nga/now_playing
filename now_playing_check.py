#!/usr/bin/env python
#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Listen to the now playing mqtt broker.
# If we don't get a new message by the time the last track has expired
# Then force an update
#===========================================================================
# Modifications
#---------------------------------------------------------------------------

import paho.mqtt.client as mqtt
mqtt.Client.connected_flag = False
mqtt.Client.mqtt_result = 0
mqtt.Client.message = ''
mqtt.Client.retained_message = False

import time
import uuid
import datetime

import ConfigParser
import logging
from optparse import OptionParser

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
# Called when we sucessfully connect to mqtt broker
#---------------------------------------------------------------------------
def on_connect(client, userdata, flags, rc):

  client.mqtt_result = rc

  if rc==0:
    client.connected_flag=True

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Called when we sucessfully subscribe to a topic
#---------------------------------------------------------------------------
def on_subscribe(client, userdata, mid, granted_qos):
  print "We have subscribed"

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Called when we receive a message from mqtt
#---------------------------------------------------------------------------
def on_message(client, userdata, message):
  now = datetime.datetime.now()

  mqtt.Client.message = str(message.payload.decode("utf-8"))
  mqtt.Client.retained_message = message.retain

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

  config_file = '/etc/now_playing.conf'
  parser.add_option("", "--config", dest="config_file",
    help="Config file [Default=%default]", default="/etc/now_playing.conf")

  (options, args) = parser.parse_args()
#+
#Load the config file
#-
  config = ConfigParser.ConfigParser()
  config.read(config_file)

#+
#Setup custom logging
#-
  logger = custom_logger('now_playing_check', options.logger_level, config)
  logger.info("Hello world!")

#+
#Connect to mosquitto, the MQTT broker
#-
  mosquitto = mqtt.Client(client_id = "now_playing_%s" % uuid.uuid4(), clean_session=True)
  mosquitto.username_pw_set(username = "now_playing", password = "ooXaku4vuh4eWae2")
  mosquitto.on_connect = on_connect
  mosquitto.on_subscribe = on_subscribe
  mosquitto.on_message = on_message
  mosquitto.connect("nostromo", 1883)
  mosquitto.loop_start()

#+
#Loop until we have connected
#-
  while not mosquitto.connected_flag:
    time.sleep(1)

    if mosquitto.mqtt_result == 0:
      print "Connected OK to mosquitto"
    else:
      print "Bad mosquitto connection: %s"  % rc
      sys.exit()

  mosquitto.subscribe(("now_playing",1))

#If we get a type 0 message then reset the timer
#Any other type we can ignore
#Keep sleeping for a second but check to see if we have a message if the track time ends + x seconds before the next message then send a generic message
#in fact we can connect to no_playing and send a timeout message
  while True:
    time.sleep(0.5)

#+
#Do we have a message?
#-
    if mqtt.Client.message != '':
      now = datetime.datetime.now()
      if mqtt.Client.message.startswith('metadata'):
        type, title, artist, duration_in_seconds, song_type = mqtt.Client.message.split('^')
        print("%s: RDS data is... artist=%s, title=%s, other info is duration_in_seconds=%s, song_type=%s" % (now.strftime("%Y-%m-%d %H:%M:%S"), title, artist, duration_in_seconds, song_type))
      else:
        print("%s: RDS would display diary entry '%s'" % (now.strftime("%Y-%m-%d %H:%M:%S"), mqtt.Client.message))

      mqtt.Client.message = ''

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#---------------------------------------------------------------------------
if __name__ == "__main__":
#    exit()
    main()
