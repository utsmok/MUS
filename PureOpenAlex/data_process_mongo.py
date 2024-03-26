
from django.conf import settings
from .models import Location, Source, PilotPureData, DealData, UTData, Author, Paper,  Organization, Journal, viewPaper, PureEntry
from django.db import transaction
from django.db.models import Q
from nameparser import HumanName
from datetime import date
from dateutil.relativedelta import relativedelta
from pymongo import MongoClient
import pyalex
from .constants import TWENTENAMES

from .data_helpers import invertAbstract
from functools import wraps
import time
from loguru import logger
import re
from unidecode import unidecode
from collections import defaultdict
from rich import print
from django.core.exceptions import MultipleObjectsReturned



TAG_RE = re.compile(r'<[^>]+>')
FACULTIES = ['ITC', 'EEMCS', 'ET', 'TNW', 'BMS', 'Science and Technology Faculty', 'Behavioural, Management and Social Sciences', 'Engineering Technology', 'Geo-Information Science and Earth Observation', 'Electrical Engineering, Mathematics and Computer Science']
OA_WORK_COLUMNS = ['_id','id','doi','title','display_name','publication_year','publication_date','ids','language','primary_location','type','type_crossref','indexed_in','open_access','authorships','countries_distinct_count','institutions_distinct_count','corresponding_author_ids','corresponding_institution_ids','apc_list','apc_paid','has_fulltext','fulltext_origin','cited_by_count','cited_by_percentile_year','biblio','is_retracted','is_paratext','keywords','concepts','mesh','locations_count','locations','best_oa_location','sustainable_development_goals','grants','referenced_works_count','referenced_works','related_works','ngrams_url','abstract_inverted_index','cited_by_api_url','counts_by_year','updated_date','created_date','topics','primary_topic']
CR_WORK_COLUMNS = ['_id','indexed','reference-count','publisher','content-domain','published-print','abstract','DOI','type','created','page','source','is-referenced-by-count','title','prefix','author','member','container-title','link','deposited','score','resource','subtitle','issued','references-count','URL','published','issue','volume','journal-issue','ISSN','issn-type','subject','short-container-title','language','isbn-type','ISBN']
TAGLIST = ["UT-Hybrid-D", "UT-Hybrid-D", "UT-Gold-D", "NLA", "N/A OA procedure"]
LICENSESOA = [
    "cc-by-sa",
    "cc-by-nc-sa",
    "publisher-specific-oa",
    "cc-by-nc-nd",
    "cc-by-nc",
    "cc0",
    "cc-by",
    "public-domain",
    "cc-by-nd",
    "pd",
]
OTHERLICENSES = [
    "publisher-specific,authormanuscript",
    "unspecified-oa",
    "implied-oa",
    "elsevier-specific",
]
TCSGROUPS = [
    "Design and Analysis of Communication Systems",
    "Formal Methods and Tools",
    "Computer Architecture Design and Test for Embedded Systems",
    "Pervasive Systems",
    "Datamanagement & Biometrics",
    "Semantics",
    "Human Media Interaction",
]
MONGOURL = getattr(settings, "MONGOURL")
APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")
pyalex.config.email = APIEMAIL

client=MongoClient(MONGOURL)
db=client['mus']
mongo_dealdata=db['api_responses_journals_dealdata_scraped']
mongo_oa_authors=db['api_responses_authors_openalex']
mongo_orcid=db['api_responses_orcid']
mongo_oa_ut_authors=db['api_responses_UT_authors_openalex']
mongo_peoplepage=db['api_responses_UT_authors_peoplepage']
mongo_oa_journals = db['api_responses_journals_openalex']
mongo_openaire_works = db['api_responses_openaire']

def timeit(func):
    @wraps(func)
    def timeit_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        total_time = end_time - start_time
        logger.debug('Function {name} took {time} seconds', name=func.__name__, time=f'{total_time:.1f}')
        return result
    return timeit_wrapper



