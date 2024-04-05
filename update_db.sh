#!/bin/bash
# note: add to crontab with crontab -e, run every day?
# dont forget to chmod +x this file as well
# and pipe files to log, ex:
# 15 0 * * * /path/to/run_updateapi.sh >> /path/to/logfile.log 2>&1

cd /usr/local/mus/
source /usr/local/mus/.venv/bin/activate
export DJANGO_SETTINGS_MODULE=mus.settings
python manage.py updatedb
