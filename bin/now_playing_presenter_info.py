#!/usr/bin/env python
#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Listen to a mosquitto topic now_playing_rds
# Turn the data into html for displaying to presenter
# Show now, next and previous played tracks
# Also show last 5 tracks played.
#===========================================================================
# Modifications
#---------------------------------------------------------------------------

import paho.mqtt.client as mqtt
mqtt.Client.connected_flag = False
mqtt.Client.mqtt_result = 0
mqtt.Client.message = ''
mqtt.Client.logger = 0

import platform

import requests
import lxml.html

import MySQLdb

import time
import uuid
import datetime
import socket
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
    handler = logging.FileHandler(config.get("now_playing_presenter_info", "log_file"), mode='a')
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

  mosquitto = mqtt.Client(client_id = "now_playing_pi_%s" % uuid.uuid4(), clean_session=True)
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

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# on_disconnect
#---------------------------------------------------------------------------
def on_disconnect(client, userdata, rc):
  mqtt.Client.logger.debug("Unexpected disconnection")

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#on_publish callback for mosquitto
# Gets called once we have published (?maybe)
#---------------------------------------------------------------------------
def on_publish(client, userdata, mid):
  mqtt.Client.logger.debug("Published message")

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#publish_to_mosquitto MQTT
#---------------------------------------------------------------------------
def publish_to_mosquitto(mosquitto, topic, metadata_to_send, logger):

  (result, mosquitto_id) = mosquitto.publish(topic, metadata_to_send, qos=1, retain=True)
  logger.debug("Metadata sent to mosquitto:%s. Result = %s" % (topic, result))

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Get next track to play, ignore non-music entries
#---------------------------------------------------------------------------
def get_next_track(radiodj_ip, logger, db):

  entry = 0
  params = {'auth':12345, 'arg':entry}
  url = "http://%s:7000/pitem" % radiodj_ip
  r = requests.get(url = url, params = params)
  if r.status_code  == 200:
    xml = lxml.html.fromstring(r.text)
    logger.debug("song type = %s" % xml.xpath('//tracktype')[0].text_content())

    while xml.xpath('//tracktype')[0].text_content() != 'Music' or r.status_code != 200:
      entry += 1
      params = {'auth':12345, 'arg':entry}
      r = requests.get(url = url, params = params)
      logger.debug("Response status = %s" % r.status_code)
      xml = lxml.html.fromstring(r.text)
      logger.debug("song type = %s" % xml.xpath('//tracktype')[0].text_content())

    artist = xml.xpath('//artist')[0].text_content()
    title = xml.xpath('//title')[0].text_content()
    album = xml.xpath('//album')[0].text_content()
    composer = xml.xpath('//composer')[0].text_content()
    publisher = xml.xpath('//publisher')[0].text_content()
    copyright = xml.xpath('//copyright')[0].text_content()
    year = xml.xpath('//year')[0].text_content()
    track_no = xml.xpath('//trackno')[0].text_content()
    disc_no = xml.xpath('//discno')[0].text_content()
    comments = xml.xpath('//comments')[0].text_content()
    original_artist = xml.xpath('//originalartist')[0].text_content()
    id = xml.xpath('//id')[0].text_content()
  else:
    logger.debug("Response status = %s" % r.status_code)
    artist = ''
    title = ''
    album = ''
    composer = ''
    publisher = ''
    copyright = ''
    year = ''
    track_no = ''
    disc_no = ''
    comments = ''
    original_artist = ''
    id = ''
    
  return artist, title, album, composer, publisher, copyright, year, track_no, disc_no, comments, original_artist, id

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#Build the now next to play html
#---------------------------------------------------------------------------
def build_next(logger, radiodj_ip, db):

  artist, title, album, composer, publisher, copyright, year, track_no, disc_no, comments, original_artist, song_id = get_next_track(radiodj_ip, logger, db)

  logger.debug("In build_next. Title = %s" % title)
  logger.debug("song_id = '%s'" % song_id);

  if song_id == '':
    html = ''
  else:
    c = db.cursor()
    sql = "select ifnull(year_made_number_1, '') year_made_number_1 \
           from songs_extra se where se.song_id = %s" % song_id
    try:
      c.execute(sql)
    except MySQLdb.Error as err:
      logger.error("Error %d: %s" % (err.args[0], err.args[1]))
      logger.error("sql = '%s'" % sql)
      sys.exit(1)

    year_made_number_1 = c.fetchone()

    if year_made_number_1 is None:
      year_made_number_1 = ''

    params = {'auth':12345, 'arg':0}

    html = "<table>"
    html += "<tr><td width='95px' align='right'>Title:</td><td>%s</td></tr>" % title
    html += "<tr><td width='95px' align='right'>Artist:</td><td>%s</td></tr>" % artist
    html += "<tr><td width='95px' align='right'>Album:</td><td>%s</td></tr>" % album
    html += "<tr><td width='95px' align='right'>Composer:</td><td>%s</td></tr>" % composer
    html += "<tr><td width='95px' align='right'>Publisher:</td><td>%s</td></tr>" % publisher
    html += "<tr><td width='95px' align='right'>Copyright:</td><td>%s</td></tr>" % copyright
    html += "<tr><td width='95px' align='right'>Year:</td><td>%s</td></tr>" % year
    html += "<tr><td width='95px' align='right'>Track/CD:<td>%s/%s</td></tr>" % (track_no, disc_no)
    html += "<tr><td width='95px' align='right'>Year made #1:</td><td>%s</td></tr>" % year_made_number_1
    html += "<tr><td width='95px' align='right'>Original Artist:</td><td>%s</td></tr>" % original_artist
    html += "<tr><td width='95px' align='right'>Comments:</td><td>%s</td></tr>" % comments
    html += "</table>"
    html += "<a target='_blank' href=\"https://www.google.com/search?q=%s %s\"><img border='0' alt='Search' src='search.jpg' width='150'></a>" % (title, artist)

  return html
  