@timeit
def processMongoPaper(dataset, user=None, update=False):
    '''
    Input: dataset with openalex & crossref work data
    Processes the input to create a Paper object in the db including all related other objects

    order of operations:
    prep_openalex_data
    prep_crossref_data
    merge crossref dates into openalex data
    get license data
    make paper object
    retrieve and/or create:
        - authorships
            - authors
                - utdata
                - affiliations
                    -organizations
        - locations
            - sources
                |
            one of which can be a:
                |
                journal
                    - dealdata
    add authorships, locations, journal to paper
    calculate/determine:
        - taverne date
        - ut keyword suggestion
        - is_in_pure
        - has_pure_oai_match

    finally, if user is not None, add viewPaper(paper, user)
    '''
    def prep_openalex_data(data):
        cleandata = {
            'paper':{
                'openalex_url':data.get('id'),
                'title':data.get('title') if data.get('title') else "",
                'doi':data.get('doi') if data.get('doi') else "",
                'year':data.get('publication_year'),
                'citations':int(data.get('cited_by_count')) if data.get('cited_by_count') else 0,
                'openaccess':data.get('open_access').get('oa_status'),
                'is_oa':data.get('open_access').get('is_oa') ,
                'primary_link':data.get('primary_location').get('landing_page_url') if data.get('primary_location').get('landing_page_url') else "",
                'pdf_link_primary':data.get('primary_location').get('pdf_url') if data.get('primary_location').get('pdf_url') else "",
                'itemtype':data.get('type_crossref') if data.get('type_crossref') else "",
                'date':data.get('publication_date') if data.get('publication_date') else "",
                'language':data.get('language',"") if data.get('language') else "",
                'abstract':invertAbstract(data.get('abstract_inverted_index')),
                'volume': data.get('biblio').get('volume') if data.get('biblio').get('volume') else "",
                'issue': data.get('biblio').get('issue') if data.get('biblio').get('issue') else "",
                'keywords':data.get('keywords', []),
                'topics':data.get('topics'),
            },
            'authorships':data.get('authorships'),
            'pages':{
                'first': data.get('biblio').get('first_page'),
                'last': data.get('biblio').get('last_page')
                },
            'primary_location':data.get('primary_location'),
            'best_oa_location':data.get('best_oa_location'),
            'full': data
        }
        if data.get('apc_list'):
            cleandata['paper'].update({'apc_listed_value':data.get('apc_list').get('value'),
            'apc_listed_currency':data.get('apc_list').get('currency'),
            'apc_listed_value_usd':data.get('apc_list').get('value_usd'),
            #'apc_listed_value_eur': convertToEuro(data.get('apc_list').get('value'), data.get('apc_list').get('currency'), date.fromisoformat(data.get('publication_date'))) if data.get('apc_list').get('currency') != 'EUR' else data.get('apc_list').get('value'),
            'apc_listed_value_eur': 0,
            })
        if data.get('apc_paid'):
            cleandata['paper'].update({
            'apc_paid_value':data.get('apc_paid').get('value'),
            'apc_paid_currency':data.get('apc_paid').get('currency'),
            'apc_paid_value_usd':data.get('apc_paid').get('value_usd'),
            #'apc_paid_value_eur': convertToEuro(data.get('apc_paid').get('value'), data.get('apc_paid').get('currency'), date.fromisoformat(data.get('publication_date'))) if data.get('apc_paid').get('currency') != 'EUR' else data.get('apc_paid').get('value'),
            'apc_paid_value_eur': 0,
            })
        return cleandata

    def prep_crossref_data(data):
        if data:

            published = None
            published_online = None
            published_print = None
            issued = None
            datetypekey={
                'published':published,
                'published_online':published_online,
                'published_print':published_print,
                'issued':issued
            }
            for datetype in ['published','published_online','published_print','issued']:
                try:
                    if data.get(datetype):
                        if data.get(datetype).get('date-parts'):
                            if len(data.get(datetype).get('date-parts')[0])==1:
                                year=data.get(datetype).get('date-parts')[0][0]
                                datetypekey[datetype]=date.fromisoformat(f"{year}-01-01")
                            elif len(data.get(datetype).get('date-parts')[0])==3:
                                datetypekey[datetype] = date.fromisoformat("-".join([f"{i:02}" for i in data.get('published')['date-parts'][0]]))
                except Exception:
                    pass
            return {
                'dates': {
                    'published':datetypekey['published'] ,
                    'published_online':datetypekey['published_online'],
                    'published_print':datetypekey['published_print'],
                    'issued':datetypekey['issued'],
                },
                'relation':data.get('relation'),
                'page':data.get('page'),
                'full':data
            }
        else:
            return {}

    def get_license_data(data):
        value=None
        data=data.get('full')
        if data.get('primary_location'):
            value = data.get('primary_location').get('license')
        else:
            if data.get('locations'):
                for loc in data.get('locations'):
                    if loc.get('license'):
                        value = loc.get('license')
        return value if value else ''
    def calc_taverne_date(oa_work, cr_work):
        dates={}
        dates=[date.fromisoformat(oa_work['date'])]
        try:
            if cr_work.get('dates'):
                dates.append([value for value in cr_work.get('dates').values()])
                return min(dates)+relativedelta(months=+6)
            else:
                return dates[0]+relativedelta(months=+6)
        except Exception as e:
            logger.error('error in calc_taverne_date: {}',e)
            return None
    def get_pages_count(oa_work, cr_work):

        first_page = oa_work.get('pages').get('first')
        last_page = oa_work.get('pages').get('last')
        pages=''
        pagescount = None
        if cr_work:
            if cr_work.get('page') and cr_work.get('page') != '':
                pages=cr_work.get('page')
                logger.debug("got pages from crossref: {pages}", pages=pages)
        elif first_page and last_page:
            pages=f'{first_page}-{last_page}'
            logger.debug("first and last page from OA, so using fp-lp: {pages}", pages=pages)
        elif first_page:
            pages=first_page
        else:
            pages=''
        if first_page and last_page:
            try:
                pagescount = int(re.findall(r"\d+", last_page)[0]) - int(re.findall(r"\d+", first_page)[0]) + 1
            except Exception:
                pagescount = None
            logger.debug(' using lastpage - firstpage for pagecount: {pagescount}', pagescount=pagescount)
        else:
            pagescount = None
        if not pages:
            pages = ''
        logger.debug("pages: {pages}, pagescount: {pagescount}", pages=pages, pagescount=pagescount)
        return pagescount, pages


    #def calc_ut_keyword_suggestion(oa_work, cr_work):
    #    return None
    paper=None
    logger.info("adding new paper from mongodata with doi {doi}", doi=dataset['works_openalex']['doi'])
    if Paper.objects.filter(doi=dataset['works_openalex']['doi']).exists():
        if update:
            logger.warning("paper already exists; updating")
            try:
                paper=Paper.objects.get(doi=dataset['works_openalex']['doi'])
            except MultipleObjectsReturned:
                paperset = Paper.objects.filter(doi=dataset['works_openalex']['doi']).order_by('id')
                len = paperset.count()
                i = 0
                for paperentry in paperset:
                    if i < len:
                        paperentry.delete()
                        i = i + 1
                    else:
                        paper = paperentry
        else:
            logger.error("paper already exists, aborting. matching itemid: {id}",id=Paper.objects.get(doi=dataset['works_openalex']['doi']).id)
            raise Exception('paper already exists, arg update==False')

    oa_work = prep_openalex_data(dataset['works_openalex'])
    if dataset.get('crossref'):
        cr_work = prep_crossref_data(dataset['crossref'])
    else:
        cr_work = {}
    oa_work['paper'].update(cr_work.get('dates', {}))
    oa_work['paper']['license'] = get_license_data(oa_work)
    oa_work['paper']['pagescount'], oa_work['paper']['pages'] = get_pages_count(oa_work, cr_work)

    if paper:
        id = paper.id
        Paper.objects.filter(id=id).update(**oa_work['paper'])
        logger.info(f"paper {paper.id} updated")

    else:
        with transaction.atomic():
            paper, created = Paper.objects.update_or_create(**oa_work['paper'])
            if created:
                paper.save()
            logger.info("paper created with id {id} ", id=paper.id)
    
    with transaction.atomic():
        paper = add_authorships(oa_work['full'],paper)
    with transaction.atomic():
        paper = add_locations(oa_work['full'],paper)

    paper.taverne_date=calc_taverne_date(oa_work['paper'], cr_work.get('dates', {}))
    #paper.ut_keyword_suggestion=calc_ut_keyword_suggestion(oa_work, cr_work)
    #paper.is_in_pure = determine_is_in_pure(oa_work['paper'])
    view = None
    if user:
        with transaction.atomic():
            view, created = viewPaper.objects.update_or_create(user=user, displayed_paper=paper)
            if created:
                view.save()
    logger.info("fully processed paper with doi {doi}", doi=paper.doi)
    return paper, view
