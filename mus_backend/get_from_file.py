'''
This script reads in data from files, lightly processes it if necessary, and
stores it into mongoDB. The data can then be used to create the main entries
in the django SQL database.

Example files:
worldcat kbart
pure reports

'''
from loguru import logger
from django.conf import settings
from pymongo import MongoClient
import xmltodict
import re
from gzip import GzipFile
from rich import print
import csv
from time import time
from PureOpenAlex.models import DBUpdate

MONGOURL = getattr(settings, "MONGOURL")
APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")
client=MongoClient(MONGOURL)
db=client['mus']
mongo_dblp_raw=db['file_dblp_raw']
mongo_pure_report_start_tcs=db['pure_report_start_tcs']
mongo_pure_report_ee=db['pure_report_ee']
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
            msg=f"{processed} processed dblp items, added {added}"
            logger.debug(msg)
        return True

    xmltodict.parse(GzipFile('dblp.xml.gz'),
                    item_depth=2, item_callback=handle_dblp)

def getfrompurereport(group):
    result={'pureids':[], 'total':0}
    filename=f'pure_report_{group}'
    if group == 'ee':
        mongocoll=mongo_pure_report_ee
    elif group == 'tcs':
        mongocoll=mongo_pure_report_start_tcs
    start = time()
    i=0
    final = []
    datasetkeys = ['linked_dataset_title','linked_dataset_pureid','linked_dataset_doi', 'linked_dataset_url']
    datekeys = ['date_created', 'last_modified', 'date_earliest_published','date_published','date_eprint_first_online']
    itemkeys= ['date_created','last_modified']
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')

    with open(f"{filename}.csv", encoding='utf-8') as f:
        data = csv.DictReader(f)
        for item in data:
            itemdict={}
            tmp_utauthors={}
            tmp_dataset={}
            tmp_pubdates={}
            tmp_itemdates={}
            i=i+1
            for key, value in item.items():
                if value=='Not set' or value=='0.0':
                    value=''
                if '|' in value:
                    value = value.split('|')
                    value=[i.strip() for i in value]
                else:
                    value=value.strip()

                if key == 'ut_authors' or key == 'author_pureids':
                    tmp_utauthors[key]=value
                elif key in datekeys:
                    if isinstance(value, str) and value:
                        if len(value)>=10:
                            if not date_pattern.match(value):
                                if date_pattern.match(value[0:10]):
                                    value=value[0:10]
                                else: # no match
                                    value=''
                        else:
                            value=''

                    if value!='':
                        if key in itemkeys:
                            tmp_itemdates[key]=value
                        else:
                            tmp_pubdates[key]=value

                elif key in datasetkeys:
                    if value!='':
                        tmp_dataset[key]=value
                else:
                    itemdict[key] = value


            if 'ut_authors' in tmp_utauthors.keys() and 'author_pureids' in tmp_utauthors.keys():
                if isinstance(tmp_utauthors['ut_authors'], str):
                    itemdict['ut_authors']=[{'name:':tmp_utauthors['ut_authors'], 'pureid':tmp_utauthors['author_pureids']}]
                elif isinstance(tmp_utauthors['ut_authors'], list) and len(tmp_utauthors['ut_authors'])==len(tmp_utauthors['author_pureids']):
                    combinedlist = zip(tmp_utauthors['ut_authors'], tmp_utauthors['author_pureids'])
                    ut_authors = []
                    for entry in combinedlist:
                        ut_authors.append({
                            'name': entry[0],
                            'pureid': entry[1]
                        })
                    itemdict['ut_authors']= ut_authors
                else:
                    itemdict['ut_authors']=tmp_utauthors['ut_authors']
                    itemdict['author_pureids']=tmp_utauthors['author_pureids']

            if tmp_dataset!={}:
                itemdict['dataset']=tmp_dataset
            if tmp_pubdates!={}:
                itemdict['publication_dates']=tmp_pubdates
            if tmp_itemdates!={}:
                itemdict['pure_entry_dates']=tmp_itemdates
            final.append(itemdict)
    elapsed = time() - start
    h=0
    msg=f"in {elapsed:.1f}s: Processed {i} records from Pure Report {filename}.csv"
    logger.info(msg)

    addlist=[]
    for item in final:
        if mongocoll.find_one({"pureid":item['pureid']}):
            continue
        else:
            addlist.append(item)
            result['total']+=1
            result['pureids'].append(item['pureid'])
    if addlist:
        mongocoll.insert_many(addlist)

    return result if result['total']>0 else None



def addfromfiles():
    result = getfrompurereport('ee')
    if result:
        dbupdate=DBUpdate.objects.create(update_source="Pure EE Report", update_type="manualmongo", details = result)
        dbupdate.save()
    '''result = getfrompurereport('tcs')
    if result:
        dbupdate=DBUpdate.objects.create(update_source="Pure TCS Report", update_type="manualmongo", details = result)
        dbupdate.save()'''