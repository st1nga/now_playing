#!/usr/bin/env python
#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Listen to now playing info, if from active studio forward to relevent places
#===========================================================================
# Modifications
#---------------------------------------------------------------------------

import MySQLdb

import tldextract

import socket
import logging
import os
import sys

from optparse import OptionParser


#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#---------------------------------------------------------------------------
def custom_logger(name, logger_level):
    '''Custom logging module'''

    logger_level = logger_level.upper()

    formatter = logging.Formatter(fmt='%(asctime)s %(process)-5d %(levelname)-8s %(lineno)-4d: %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    handler = logging.FileHandler('/var/log/now_playing.log', mode='a')
    handler.setFormatter(formatter)
#    screen_handler = logging.StreamHandler(stream=sys.stdout)
#    screen_handler.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.setLevel(logging.getLevelName(logger_level))
    logger.addHandler(handler)
#    logger.addHandler(screen_handler)
    return logger

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# We have now playing data for the active studio
#---------------------------------------------------------------------------
def send_now_playing(logger, now_playing_data):

  path, track_id, artist, title, album, album_cover, year, track_no, disc_no, bpm, rotation_name, rotation_id, duration_in_seconds, track_type, subcat_id, genre_id = now_playing_data.split('^')
  logger.info("Playing '%s' by '%s' it is %s seconds long" % (title, artist, duration_in_seconds))


#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# This is the child process.
#---------------------------------------------------------------------------
def now_playing(radiodj_addr, now_playing_socket, radiodj, logger):

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
    db = MySQLdb.connect(host="database", user="now_playing_r", passwd="now_playing", db="radiodj")
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
  db.close()

  (radiodj_fqdn, junk, junk) = socket.gethostbyaddr(radiodj_ip)
  (radiodj_host, radiodj_domain, radiodj_suffix) = tldextract.extract(radiodj_fqdn)

  if radiodj_host == active_studio:
    logger.debug("Connection from active studio|||")
    send_now_playing(logger, now_playing_data)

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#---------------------------------------------------------------------------
def main():
  
  listen_host = '0.0.0.0'
  listen_port = socket.getservbyname('now_playing', 'tcp')

#Parse the options passed
  parser = OptionParser()
  parser.add_option("", "--logger-level", dest="logger_level",
    help="Log level: ERROR, WARNING, INFO, DEBUG [Default=%default]", default="INFO")

  (options, args) = parser.parse_args()

#Setup custom logging
  logger = custom_logger('now_playing', options.logger_level)
  logger.info("Hello world!")

#bind to the now_playing port
  now_playing_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  now_playing_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

  try:
    now_playing_socket.bind((listen_host, listen_port))
  except socket.error, err:
    logger.error("Error %d:%d: %d: %s" % (listen_host, listen_port, err.args[0], err.args[1]))
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
      now_playing(addr, now_playing_socket, radiodj, logger)
      sys.exit(0)
  

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#---------------------------------------------------------------------------
if __name__ == "__main__":
#    exit()
    main()