def add_authorships(data, paper):

    def getorgs(affils, is_ut):
        affiliations=[]
        for org in affils:
            # get affiliation info into a list of dicts, check for is_ut along the way
            if not org:
                continue
            if org.get('institution'):
                orgsrc = org.get('institution')
            else:
                orgsrc = org

            orgdata = {
                'name':orgsrc.get('display_name'),
                'openalex_url':orgsrc.get('id'),
                'ror':orgsrc.get('ror') if orgsrc.get('ror') else '',
                'type':orgsrc.get('type'),
                'country_code':orgsrc.get('country_code') if orgsrc.get('country_code') else '',
                'data_source':'openalex'
            }
            if not is_ut:
                if orgdata['ror'] == 'https://ror.org/006hf6230':
                    is_ut=True
                elif orgdata['name'] in TWENTENAMES:
                    is_ut=True
            if org.get('years'):
                years = org.get('years')
            else:
                years = []
            try:
                if Organization.objects.filter(Q(ror=orgdata['ror']) & Q(name=orgdata['name']) & Q(openalex_url=orgdata['openalex_url'])).exists():
                    found_org  = Organization.objects.filter(Q(ror=orgdata['ror']) & Q(name=orgdata['name']) & Q(openalex_url=orgdata['openalex_url'])).first()
                    if found_org.type != orgdata['type'] or found_org.country_code != orgdata['country_code']:
                        #for now, assumed that the new data is better... might be a bad assumption
                        if orgdata['type'] and orgdata['type'] != '':
                            found_org.type = orgdata['type']
                        if orgdata['country_code'] and orgdata['country_code'] != '':
                            found_org.country_code = orgdata['country_code']
                        found_org.save()
                    org = found_org

                if not isinstance(org, Organization):
                    org, created = Organization.objects.update_or_create(**orgdata)
                    if created:
                        org.save()
            except Exception:
                continue
            affiliations.append([org, years])
        return affiliations
    def makefullauthor(author, authorship):
        # author doesn't exist yet, make new one
        is_ut=False
        affiliations=[]

        # First check if the author was found as UT author in OpenAlex; if so, get that detailed data
        oa_ut_authordata = mongo_oa_ut_authors.find_one({"id":author.get('id')})

        if oa_ut_authordata:
            is_ut = True
            authordata = oa_ut_authordata
            affils = oa_ut_authordata.get('affiliations')
        else:
            # else try to get detailed data from the other mongo_db
            oa_authordata = mongo_oa_authors.find_one({"id":author.get('id')})
            if oa_authordata:
                authordata = oa_authordata
                affils = oa_authordata.get('affiliations')
            else:
                # if that fails use the data from work->authorships
                authordata = author
                affils = authorship.get('institutions')

            if affils and affils != [] and affils != {} and affils is not None:
                affiliations = getorgs(affils, is_ut)

        # process author data
        hname = HumanName(authordata.get('display_name'))
        authordict = {
                'name': authordata.get('display_name'),
                'orcid': authordata.get('orcid'),
                'openalex_url': authordata.get('id'),
                'first_name': hname.first,
                'last_name': hname.last,
                'middle_name': hname.middle,
                'initials': hname.initials(),
                'is_ut': is_ut
            }
        if authordata.get('ids') or authordata.get('display_name_alternatives'):
            authordict.update({
                'scopus_id':authordata.get('ids').get('scopus'),
                'known_as': authordata.get('display_name_alternatives')
                })

        authorobject, created = Author.objects.update_or_create(**authordict)
        if created:
            authorobject.save()
            ut_author_year_match = False
        else:
            ut_author_year_match = authorobject.ut_author_year_match

        for aff in affiliations:
            authorobject.affils.add(aff[0],through_defaults={'years':aff[1]})
            if not ut_author_year_match:
                if 'twente' in aff[0].name.lower():
                    if paper.year in aff[1]:
                        ut_author_year_match = True
        return authorobject, ut_author_year_match
    def add_peoplepagedata(author, authorobject):
        peoplepage_data = mongo_peoplepage.find_one({"id":author.get('id')})
        if peoplepage_data:
            utdata = {
                'avatar': peoplepage_data.get('avatar_url'),
                'current_position': peoplepage_data.get('position'),
                'current_group': peoplepage_data.get('grouplist')[0].get('group'),
                'current_faculty': peoplepage_data.get('grouplist')[0].get('faculty'),
                'employee': authorobject,
                'email': peoplepage_data.get('email'),
                'employment_data': peoplepage_data.get('grouplist'),
                'avatar_path': peoplepage_data.get('avatar_url').replace('https://people.utwente.nl/','author_avatars/').replace('/picture',''),
            }
            ut, created = UTData.objects.update_or_create(**utdata)
            if created:
                ut.save()
            authorobject.is_ut = True
            authorobject.save()
        else:
            logger.warning("no ut data for ut author found, oa id: {id} ", id=author.get('id'))
    authorships = data.get('authorships')
    for authorship in authorships:
        author = authorship.get('author')
        ut_author_year_match = False
        if Author.objects.filter(openalex_url=author.get('id')).exists():
            authorobject = Author.objects.filter(openalex_url=author.get('id')).get()
        else:
            authorobject, ut_author_year_match = makefullauthor(author, authorship)
        
        if not ut_author_year_match:
            for affil in authorobject.affiliations.all():
                if 'twente' in affil.organization.name.lower():
                    if paper.year in affil.years:
                        ut_author_year_match = True
                        break

        authorshipdict = {
                    'paper':paper,
                    'position':authorship.get('author_position'),
                    'corresponding':authorship.get('is_corresponding'),
                    'ut_author_year_match':ut_author_year_match
                }
        paper.authors.add(authorobject, through_defaults={'position':authorshipdict.get('position'), 'corresponding':authorshipdict.get('corresponding')})

        if authorobject.is_ut:
            add_peoplepagedata(author, authorobject)

    return paper
