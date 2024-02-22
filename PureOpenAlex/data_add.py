import pyalex
from pyalex import Works
from .namematcher import NameMatcher
import logging
from .models import PureEntry,  Paper, viewPaper
from django.db import transaction
from .data_process import processPaperData
from .data_process_mongo import processMongoPaper
from .data_repair import clean_duplicate_organizations
from .data_helpers import APILOCK
from pymongo import MongoClient

from django.conf import settings
APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")
pyalex.config.email = APIEMAIL

"""
data_add.py description

This script contains the functions that handle adding new papers to the Django OpenAlex database from OpenAlex or Pure.

"""

SCORETHRESHOLD = 0.98  # for namematching authors on UT peoplepage
APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")
pyalex.config.email = APIEMAIL
name_matcher = NameMatcher()
logger = logging.getLogger(__name__)

client=MongoClient('mongodb://smops:bazending@192.168.2.153:27017/')
db=client['mus']

def addOpenAlexWorksFromMongo():
    '''
    for each document in collection 'api_responses_works_openalex':
    [1] Check if it is already in the SQL database:
    if ResearchOutput.objects.filter(openalex_url=document['id']).exists() == False:
    [2] if not,retrieve the full dict for this item from relevant collections
        and add them to dict 'dataset'
    [3] add dataset to list
    [B] For each item, call add_openalex_work(dataset)

    Example dataset contents:

    dataset = {
        'openalex_work':{
            'data':dict(mongodbdata),
            'source':dict(mongoDBitemdata)
        }
        'crossref_work':{
            'data':dict(mongodbdata),
            'source':dict(mongoDBitemdata)
        }
    }
    '''

    datasets=[]
    ignorelist={}

    openalex_works=db['api_responses_works_openalex']
    crossref_info=db['api_responses_crossref']
    i=0
    j=0
    h=0
    all_openalex_urls=set(Paper.objects.values_list('openalex_url',flat=True))
    for document in openalex_works.find():
        if document['id'] not in all_openalex_urls and document['id'] not in ignorelist.keys():
            crossrefdoc=None
            try:
                doi=document['doi'].replace('https://doi.org/','')
                crossrefdoc=crossref_info.find_one({'DOI':doi})
            except Exception:
                doi=None
            dataset={
                'openalex_work':{'data':document,'source':{'database':'mus','collection':'api_responses_works_openalex','mongo_id':str(document['_id'])}},
                'crossref_work':{} if crossrefdoc is None else {'data':crossrefdoc, 'source':{'database':'mus','collection':'api_responses_crossref','mongo_id':str(crossrefdoc['_id'])}},
            }
            datasets.append(dataset)
            i=i+1
            if i % 1000 == 0:
                message=f"{i} works currently in dataset"
        else:
            h=h+1
    message=f"processing {len(datasets)} new works, {h} already found in DB"
    added=[]
    k=0
    for dataset in datasets:
        j=j+1
        try:
            with transaction.atomic():
                id=dataset['openalex_work']['data']['id']
                processMongoPaper(dataset)
                added.append(id)
        except Exception:
            ignorelist[id]=True
        if len(added)>=100:
            k=k+len(added)
            message=f"{k} works added (+{len(added)})"
            logger.info(message)
            added=[]

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
