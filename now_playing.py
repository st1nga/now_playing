#!/usr/bin/env python
#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# List to now_playing port, fork on connection.
# Determine active studio, ignore non active studio.
# If studio active get data and pass on to required sources.
#--------------------------------------------------------------------------

import MySQLdb
import socket
import select
import logging
import sys
import struct
import inspect


from optparse import OptionParser

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# Define a custom logger - because I like these :-)
#---------------------------------------------------------------------------
def custom_logger(name, logger_level):
    '''Custom logging module'''

    logger_level = logger_level.upper()

    formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(lineno)-4d: %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    handler = logging.FileHandler('/var/log/now_playing.log', mode='a')
    handler.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.setLevel(logging.getLevelName(logger_level))
    logger.addHandler(handler)
    return logger

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# MAIN Main main
#---------------------------------------------------------------------------
def main():

#Parse options

  parser = OptionParser()
  parser.add_option("", "--logger-level", dest="logger_level",
    help="Log level: ERROR, WARNING, INFO, DEBUG [Default=%default]", default="INFO")

  (options, args) = parser.parse_args()

  logger = custom_logger('now_playing', options.logger_level)
  logger.info("Hello world!")

#Get port number
  port = socket.getservbyname('now_playing', 'tcp')

#bind to port so that we can accept commands from webpage
  now_playing_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  now_playing_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

  logger.info("Binding to port %d" % (port))

  try:
     now_playing_socket.bind(('0.0.0.0', port))
  except now_playing_socket.error, err:
    logger.error("Error 0.0.0.0:%d: %d: %s" % (port, err.args[0], err.args[1]))
    sys.exit(1)

#Listen for a connection

  now_playing_socket.listen(1)
  

#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#---------------------------------------------------------------------------
if __name__ == "__main__":
#    exit()
    main()