def add_locations(data, paper):
    def get_deal_data(openalex_id):
        dealdatacontents = mongo_dealdata.find_one({"id":openalex_id})
        if dealdatacontents:
            dealdata = {
                'deal_status':dealdatacontents.get('APCDeal'),
                'publisher': dealdatacontents.get('publisher'),
                'jb_url': dealdatacontents.get('journal_browser_url'),
                'oa_type': dealdatacontents.get('oa_type'),
            }
            return dealdata, dealdatacontents.get('keywords'), dealdatacontents.get('publisher')
        else:
            return None, None, None
        
    
    primary_location = ""
    best_oa_location = ""
    if data.get('primary_location'):
        primary_location = data.get('primary_location').get('landing_page_url')
        if not primary_location:
            primary_location = data.get('primary_location').get('pdf_url')
    if data.get('best_oa_location'):
        best_oa_location = data.get('best_oa_location').get('landing_page_url')
        if not best_oa_location:
            best_oa_location = data.get('best_oa_location').get('pdf_url')
    for location in data['locations']:
        if location['source']:
            try:
                source, sourcedict = get_source(location['source'])
            except Exception as e:
                logger.warning(f'exception {e} while trying to add source')
                source = None
                sourcedict={}
        else:
            is_twente = False
            if location.get('landing_page_url'):
                if 'twente' in location.get('landing_page_url'):
                    is_twente = True
            if location.get('pdf_url'):
                if 'twente' in location.get('pdf_url'):
                    is_twente = True
            if is_twente:
                source = Source.objects.filter(openalex_url='https://openalex.org/P4363603077').first()
                if source:
                    sourcedict = None
                else:
                    raise Exception("UTWente RIS source not found in DB?")
                paper.is_in_pure = True
                paper.save()
            else:
                source = None
                sourcedict = None

        if location.get('landing_page_url') == primary_location or location.get('pdf_url') == primary_location:
            is_primary=True
        else:
            is_primary=False
        if location.get('landing_page_url') == best_oa_location or location.get('pdf_url') == best_oa_location:
            is_best_oa=True
        else:
            is_best_oa=False

        cleandata={
            'is_oa':location.get('is_oa'),
            'is_accepted':location.get('is_accepted'),
            'is_published':location.get('is_published'),
            'license':location.get('license') if location.get('license') else '',
            'landing_page_url':location.get('landing_page_url') if location.get('landing_page_url') else '',
            'pdf_url':location.get('pdf_url') if location.get('pdf_url') else '',
            'is_primary':is_primary,
            'is_best_oa':is_best_oa,
            'source':source
        }
        location, created = Location.objects.update_or_create(**cleandata)
        if created:
            location.save()

        paper.locations.add(location)

        if sourcedict:
            if any([sourcedict.get('type') == 'journal', is_primary, len(data['locations'])==1]):
                journaldata=sourcedict
                journaldata['name']=sourcedict.get('display_name')
                del journaldata['display_name']
                if 'homepage_url' in journaldata:
                    del journaldata['homepage_url']
                dealdata, keywords, publisher = get_deal_data(journaldata['openalex_url'])
                journaldata['keywords']=keywords
                journaldata['publisher']=publisher if publisher else ""
                journal, created = Journal.objects.update_or_create(**journaldata)
                if created:
                    journal.save()
                if dealdata and not journal.dealdata:
                    deal, created = DealData.objects.update_or_create(**dealdata)
                    if created:
                        deal.save()
                    journal.dealdata=deal
                    journal.save()
                paper.journal=journal
                paper.save()

    return paper
