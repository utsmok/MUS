import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mus.settings")
import django
django.setup()
from xclass_refactor.updatemanager import main
main()