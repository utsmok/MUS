import pyalex
from pyalex import Works
from .namematcher import NameMatcher
from .models import  Paper, viewPaper, PureEntry
from django.db import transaction
from .data_process_mongo import processMongoPaper, processMongoPureEntry, processMongoOpenAireEntry, processMongoTCSPilotEntry
from pymongo import MongoClient
from django.conf import settings
from loguru import logger
import pymongo
from rich import print

APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")
OPENAIRETOKEN = getattr(settings, "OPENAIRETOKEN", "")

pyalex.config.email = APIEMAIL

"""
data_add.py description

This script contains the functions that handle adding new papers to the Django OpenAlex database from OpenAlex or Pure.

"""

SCORETHRESHOLD = 0.98  # for namematching authors on UT peoplepage
APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")

pyalex.config.email = APIEMAIL
name_matcher = NameMatcher()

client=MongoClient(getattr(settings, 'MONGOURL', None))
db=client['mus']
mongo_openaire_results = db['api_responses_openaire']
openalex_works=db['api_responses_works_openalex']
crossref_info=db['api_responses_crossref']
pure_works=db['api_responses_pure']
tcs_pilot_entries=db['pure_report_start_tcs']


def addOpenAlexWorksFromMongo():
    datasets=[]
    i=0
    j=0
    filterdois = Paper.objects.all().values_list('doi', flat=True).order_by('doi')
    for document in openalex_works.find().sort('doi'):
        if document['doi'] in filterdois:
            continue
        crossrefdoc={}
        try:
            doi=document['doi'].replace('https://doi.org/','')
            crossrefdoc=crossref_info.find_one({'DOI':doi})
        except Exception:
            continue

        if doi is None:
            continue

        dataset={
            'works_openalex':document,
            'crossref':crossrefdoc,
        }
        datasets.append(dataset)
        i=i+1

        if i % 1000 == 0:
            message=f"{i} works currently in dataset"
            logger.info(message)

    message=f"processing {len(datasets)}  works"
    logger.info(message)
    added=[]
    k=0
    for dataset in datasets:
        j=j+1
        id=dataset['works_openalex']['id']
        try:
            processMongoPaper(dataset)
        except Exception as e:
            logger.exception('exception {e} while adding work with doi {doi}',doi=id,e=e)
        added.append(id)
        if len(added)>=100:
            k=k+len(added)
            message=f"{k} works added (+{len(added)})"
            logger.info(message)
            added=[]

def addPureWorksFromMongo():
    datasets=[]
    i=0
    k=0
    s=0
    pureentries = PureEntry.objects.all().only('doi','researchutwente', 'risutwente')
    sets={}
    sets['doi'] = set(pureentries.values_list('doi', flat=True))
    sets['ris_file'] = set(pureentries.values_list('risutwente', flat=True))
    sets['ris_page'] = set(pureentries.values_list('researchutwente', flat=True))
    allapientrys = pure_works.find().sort('date',pymongo.DESCENDING)
    for document in allapientrys:
        stop=False
        for checkitemstr in ['doi', 'ris_file', 'ris_page']:
            checkitem = document.get('identifier').get(checkitemstr)
            if checkitem:
                if isinstance(checkitem, list):
                    checkitem = checkitem[0]
                if checkitem in sets[checkitemstr]:

                    stop=True
                    break

        if stop:
            s=s+1
            continue
        
        datasets.append(document)
        i=i+1
        if i % 500 == 0:
            message=f"processing batch of {len(datasets)} works, skipped {s} works"
            logger.info(message)            
            for dataset in datasets:
                try:
                    processMongoPureEntry(dataset)
                except Exception as e:
                    logger.exception('exception {e} while adding PureEntry', e=e)
                    continue
                k=k+1
                if k%100==0:
                    message=f"{k} works added in total"
                    logger.info(message)
            datasets=[]

    message=f"final batch: processing {len(datasets)} works"
    logger.info(message)            
    for dataset in datasets:
        try:
            processMongoPureEntry(dataset)
        except Exception as e:
            logger.exception('exception {e} while adding PureEntry', e=e)
            continue
        k=k+1
        if k%100==0:
            message=f"{k} works added in total"
            logger.info(message)