def get_source(data):
    issn=data.get('issn_l')
    issnlist=data.get('issn')
    eissn=""
    if isinstance(issnlist, list):
        for nissn in issnlist:
            if nissn != issn:
                eissn = nissn
                break
    host_org = data.get('host_organization_lineage_names','')
    if isinstance(host_org, list) and len(host_org) > 0:
        host_org = host_org[0]

    publisher = ''
    split = str(data.get('host_organization')).split('.org/')
    if len(split) > 1:
        if split[1].startswith('P'):
            publisher = data.get('host_organization_name')

    sourcedict = {
        'openalex_url':data.get('id'),
        'display_name':data.get('display_name'),
        'host_org':host_org,
        'type':data.get('type'),
        'is_in_doaj':data.get('is_in_doaj'),
        'e_issn':eissn,
        'issn':issn,
        'homepage_url':'',
    }
    extradata = mongo_oa_journals.find_one({'id':data.get('id')})
    if extradata:
        sourcedict['homepage_url']=extradata.get('homepage_url')
    if not sourcedict.get('homepage_url'):
        sourcedict['homepage_url']=''

    source, created = Source.objects.update_or_create(**sourcedict)
    if created:
        source.save()
    sourcedict['publisher']=publisher
    sourcedict['is_oa']=data.get('is_oa')
    return source, sourcedict
