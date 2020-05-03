# now_playing
A suite of programs that relate to now playing
## Overview
RadioDJ spits out now playing data to a specified port, 8001 in our case.
This data is processed and sent to various other programs via mosquitto (MQTT) and websockets.
## now_playing_feed.py
Listens to RadioDJ on port 8001.
Determines if the data is coming from the studio that is on air and write the message to mosquitto:now_playing
## now_playing_rds.py
Listens to mosquitto:now_playing
If the track is a song it send the message to mosquitto:now_playing_rds
If the track in not a song, it looks in the schedule to see what to display and spits that out to mosquitto:now_playing_rds and mosquitto:now_playing_traffic
Keeps track of the start time and length of the track being played if we don't get another message by the time it expires it forces an update using the schedule.
Also squirts a message to mosquitto:now_playing_presenter_info
## now_playing_traffic.py
Listens to mosquitto:now_playing_traffic, if the track is about travel it turns on the RDS TA flag.
Waits for another message from mosquitto for 90 seconds and then turns it off.
## now_playing_presenter_info.py
Listens to mosquitto:now_playing_presenter_info and write data to websockets pi/now pi/next and pi/prev.
The data it sends is html so that the web page can just display the html.
## np_metadata_to_icecast.py
Listens to mosquitto:now_playing_rds
Squirts data to icecast2

## boilerplate text
RadioDJ uses the following to send data
$path$^$track_id$^$artist$^$title$^$album$^$album_cover$^$year$^$track_no$^$disc_no$^$bpm$^$rotation_name$^$rotation_id$^$durationinSeconds$^$track-type$^$subcat-id$^$genre-id$
## Notes
pip install tldextract
