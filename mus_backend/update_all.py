from collections import defaultdict
from django.conf import settings
from loguru import logger
from PureOpenAlex.models import DBUpdate, Paper, Author, Journal, UTData, PureEntry, Location, DealData, viewPaper
from .get_from_api import getCrossrefWorks, getOpenAlexWorks, getOpenAlexAuthorData, getDataCiteItems, getPureItems, addItemsFromOpenAire
from .get_from_file import getfrompurereport, getdblp
from .get_from_scraper import fillJournalData, fillUTPeopleData
from PureOpenAlex.data_add import addOpenAlexWorksFromMongo, addPureWorksFromMongo, addOpenAireWorksFromMongo
from django.db.models import Q
from pymongo import DeleteOne,MongoClient
from pymongo.collection import Collection
from pymongo.errors import InvalidOperation
import datetime
import asyncio

MONGOURL = getattr(settings, "MONGOURL", None)
client = MongoClient(MONGOURL)
db = client['mus']



def clean_all():
    def clean_duplicates(coll: Collection):
        pipeline = [{'$group': {'_id': '$id', 'count': {'$sum': 1}, 'ids': {'$push': '$_id'}}},
        {'$match': {'count': {'$gte': 2}}}]
        requests = []
        documents = 0
        for document in coll.aggregate(pipeline):
            documents = documents + 1
            it = iter(document['ids'])
            next(it)
            for id in it:
                requests.append(DeleteOne({'_id': id}))
        coll.bulk_write(requests)
        return len(requests), documents

    logger.info('cleaning duplicates in mongo collection api_responses_authors_openalex')
    try:
        cleanedauthors, numauths = clean_duplicates(db['api_responses_authors_openalex'])
        logger.info(f'removed {cleanedauthors} duplicate entries for {numauths} authors')
    except InvalidOperation:
        logger.info('no duplicate entries found in mongo collection api_responses_authors_openalex')

    logger.info('cleaning duplicates in mongo collection api_responses_works_openalex')
    try:
        cleanedworks, numworks = clean_duplicates(db['api_responses_works_openalex'])
        logger.info(f'removed {cleanedworks} duplicate entries for {numworks} works')
    except InvalidOperation:
        logger.info('no duplicate entries found in mongo collection api_responses_works_openalex')

    logger.info('now running cleaning functions for models:')
    logger.info('paper.link_journals()')
    Paper.objects.link_journals()
    logger.info('pureentry.link_mongo_pure_reports()')
    PureEntry.objects.link_with_mongo_pure_reports()
    logger.info('pureentry.link_with_postgres_pure_reports()')
    PureEntry.objects.link_with_postgres_pure_reports()
    logger.info('pureentry.add_authors()')
    PureEntry.objects.add_authors()
    logger.info('author.fix_affiliations()')
    Author.objects.fix_affiliations()
    logger.info('author.fix_avatars()')
    Author.objects.fix_avatars()
    logger.info('pureentry.link_papers()')
    PureEntry.objects.link_papers()

def update_pure_items(years, processpapers):
    logger.info('running update_pure_items()')

    logger.info('running getPureItems()')
    addedfrompure = getPureItems(years)
    logger.info('done running getPureItems()')
    if addedfrompure:
        pureupdate = DBUpdate.objects.create(update_source="Pure", update_type="manualmongo", details = addedfrompure)
        pureupdate.save()
        if len(addedfrompure['ris_files'])>0 or len(addedfrompure['ris_pages'])>0:
            processpapers['pure'].extend({'ris_files':addedfrompure['ris_files'],'ris_pages':addedfrompure['ris_pages']})
            logger.info(f"{len(addedfrompure['ris_files'])} updated works retrieved from Pure OAI-PMH")
            addPureWorksFromMongo(addedfrompure)

    return processpapers