def determine_is_in_pure(data):
    locs = data.get('locations')
    twentecheckstrs={'twente','ris.utwente.nl','research.utwente.nl'}
    if locs:
        for loc in locs:
            if twentecheckstrs in str(loc.get('landing_page_url')).lower() or twentecheckstrs in str(loc.get('pdf_url')).lower():
                return True
    return False

def processMongoPureEntry(puredata):
    logger.debug("creating pureentry for title {}", puredata.get('title'))
    if isinstance(puredata.get('date'),list):
        puredata['date'] = puredata.get('date')[0]
    pureentrydict = {
        'title': puredata.get('title', ''),
        'language': puredata.get('language', ''),
        'itemtype': puredata.get('type', ''),
        'format': puredata.get('format', ''),
        'abstract': TAG_RE.sub('', puredata.get('description', '')),
        'date': puredata.get('date', ''),
        'year': puredata.get('date', '')[0:4] if puredata.get('date') else '',
        'source': puredata.get('source', ''),
        'publisher': puredata.get('publisher', ''),
        'rights': puredata.get('rights', ''),
        'keywords': puredata.get('subject').get('subjects','') if puredata.get('subject') else '',
        'ut_keyword': puredata.get('subject').get('ut_keywords', '') if puredata.get('subject') else '',
    }
    pureentry, created = PureEntry.objects.update_or_create(**pureentrydict)
    if created:
        pureentry.save()

    pureentry = add_pureentry_journal(puredata.get('isPartOf',None), pureentry)
    pureentry = add_pureentry_authors(puredata, pureentry)
    pureentry = add_pureentry_ids(puredata.get('identifier', None), pureentry)
    pureentry = match_paper(pureentry)
    logger.debug("pureentry {entryid} created for title {title}", title=puredata.get('title'), entryid=pureentry.id)
    
def add_pureentry_journal(ispartof, pureentry):
    if not ispartof:
        return pureentry

    issn = str(ispartof.split(':')[-1])
    journal = Journal.objects.filter(Q(issn=issn) | Q(e_issn=issn)).first()
    if journal:
        with transaction.atomic():
            pureentry.journal = journal
            pureentry.save()
            logger.debug("pureentry {entryid} matched journal {issn}", entryid=pureentry.id, issn=issn)
    return pureentry
def add_pureentry_authors(puredata, pureentry):
    creators = puredata.get('creator')
    contributors = puredata.get('contributor')
    fullist = []
    if isinstance(creators, str):
        fullist.append(creators)
    if isinstance(contributors, str):
        fullist.append(contributors)
    if isinstance(creators, list):
        for creator in creators:
            fullist.append(creator)
    if isinstance(contributors, list):
        for contributor in contributors:
            fullist.append(contributor)
    if len(fullist) > 0:
        pureentry, nomatchcount = find_author_match(fullist, pureentry)
        if nomatchcount == len(fullist):
            logger.debug("No author matches found for pureentry {entryid}", entryid=pureentry.id)
    else:
        logger.warning("No authors found at all for pureentry {entryid}", entryid=pureentry.id)
    return pureentry
def find_author_match(pureauthors, pureentry):
    purenames={}
    purefullnames = {}
    pureinitials = {}
    authorlist=[]
    i=0

    for author in pureauthors:
        if not author:
            continue
        hname=HumanName(unidecode(author),initials_format="{first} {middle}")
        purenames[i] = {
            'full': hname.full_name,
            'initials': hname.initials(),
            'last': hname.last
        }
        purefullnames[hname.full_name]=i
        pureinitials[hname.initials()+" "+hname.last]=i

    for key, value in purenames.items():
        if Author.objects.filter(name__icontains=value['full']).exists():
            authorlist.append(Author.objects.filter(name__icontains=value['full']).first())
        elif Author.objects.filter(Q(initials__icontains=value['initials']) & Q(last_name__icontains=value['last'])).exists():
            authorlist.append(Author.objects.filter(Q(initials__icontains=value['initials']) & Q(last_name__icontains=value['last'])).first())

    if authorlist:
        for author in authorlist:
            pureentry.authors.add(author)
        pureentry.save()

    return pureentry, len(pureauthors)-len(authorlist)
