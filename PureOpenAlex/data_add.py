import pyalex
from pyalex import Works
from .namematcher import NameMatcher
from .models import PureEntry,  Paper, viewPaper
from django.db import transaction
from .data_process import processPaperData
from .data_process_mongo import processMongoPaper, processMongoPureEntry
from .data_repair import clean_duplicate_organizations
from .data_helpers import APILOCK
from pymongo import MongoClient
from django.conf import settings
from loguru import logger
import pymongo
import httpx
import xmltodict
from rich import print
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET 
import pickle 

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

client=MongoClient('mongodb://smops:bazending@192.168.2.153:27017/')
db=client['mus']
mongo_openaire_results = db['api_responses_openaire']
def addOpenAlexWorksFromMongo():
    datasets=[]
    openalex_works=db['api_responses_works_openalex']
    crossref_info=db['api_responses_crossref']
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
    pure_works=db['api_responses_pure']
    i=0
    k=0
    for document in pure_works.find().sort('date',pymongo.DESCENDING):
        datasets.append(document)
        i=i+1
        if i % 1000 == 0:
            message=f"processing batch of {len(datasets)} works"
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

def addItemsFromOpenAire():
    def get_openaire_token():
        print('getting new token')
        refreshurl=f'https://services.openaire.eu/uoa-user-management/api/users/getAccessToken?refreshToken={OPENAIRETOKEN}'
        tokendata = httpx.get(refreshurl)
        return tokendata.json()
        

    print('adding items from OpenAire')
    tokendata=get_openaire_token()
    time = datetime.now()
    url = 'https://api.openaire.eu/search/researchProducts'
    headers = {
        'Authorization': f'Bearer {tokendata.get("access_token")}'
    }

    paperlist = Paper.objects.filter(year__gte=2019).values('doi','openalex_url')
    for paper in paperlist:
        if mongo_openaire_results.find_one({'id':paper['openalex_url']}):
            print('item already in mongodb, skipping.')
            continue
        params = {'doi':paper['doi'].replace('https://doi.org/','')}
        try:
            r = httpx.get(url, params=params, headers=headers)
        except Exception as e:
            print('httpx error: ',e)
        try:
            metadata = xmltodict.parse(r.text, attr_prefix='',dict_constructor=dict,cdata_key='text', process_namespaces=True).get('response').get('results').get('result').get('metadata').get('http://namespace.openaire.eu/oaf:entity').get('http://namespace.openaire.eu/oaf:result')
        except Exception as e:
            print('error while trying to get metadata: ',e)
            continue

        metadata['id']=paper['openalex_url']
        mongo_openaire_results.insert_one(metadata)
        
        if datetime.now()-time > timedelta(minutes=58):
            tokendata=get_openaire_token()
            headers = {
                'Authorization': f'Bearer {tokendata.get("access_token")}'
            }
            time = datetime.now()


    return None
# needs new implementation
def addPaper(
    doi, recheck=False, viewpaper=False, user=None
):
    """
    Adds an article to the database using its DOI.

    Parameters:
        doi (str): The DOI of the article to be added.
        jb (bool): True if the journal browser should be scraped
        people (bool): True if the people page should be scraped

    Returns:
        bool: True if the article was successfully added, False otherwise.
    """
    return False
    status = False
    lookup = True
    action = f"No action for {doi}"
    result = {}
    logger.debug("addArticle [doi] %s ", doi)
    if doi != "":
        try:
            if doi[0:4] != "http":
                doi = "".join(["https://doi.org/", doi])
            elif doi[0:16] == "https://doi.org/":
                doi = doi

            action = f"No action for {doi}"

            if Paper.objects.filter(doi=doi).exists():
                if viewpaper:
                    if recheck:
                        with transaction.atomic():
                            Paper.objects.filter(doi=doi).delete()
                        lookup = True
                        logger.info(
                            "addPaper [status] re-adding [doi] %s ",
                            doi,
                        )
                    else:
                        status = True
                        lookup = False
                        if viewPaper.objects.filter(
                            displayed_paper=Paper.objects.get(doi=doi), user=user
                        ).exists():
                            logger.info(
                                "addPaper [status] skipping [reason] already marked [doi] %s ",
                                doi,
                            )
                            action = f"No action: {doi} already in DB & marked"
                        else:
                            with transaction.atomic():
                                paper = Paper.objects.get(doi=doi)
                                viewPaper.objects.create(
                                    displayed_paper=paper, user=user
                                )
                            logger.info(
                                "addPaper [status] marking [doi] %s ",
                                doi,
                            )
                            action = f"added {doi} to view"
                else:
                    if recheck:
                        with transaction.atomic():
                            Paper.objects.filter(doi=doi).delete()
                            lookup = True
                            logger.info(
                                "addPaper [status] re-adding [doi] %s ",
                                doi,
                            )
                    else:
                        logger.info(
                            "addPaper [status] skipping [reason] already in db [doi] %s ",
                            doi,
                        )

                        result["status"] = True
                        result["action"] = action
                        return result
            if lookup:
                try:
                    APILOCK.acquire()
                    work = Works()[doi]
                    try:
                        APILOCK.release()
                    except Exception:
                        pass
                    if Paper.objects.filter(doi=work["doi"]).exists() and not recheck:
                        logger.info(
                            "addPaper [status] skipping [reason] already in db [doi] %s ",
                            work["doi"],
                        )
                        status = True
                    else:
                        processPaperData(work)
                        logger.debug("processPaperData [status] done [doi] %s", doi)
                        paper = Paper.objects.filter(doi=work["doi"]).first()
                        relatedpureentries = PureEntry.objects.filter(
                            doi__iexact="doi",
                        ).all()
                        if relatedpureentries.exists():
                            with transaction.atomic():
                                paper.has_pure_oai_match = True
                                paper.save()
                                for pureentry in relatedpureentries:
                                    pureentry.paper = paper
                                    pureentry.save()

                        if viewpaper:
                            with transaction.atomic():
                                viewPaper.objects.create(
                                    displayed_paper=Paper.objects.filter(
                                        doi=work["doi"]
                                    ).first(),
                                    user=user,
                                )
                        status = True
                        if recheck:
                            action = f"{doi} deleted & readded to DB"
                        else:
                            action = f"{doi} added to DB"
                except Exception as error:
                    logger.error(
                        "addArticle [status] Error [doi] %s: %s",
                        error,
                        doi,
                    )
                    logger.exception("[stacktrace]")
                    try:
                        APILOCK.release()
                    except Exception:
                        pass

                    status = False
        except Exception:
            pass
    if not status:
        logger.error("addArticle [status] Failed [doi] %s ", doi)
        action = f"Error while trying to process {doi}"
    clean_duplicate_organizations()
    result["status"] = status
    result["action"] = action
    return result