def addOpenAireWorksFromMongo():
    datasets=[]
    i=0
    k=0
    h=0
    for document in mongo_openaire_results.find().sort('date',pymongo.DESCENDING):
        datasets.append(document)
        i=i+1
        if i % 500 == 0:
            message=f"processing batch of {len(datasets)} OpenAire works"
            logger.info(message)            
            print(message)
            for dataset in datasets:
                try:
                    updated = processMongoOpenAireEntry(dataset)
                    if updated:
                        h=h+1
                except Exception as e:
                    logger.exception('exception {e} while adding OpenAire item {id}', e=e, id=dataset['id'])
                    print(f'exception {e} while adding OpenAire item {dataset['id']}')
                    continue
                k=k+1
                if k%100==0:
                    message=f"processed {k} entries, {h} updated"
                    logger.info(message)
                    print(message)
            datasets=[]
    message=f"final batch: processing {len(datasets)} works"
    logger.info(message)            
    print(message)
    for dataset in datasets:
        try:
            updated = processMongoOpenAireEntry(dataset)
            if updated:
                h=h+1
        except Exception as e:
            logger.exception('exception {e} while adding OpenAire item {id}', e=e, id=dataset['id'])
            print(f'exception {e} while adding OpenAire item {dataset['id']}')
            continue
        k=k+1
    
    message=f"processed {k} entries, {h} updated"
    logger.info(message)
    print(message)

def addTCSPilotWorksFromMongo():
    datasets=[]
    i=0
    k=0
    h=0
    for document in tcs_pilot_entries.find():
        datasets.append(document)
        i=i+1
        if i % 500 == 0:
            message=f"processing batch of {len(datasets)} TCS pure entries"
            print(message)
            for dataset in datasets:
                entry = processMongoTCSPilotEntry(dataset)
                if entry:
                    h=h+1
                k=k+1
                if k%100==0:
                    message=f"processed {k} entries, {h} updated"
                    logger.info(message)
                    print(message)
            datasets=[]
    message=f"final batch: processing {len(datasets)} works"
    logger.info(message)            
    print(message)
    for dataset in datasets:
        entry = processMongoTCSPilotEntry(dataset)
        if entry:
            h=h+1

        k=k+1
    
    message=f"processed {k} entries, {h} updated"
    logger.info(message)
    print(message)

def addPaper(doi, user):
    status = 'danger'
    message = f'An unknown error occurred while adding paper {doi} for {user}.'
    openalex_url = ''
    paper = Paper.objects.filter(doi=doi).first()
    if paper:
        openalex_url = paper.openalex_url
        message = f'Paper {doi} in db, but failed to create bookmark'
        viewpaper, created = viewPaper.objects.get_or_create(
            displayed_paper=paper, user=user
        )
        if created:
            with transaction.atomic():
                viewpaper.save()
        status = 'success'
        message = f'Paper {doi} added to bookmarks for {user}.'
        return status, message, openalex_url
    
    mongo_oa_work = openalex_works.find_one({'doi':doi})
    if mongo_oa_work:
        message = f'raw data for {doi} retrieved, but failed to insert into database.'
        data={}
        data['works_openalex']=mongo_oa_work
        paper, view = processMongoPaper(data, user)
        if isinstance(paper, Paper) and isinstance(view, viewPaper):
            status = 'success'
            message = f'Paper {doi} added to db & bookmarks for {user}.'
            openalex_url = paper.openalex_url
            return status, message, openalex_url
    
    openalexresult = Works()[doi]
    message = f'No data for {doi} found in OpenAlex'
    if openalexresult:
        message = f'New data for {doi} retrieved from OpenAlex, but failed to insert into database.'
        result=openalex_works.insert_one(openalexresult)
        if result.inserted_id:
            data={}
            data['works_openalex']=openalex_works.find_one({'_id':result.inserted_id})
            paper, view = processMongoPaper(data, user)
            if isinstance(paper, Paper) and isinstance(view, viewPaper):
                openalex_url = paper.openalex_url
                status = 'success'
                message = f'Paper {doi} added to db & bookmarks for {user}.'
                return status, message, openalex_url
    
    return status, message, openalex_url