def add_pureentry_ids(ids, pureentry):
    if not ids:
        return pureentry
    duplicate_ids = defaultdict(list)
    for idtype, value in ids.items():
        if idtype == 'doi':
            idtype='doi'
        elif idtype == 'ris_page':
            idtype='researchutwente'
        elif idtype == 'ris_file':
            idtype='risutwente'
        elif idtype == 'scopus_link':
            idtype='scopus'
        elif idtype == 'ISBN':
            idtype='isbn'
        else:
            idtype='other_links'

        if isinstance(value, str):
            if ':' in value and 'http' not in value:
                value = value.split(':')[-1]
            pureentry.__setattr__(idtype, value)
        if isinstance(value, list):
            if ':' in value and 'http' not in value[0]:
                value[0] = value[0].split(':')[-1]
            pureentry.__setattr__(idtype, value[0])
            for dupeid in value[1:]:
                if ':' in dupeid and 'http' not in dupeid:
                    dupeid = dupeid.split(':')[-1]
                duplicate_ids[idtype].append(dupeid)
    if len(duplicate_ids.keys()) > 0:
        pureentry.__setattr__('duplicate_ids', duplicate_ids)
    pureentry.save()
    return pureentry
def match_paper(pureentry):
    paper = None
    if pureentry.doi:
        paper = Paper.objects.filter(doi=pureentry.doi).first()
    if not paper:
        if pureentry.duplicate_ids:
            if 'doi' in pureentry.duplicate_ids:
                for doi in pureentry.duplicate_ids['doi']:
                    paper = Paper.objects.filter(doi=doi).first()
                    if paper:
                        break
    if not paper:
        paper = Paper.objects.filter(Q(title=pureentry.title)).first()
    if paper:
        pureentry.paper = paper
        pureentry.save()
        with transaction.atomic():
            paper.has_pure_oai_match = True
            paper.save()
        logger.debug("matching paper found for pureentry {entryid}", entryid=pureentry.id)
    return pureentry
def processMongoPureReportEntry(entrydata):
    UTKEYWORD=["UT-Hybrid-D", "UT-Gold-D", "NLA", "N/A OA procedure", "n/a OA procedure"]

    entry = None
    entrydict = {
        'pureid': entrydata.get('pureid'),
        'title': entrydata.get('title'),
        'doi': entrydata.get('dois',''),
        'orgs': entrydata.get('orgs'),
        'all_authors': entrydata.get('all_authors'),
        'ut_authors': entrydata.get('ut_authors'),
        'other_links': entrydata.get('other_links',''),
        'apc_paid_amount': entrydata.get('apc_paid_amount') if isinstance(entrydata.get('apc_paid_amount'), float) or isinstance(entrydata.get('apc_paid_amount'), int) else None,
        'file_names': entrydata.get('file_names',[]),
        'article_number': entrydata.get('article_number',''),
        'item_type': entrydata.get('item_type'),
        'year': entrydata.get('year'),
        'open_access': entrydata.get('open_access'),
        'keywords': entrydata.get('keywords',[]),
        'import_source': entrydata.get('import_source',''),
        'journal_title': entrydata.get('journal_title',''),
        'issn': entrydata.get('issn',''),
        'is_doaj': entrydata.get('is_doaj',False) if isinstance(entrydata.get('is_doaj'), bool) else False,
        'publisher_journal': entrydata.get('publisher_journal',''),
        "pure_entry_created" :entrydata.get('pure_entry_dates').get('date_created'),
        "pure_entry_last_modified":entrydata.get('pure_entry_dates').get('last_modified'),
        "date_earliest_published":entrydata.get('publication_dates').get('date_earliest_published') if entrydata.get('publication_dates') else None,
        "date_published":entrydata.get('publication_dates').get('date_published') if entrydata.get('publication_dates') else None,
        "date_eprint_first_online":entrydata.get('publication_dates').get('date_first_online') if entrydata.get('publication_dates') else None,
        "event":entrydata.get('event',''),
        'publisher_other':entrydata.get('publisher_other',''),
        'ut_keyword':'',
        'pages':entrydata.get('pages',''),
        'pagescount':entrydata.get('pagescount',None) if isinstance(entrydata.get('pagescount'), int) else None,
    }
    if entrydata.get('keywords'):
        if isinstance(entrydata.get('keywords'), list):
            for keyword in entrydata.get('keywords'):
                if 'UT-' in keyword or 'OA procedure' in keyword or keyword in UTKEYWORD:
                    entrydict['ut_keyword'] = keyword
        elif isinstance(entrydata.get('keywords'), str):
            keyword = entrydata.get('keywords')
            if 'UT-' in keyword or 'OA procedure' in keyword or keyword in UTKEYWORD:
                entrydict['ut_keyword'] = entrydata.get('keywords')

    entry = PilotPureData.objects.create(**entrydict)
    if entrydata.get('pure_entry_id') and entry:
        pureentry = PureEntry.objects.filter(pureid=entrydata.get('pure_entry_id')).first().pilot_pure_data = entry
        pureentry.save()
    return entry