def update_works(years, processpapers):

    logger.info('running update_works()')
    logger.info('running getOpenAlexWorks()')
    result_oaworks = getOpenAlexWorks(years)
    logger.info('done running getOpenAlexWorks()')
    if result_oaworks:
        if len(result_oaworks['dois'])>0:
            processpapers['works'].extend(result_oaworks['dois'])
            logger.info(f'{len(result_oaworks["dois"])} updated works retrieved from OpenAlex')

    logger.info('running addItemsFromOpenAire()')
    addedfromopenaire = addItemsFromOpenAire()
    logger.info('done running addItemsFromOpenAire()')
    if addedfromopenaire:
        oaire=DBUpdate.objects.create(update_source="OpenAire", update_type="manualmongo", details=addedfromopenaire)
        oaire.save()
        if len(addedfromopenaire['dois'])>0:
            processpapers['openaire'].extend(addedfromopenaire['dois'])
            logger.info(f'{len(addedfromopenaire["dois"])} updated works retrieved from OpenAire')
    logger.info('running getCrossrefWorks()')
    addedfromcrossref = getCrossrefWorks(years)
    logger.info('done running getCrossrefWorks()')
    if addedfromcrossref:
        cr = DBUpdate.objects.create(update_source="Crossref", update_type="manualmongo", details=addedfromcrossref)
        cr.save()
        if len(addedfromcrossref['dois'])>0:
            processpapers['works'].extend(addedfromcrossref['dois'])
            logger.info(f'{len(addedfromcrossref["dois"])} updated works retrieved from Crossref')
    logger.info('running getDataCiteItems()')
    addedfromdatacite = getDataCiteItems(years)
    logger.info('done running getDataCiteItems()')
    if addedfromdatacite:
        dataciteupdate = DBUpdate.objects.create(update_source="DataCite", update_type="manualmongo", details = addedfromdatacite)
        dataciteupdate.save()
        logger.info(f'{len(addedfromdatacite["dois"])} updated works retrieved from DataCite')


    if len(processpapers['works'])>0:
        logger.info('running getOpenAlexAuthorData()')
        getOpenAlexAuthorData()
        logger.info('done running getOpenAlexAuthorData()')
        logger.info('running fillJournalData()')
        fillJournalData()
        logger.info('done running fillJournalData()')
        logger.info('now processing the retrieved data')
        addOpenAlexWorksFromMongo(processpapers['works'])
        logger.info('done processing the retrieved data')
        if addedfromopenaire:
            logger.info('running addOpenAireWorksFromMongo()')
            addOpenAireWorksFromMongo(processpapers['openaire'])
            logger.info('done running addOpenAireWorksFromMongo()')

    else:
        logger.info('no new OA works to process')

    return processpapers

def update_people_page_data():
    logger.info('running update_people_page_data()')
    logger.info('running fillUTPeopleData()')
    dbupdatepeoplepage = asyncio.run(fillUTPeopleData())
    if dbupdatepeoplepage:
        dbu=DBUpdate.objects.create(**dbupdatepeoplepage)
        dbu.save()
    logger.info('done running fillUTPeopleData()')

def update_all(clean=False, people=False, get_dbupdates=False):
    years=[2022,2023,2024,2025]
    processpapers=defaultdict(list)
    logger.info('running updateAll()')
    if get_dbupdates:
        logger.info('getting all works from dbupdates modified between now and 1 days ago')
        dbupdates = DBUpdate.objects.filter(Q(update_type="getOpenAlexWorks")&Q(modified__gte=datetime.datetime.now() - datetime.timedelta(days=1)))
        if dbupdates:
            logger.info(f'found {dbupdates.count()} dbupdates to process')
        for dbupdate in dbupdates:
            updatedata=dbupdate.details
            if len(updatedata['dois'])>0:
                processpapers['works'].extend(updatedata['dois'])
    processpapers = update_works(years, processpapers)
    processpapers = update_pure_items(years, processpapers)
    logger.info('done with updateAll()')


    if clean:
        logger.info('clean = True, running cleandb()')
        clean_all()
    if people:
        logger.info('people = True, running update_people_page_data()')
        update_people_page_data()
        logger.info('done running update_people_page_data()')