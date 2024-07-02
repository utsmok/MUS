import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mus.settings")
import django
django.setup()

#from mus_wizard.wizard import main
#main()
from mus_wizard.ut_publish_read import HarvestData
from mus_wizard.utwente.pure_report_import import PureReport
import asyncio

#asyncio.run(HarvestData().run())
PureReport().run()


