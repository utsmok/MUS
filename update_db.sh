#!/bin/bash
cd /usr/local/mus/
source /usr/local/mus/.venv/bin/activate
export DJANGO_SETTINGS_MODULE=mus.settings
python manage.py updateapi