#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#Build the now playing html
#---------------------------------------------------------------------------
def build_now(logger, metadata, db):

  path, track_id, artist, title, album, album_cover, year, track_no, disc_no, bpm, rotation_name, rotation_id, \
    duration_in_seconds, song_type, subcat_id, genre_id, radiodj_ip, track_started = metadata.split('^')
  
  logger.debug("In build_now. Ttile = %s" % title)

  if int(song_type) == 0:
    c = db.cursor()
    sql = "select original_artist, composer, publisher, copyright, comments, ifnull(year_made_number_1, '') year_made_number_1 \
           from songs s left join songs_extra se on s.id = se.song_id where s.id = %s" % track_id
    try:
      c.execute(sql)
    except MySQLdb.Error as err:
      logger.error("Error %d: %s" % (err.args[0], err.args[1]))
      logger.error("sql = '%s'" % sql)
      sys.exit(1)

    original_artist, composer, publisher, copyright, comments, year_made_number_1 = c.fetchone()

    html = "<table>"
    html += "<tr><td width='95px' align='right'>Title:</td><td>%s</td></tr>" % title
    html += "<tr><td width='95px' align='right'>Artist:</td><td>%s</td></tr>" % artist
    html += "<tr><td width='95px' align='right'>Album:</td><td>%s</td></tr>" % album
    html += "<tr><td width='95px' align='right'>Composer:</td><td>%s</td></tr>" % composer
    html += "<tr><td width='95px' align='right'>Publisher:</td><td>%s</td></tr>"  % publisher
    html += "<tr><td width='95px' align='right'>Copyright:</td><td>%s</td></tr>" % copyright
    html += "<tr><td width='95px' align='right'>Year:</td><td>%s</td></tr>" % year
    html += "<tr><td width='95px' align='right'>Track/CD:<td>%s/%s</td></tr>" % (track_no, disc_no)
    html += "<tr><td width='95px' align='right'>Year made #1:</td><td>%s</td></tr>" % year_made_number_1
    html += "<tr><td width='95px' align='right'>Original Artist:</td><td>%s</td></tr>" % original_artist
    html += "<tr><td width='95px' align='right'>comments:</td><td>%s</td></tr>" % comments
    html += "</table>"
    html += "<a target='_blank' href=\"https://www.google.com/search?q=%s %s\"><img border='0' alt='Search' src='search.jpg' width='150'></a>" % (title, artist)
  else:
    html = ""

  return html

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Build the html for the next 5 tracks that will play
#---------------------------------------------------------------------------
def build_next_5(logger, db):

  logger.debug("in next_5")

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Build the html for the last 5 tracks that played
#---------------------------------------------------------------------------
def build_last_5(logger, db):

  logger.debug("In build_last_5")

  sql = "select time(date_played), title, artist from history where active = 1 and song_type = 0 and date_played = date_played order by date_played desc limit 2,7"
  c = db.cursor()
  c.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
  try:
    c.execute(sql)
  except MySQLdb.Error as err:
    logger.error("Error %d: %s" % (err.args[0], err.args[1]))
    logger.error("sql = '%s'" % sql)
    sys.exit(1)

  html = "<ul>"
  row = c.fetchone()
  while row is not None:
    html += "<li>%s, %s <b>-</b> %s</li>" % (row[0], row[1], row[2])
    row = c.fetchone()

  html += "</ul>"
  c.execute("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
  return html

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
  config.read(options.config_file)

#+
#Setup custom logging
#-
  logger = custom_logger(config.get('now_playing_presenter_info', 'logger_name'), options.logger_level, config, options.log_to_screen)
  mqtt.Client.logger = logger
  logger.info("Hello world! Python version = '%s'" % platform.python_version())

#+
#Connect to database
#-
  try:
    db = MySQLdb.connect(host = config.get("sql", "host"), user = config.get("sql", "username"), passwd = config.get("sql", "password"), db = config.get("sql", "database"))
#    db.autocommit(True)
  except MySQLdb.Error as err:
    logger.error("Error %d: %s" % (err.args[0], err.args[1]))
    sys.exit(1)

#+
#Connect to mosquitto, the MQTT broker
#-
  mosquitto = connect_to_mosquitto(logger, config)
  mosquitto.subscribe('now_playing_pi_feed', 1)
  prev_html = ''
  now_html = ''

#+
#Loop until hell freezes over
#-
  while True:
    if mqtt.Client.message != '':
      logger.debug("Got a message")
      path, track_id, artist, title, album, album_cover, year, track_no, disc_no, bpm, rotation_name, rotation_id, \
        duration_in_seconds, song_type, subcat_id, genre_id, radiodj_ip, track_started = mqtt.Client.message.split('^')
  
      if now_html != '':
        publish_to_mosquitto(mosquitto, 'pi/prev', now_html, logger)

      next_html = build_next(logger, radiodj_ip, db)
      publish_to_mosquitto(mosquitto, 'pi/next', next_html, logger)

      last_5_html = build_last_5(logger, db)
      publish_to_mosquitto(mosquitto, 'pi/last_5', last_5_html, logger)
      if int(song_type) == 0:
        now_html = build_now(logger, mqtt.Client.message, db)
        publish_to_mosquitto(mosquitto, 'pi/now', now_html, logger)
      else:
        publish_to_mosquitto(mosquitto, 'pi/now', '', logger)

      mqtt.Client.message = ""

    time.sleep(0.5)


#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#---------------------------------------------------------------------------
if __name__ == "__main__":
#    exit()
    main()