@transaction.atomic
def processMongoOpenAireEntry(openairedata):
    logger.debug(f'processing openaire data for {openairedata["id"]}')
    paper = Paper.objects.get(openalex_url=openairedata['id'])
    updated=False
    if not paper:
        return None

    try:
        oa_journaldata =openairedata.get('journal')
    except Exception:
        oa_journaldata = None
    if oa_journaldata:
        if isinstance(oa_journaldata, dict):
            oa_issn = oa_journaldata.get('issn')
            oa_title = oa_journaldata.get('text')
            startpage = oa_journaldata.get('sp')
            endpage = oa_journaldata.get('ep')
            try:
                oa_publisher = openairedata.get('publisher')
            except Exception:
                oa_publisher = None

            if not paper.journal:
                logger.debug('paper does not have journal')
                if any([Journal.objects.filter(issn=oa_issn).exists(), Journal.objects.filter(e_issn=oa_issn).exists(), Journal.objects.filter(name=oa_title).exists()]):
                    logger.debug('journal found in db, adding to paper')
                    journals = Journal.objects.filter(Q(issn=oa_issn) | Q(e_issn=oa_issn) | Q(name=oa_issn))
                    logger.debug('openaire journal name:', oa_title)
                    for journal in journals:
                        if journal.name.lower() == oa_title.lower():
                            paper.journal = journal
                            with transaction.atomic():
                                paper.save()
                                updated=True
                else:
                    logger.debug('journal not found in db. Could be created. Skipping for now.')
            if paper.journal:
                if paper.journal.publisher and oa_publisher:
                    if paper.journal.publisher.lower() != oa_publisher.lower():
                        if oa_publisher is not None and oa_publisher != '':
                            logger.debug(f'updating journal publisher from {paper.journal.publisher} to {openairedata.get("publisher")}')
                            paper.journal.publisher = oa_publisher
                            with transaction.atomic():
                                paper.journal.save()
                                updated=True
            if (not paper.pages or not paper.pagescount) or (paper.pages=="" or paper.pagescount==0):
                if startpage and endpage:
                    if startpage.isdigit() and endpage.isdigit():
                        logger.debug('pageinfo found in openaire, adding to paper')
                        paper.pages = startpage+'-'+endpage
                        paper.pagescount = int(endpage)-int(startpage)+1
                        with transaction.atomic():
                            paper.save()
                            updated=True
                if startpage and not endpage:
                    if startpage.isdigit():
                        logger.debug('only startpage found, adding as articlenumber')
                        paper.pages = startpage
                        paper.pagescount = 1
                        with transaction.atomic():
                            paper.save()
                            updated=True
    if not paper.has_pure_oai_match:
        try:
            oa_instance = openairedata.get('children').get('instance')
        except Exception:
            pass
        if oa_instance:
            if isinstance(oa_instance, list):
                for result in oa_instance:
                    try:
                        link = result.get('fulltext')
                        if link:
                            blink = link
                            link = link.lower()
                        else:
                            continue
                    except Exception:
                        continue
                    logger.debug('checking link:', link)
                    if 'utwente' in link:
                        logger.debug('found utwente pure link, marking as matched')
                        paper.has_pure_oai_match = True
                        paper.save()
                        updated=True
                        if 'ris.utwente.nl' in link or 'research.utwente.nl' in link:
                            pureentry=PureEntry.objects.filter(Q(risutwente=link)|Q(researchutwente=link)|Q(risutwente=blink)|Q(researchutwente=blink))
                            if pureentry.exists():
                                    print('found matching pure entry in db, linking')
                                    for entry in pureentry:
                                        entry.paper = paper
                                        with transaction.atomic():
                                            entry.save()
                                            updated=True
                                            break
                            else:
                                logger.debug("no matching pure item in database... maybe add it? How could it have been missed?")
                        else:
                            logger.debug('link to ut ris not found in openaire data... ?')



    return updated