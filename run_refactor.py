import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mus.settings")
import django
django.setup()
import xclass_refactor
from xclass_refactor.class_refactor import main
main()