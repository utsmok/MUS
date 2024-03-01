'''
This script reads in data from files, lightly processes it if necessary, and
stores it into mongoDB. The data can then be used to create the main entries
in the django SQL database.

Example files:
worldcat kbart
pure reports

'''
from lxml import etree
import pymongo
from django.conf import settings
from pymongo import MongoClient
import xmltodict
import orjson
from gzip import GzipFile
from rich import print
MONGOURL = getattr(settings, "MONGOURL")
APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")
client=MongoClient(MONGOURL)
db=client['mus']
mongo_dblp_raw=db['file_dblp_raw']
global added
global processed
added = 0
processed = 0

def getdblp():

    def handle_dblp(_, item):
        global added
        global processed
        processed += 1
        if item.get('year'):
            if item.get('year') >= '2018':
                mongo_dblp_raw.insert_one(item)
                added += 1
        if added % 1000 == 0:
            print(processed, "processed, added", added)
        return True

    xmltodict.parse(GzipFile('dblp.xml.gz'),
                    item_depth=2, item_callback=handle_dblp)



