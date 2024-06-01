import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mus.settings")
import django
django.setup()
from mus_wizard.wizard import main
main()