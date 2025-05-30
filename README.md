# sonarr_remove_from_queue_if_dupe_script
This script is designed to look for ‘SAMPLE’ items stuck in Sonarr queue. It will then remove the file from NZBGET and clear the queue cache from Sonarr and force Sonarr to search again for a new file that is not a sample. This is a python script. It can be run manually or you can add it to your cron job. This will also generate a log file within the same directory as the script called sonarr_sample_clearner.log

This has been tested using Ubuntu 22.04

Items to Update in Script:

API KEY for Sonarr
BASE URL for Sonarr
NZBGET URL
NZBGET USERNAME
NZBGET PASSOWRD
