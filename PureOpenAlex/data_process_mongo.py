
from django.conf import settings
from .models import Location, Source, DealData, UTData, Author, Paper,  Organization, Journal, viewPaper
from django.db import transaction
from django.db.models import Q
from nameparser import HumanName
from datetime import date
from dateutil.relativedelta import relativedelta
from pymongo import MongoClient
import logging
import pyalex
from rich import print
from typing import TypeVar
from .data_helpers import (
    convertToEuro,
    invertAbstract,
    TWENTENAMES,)
FACULTIES = ['ITC', 'EEMCS', 'ET', 'TNW', 'BMS', 'Science and Technology Faculty', 'Behavioural, Management and Social Sciences', 'Engineering Technology', 'Geo-Information Science and Earth Observation', 'Electrical Engineering, Mathematics and Computer Science']
OA_WORK_COLUMNS = ['_id','id','doi','title','display_name','publication_year','publication_date','ids','language','primary_location','type','type_crossref','indexed_in','open_access','authorships','countries_distinct_count','institutions_distinct_count','corresponding_author_ids','corresponding_institution_ids','apc_list','apc_paid','has_fulltext','fulltext_origin','cited_by_count','cited_by_percentile_year','biblio','is_retracted','is_paratext','keywords','concepts','mesh','locations_count','locations','best_oa_location','sustainable_development_goals','grants','referenced_works_count','referenced_works','related_works','ngrams_url','abstract_inverted_index','cited_by_api_url','counts_by_year','updated_date','created_date','topics','primary_topic']
CR_WORK_COLUMNS = ['_id','indexed','reference-count','publisher','content-domain','published-print','abstract','DOI','type','created','page','source','is-referenced-by-count','title','prefix','author','member','container-title','link','deposited','score','resource','subtitle','issued','references-count','URL','published','issue','volume','journal-issue','ISSN','issn-type','subject','short-container-title','language','isbn-type','ISBN']
TAGLIST = ["UT-Hybrid-D", "UT-Gold-D", "NLA", "N/A OA procedure"]
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
logger = logging.getLogger(__name__)
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

from functools import wraps
import time


def timeit(func):
    @wraps(func)
    def timeit_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        total_time = end_time - start_time
        print(f'Function {func.__name__} took {total_time:.1f} seconds')
        return result
    return timeit_wrapper

@timeit
@transaction.atomic
def processMongoPaper(dataset, user=None):
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
                \/
            - journal
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
        print("\n========================== P R E P  O P E N A L E X ==========================\n")
        cleandata = {
            'paper':{
                'openalex_url':data.get('id'),
                'title':data.get('title'),
                'doi':data.get('doi'),
                'year':data.get('publication_year'),
                'citations':data.get('cited_by_count'),
                'openaccess':data.get('open_access').get('oa_status'),
                'is_oa':data.get('open_access').get('is_oa'),
                'primary_link':data.get('primary_location').get('landing_page_url') if data.get('primary_location').get('landing_page_url') else "",
                'pdf_link_primary':data.get('primary_location').get('pdf_url') if data.get('primary_location').get('pdf_url') else "",
                'itemtype':data.get('type_crossref'),
                'date':data.get('publication_date'),
                'language':data.get('language',""),
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
        print("\n========================= P R E P  C R O S S R E F =========================\n")
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
                if data.get(datetype):
                    if data.get(datetype).get('date-parts'):
                        if len(data.get(datetype).get('date-parts')[0])==1:
                            year=data.get(datetype).get('date-parts')[0][0]
                            datetypekey[datetype]=date.fromisoformat(f"{year}-01-01")
                        elif len(data.get(datetype).get('date-parts')[0])==3:
                            datetypekey[datetype] = date.fromisoformat("-".join([f"{i:02}" for i in data.get('published')['date-parts'][0]]))

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
        print("\n============================== L I C E N S E ==============================\n")
        value=None
        print('licenses:')
        data=data.get('full')
        if data.get('locations'):
            for loc in data.get('locations'):
                print(loc.get('license'))
        else:
            print('no locations?')
        if data.get('primary_location'):
            value = data.get('primary_location').get('license')
        else:
            if data.get('locations'):
                for loc in data.get('locations'):
                    if loc.get('license'):
                        value = loc.get('license')
        return value if value else ''
    def calc_taverne_date(oa_work, cr_work):
        print("\n============================== T A V E R N E ==============================\n")
        dates={}
        dates=[date.fromisoformat(oa_work['date'])]
        try:
            if cr_work.get('dates'):
                dates.append([value for value in cr_work.get('dates').values()])
                return min(dates)+relativedelta(months=+6)
            else:
                return dates[0]+relativedelta(months=+6)
        except Exception as e:
            print('error in calc_taverne_date',e)
            return None
    def get_pages_count(oa_work, cr_work):
        print("\n============================== P A G E S ==============================\n")

        first_page = oa_work.get('pages').get('first')
        last_page = oa_work.get('pages').get('last')
        print("first_page, last_page",first_page, last_page)
        pages=''
        pagescount = None
        if cr_work:
            if cr_work.get('page') and cr_work.get('page') != '':
                pages=cr_work.get('page')
                print(f"from crossref: {pages=}")
        elif first_page and last_page:
            pages=f'{first_page}-{last_page}'
            print(f"first and last page, so using fp-lp: {pages=}")
        elif first_page:
            pages=first_page
        else:
            pages=''
        if first_page and last_page:
            pagescount = int(last_page) - int(first_page) + 1
            print(f'lastpage - firstpage for pagecount: {pagescount=}')
        else:
            pagescount = None
        if not pages:
            pages = ''
        print(f"{pages=}, {pagescount=}")
        return pagescount, pages


    #def calc_ut_keyword_suggestion(oa_work, cr_work):
    #    return None
    print("\n============================== N E W   I T E M ==============================")
    print("============================== N E W   I T E M ==============================")
    print("============================== N E W   I T E M ==============================\n")

    oa_work = prep_openalex_data(dataset['works_openalex'])
    cr_work = prep_crossref_data(dataset['crossref'])
    stop = False
    oa_work['paper'].update(cr_work.get('dates', {}))
    oa_work['paper']['license'] = get_license_data(oa_work)
    oa_work['paper']['pagescount'], oa_work['paper']['pages'] = get_pages_count(oa_work, cr_work)
    print(f' making paper using {oa_work['paper']=}')
    #go_on=input("continue creating the paper? (y/n)")
    #if go_on != 'y':
    #    return


    if Paper.objects.filter(doi=oa_work['paper']['doi']).exists():
        print("paper already exists (itemid=",Paper.objects.get(doi=oa_work['paper']['doi']).id,")")
        stop_q = input("continue creating the paper? (y/n)")
        if stop_q != 'y':
            viewfulloa = input("Do you want to view the full open alex input object? (y/n)")
            if viewfulloa == 'y':
                print("oa_work['full'] is:")
                print(oa_work['full'])
            print("stopping execution of this iteration")
            return

    paper, created = Paper.objects.get_or_create(**oa_work['paper'])
    if created:
        paper.save()
    print("paper created with id ", paper.id)

    paper = add_authorships(oa_work['full'],paper)
    paper = add_locations(oa_work['full'],paper)

    paper.taverne_date=calc_taverne_date(oa_work['paper'], cr_work.get('dates', {}))
    #paper.ut_keyword_suggestion=calc_ut_keyword_suggestion(oa_work, cr_work)
    #paper.is_in_pure = determine_is_in_pure(oa_work['paper'])

    if user:
        viewPaper.objects.get_or_create(user=user, displayed_paper=paper)

@timeit
@transaction.atomic
def add_authorships(data, paper):

    @timeit
    def getorgs(affils, is_ut):
        affiliations=[]
        for org in affils:
            # get affiliation info into a list of dicts, check for is_ut along the way
            if not org:
                continue
            if org.get('institution'):
                orgsrc = org.get('institution')
            orgdata = {
                'name':orgsrc.get('display_name'),
                'openalex_url':orgsrc.get('id'),
                'ror':orgsrc.get('ror'),
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

            # if org is already in db, either
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
                org, created = Organization.objects.get_or_create(**orgdata)
                if created:
                    org.save()

            affiliations.append([org, years])
        return affiliations
    @timeit
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

        authorobject, created = Author.objects.get_or_create(**authordict)
        if created:
            authorobject.save()
        for aff in affiliations:
            authorobject.affils.add(aff[0],through_defaults={'years':aff[1]})

        return authorobject
    @timeit
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
            }
            ut, created = UTData.objects.get_or_create(**utdata)
            if created:
                ut.save()
            authorobject.is_ut = True
            authorobject.save()
        else:
            print("no ut data for ut author found, oa id: ", author.get('id'))
    print("\n============================== A U T H O R S ==============================\n")
    authorships = data.get('authorships')
    for authorship in authorships:
        author = authorship.get('author')
        if Author.objects.filter(openalex_url=author.get('id')).exists():
            authorobject = Author.objects.filter(openalex_url=author.get('id')).get()
        else:
            authorobject = makefullauthor(author, authorship)

        authorshipdict = {
                    'paper':paper,
                    'position':authorship.get('author_position'),
                    'corresponding':authorship.get('is_corresponding'),
                }
        paper.authors.add(authorobject, through_defaults={'position':authorshipdict.get('position'), 'corresponding':authorshipdict.get('corresponding')})

        if authorobject.is_ut:
            add_peoplepagedata(author, authorobject)

    return paper

@timeit
@transaction.atomic
def add_locations(data, paper):
    print("\n============================== L O C A T I O N S ==============================\n")
    @timeit
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
    print('primary:',data.get('primary_location'))
    print('best_oa:',data.get('best_oa_location'))
    for location in data['locations']:
        if location['source']:
            source, sourcedict = get_source(location['source'])
        else:
            is_twente = False
            if location.get('landing_page_url'):
                if 'twente' in location.get('landing_page_url'):
                    is_twente = True
            if location.get('pdf_url'):
                if 'twente' in location.get('pdf_url'):
                    is_twente = True

            if is_twente:
                source, created = Source.objects.filter(openalex_url='https://openalex.org/P4363603077').get_or_create({
                    'openalex_url':'https://openalex.org/P4363603077',
                    'display_name':'University of Twente RIS',
                    'host_org':'University of Twente',
                    'type':'repository',
                    'is_in_doaj':False,
                })
                if created:
                    source.save()
                sourcedict = None

                print('found ut pure location')
                paper.is_in_pure = True
                paper.save()
            else:
                print('no source for this location:')
                print(location)

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
        location, created = Location.objects.get_or_create(**cleandata)
        if created:
            location.save()

        paper.locations.add(location)

        if any([is_primary, len(data['locations'])==1]) and sourcedict:
            journaldata=sourcedict
            journaldata['name']=sourcedict.get('display_name')
            del journaldata['display_name']
            if 'homepage_url' in journaldata:
                del journaldata['homepage_url']
            dealdata, keywords, publisher = get_deal_data(journaldata['openalex_url'])
            journaldata['keywords']=keywords
            journaldata['publisher']=publisher if publisher else ""
            journal, created = Journal.objects.get_or_create(**journaldata)
            if created:
                journal.save()
            if dealdata and not journal.dealdata:
                deal, created = DealData.objects.get_or_create(**dealdata)
                if created:
                    deal.save()
                journal.dealdata=deal
                journal.save()

            paper.journal=journal
    return paper

@timeit
@transaction.atomic
def get_source(data):
    print("\n============================== S O U R C E ==============================\n")
    issn=data.get('issn_l')
    issnlist=data.get('issn')
    eissn=""
    if isinstance(issnlist, list):
        for nissn in issnlist:
            if nissn != issn:
                eissn = nissn
                break

    sourcedict = {
        'openalex_url':data.get('id'),
        'display_name':data.get('display_name'),
        'host_org':data.get('host_organization_name') if data.get('host_organization_name') else '',
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

    print(f"creating source using {sourcedict=}")
    source, created = Source.objects.get_or_create(**sourcedict)
    if created:
        source.save()

    return source, sourcedict
def determine_is_in_pure(data):
    locs = data.get('locations')
    twentecheckstrs={'twente','ris.utwente.nl','research.utwente.nl'}
    if locs:
        for loc in locs:
            if str(loc.get('landing_page_url')).lower() in twentecheckstrs or str(loc.get('pdf_url')).lower() in twentecheckstrs:
                return True
    return False


'''
def oldprocessMongoPaper(dataset):
    # check authorships
    # check affiliations

    data=check_data(dataset['openalex_work']['data'], 'openalex_work')
    if 'data' in dataset['crossref_work'].keys():
        data_crossref=check_data(dataset['crossref_work']['data'], 'crossref_work')
    else:
        data_crossref=check_data({},'crossref_work')

    pagescount,pages = calc_pagedata(data, data_crossref)
    crossrefdates = calc_crossref_dates(data_crossref)
    [year, month, day]=str(data['publication_date']).split('-')
    openalex_date=date(int(year), int(month), int(day))
    dates = [date for date in [crossrefdates['published_print'], crossrefdates['published_online'], crossrefdates['published'], crossrefdates['issued']] if date is not None]
    dates.append(openalex_date)
    earliestdate = min(dates)
    tavernedate = earliestdate + relativedelta(months=+6)
    apc_data = getAPCData(data)
    prim_loc=""
    prim_pdf=""
    if 'primary_location' in data.keys():
        if isinstance(data['primary_location'],dict):
            prim_loc=data['primary_location']['landing_page_url'] if 'landing_page_url' in data['primary_location'].keys() else ""
            prim_pdf=data['primary_location']['pdf_url'] if data['primary_location']['pdf_url'] is not None else ""
    fulldict = {
        'openalex_url':data['id'],
        'doi':data['doi'],
        'title':data['title'],
        'itemtype':data['type_crossref'],
        'language':data['language'],
        'citations':data['cited_by_count'],
        'abstract':add_abstract(data['abstract_inverted_index']),
        'year':data['publication_year'],
        'date':openalex_date,
        'primary_link':prim_loc,
        'is_oa': data['open_access']['is_oa'],
        'pages':pages,
        'pagescount':pagescount,
        'volume':data['biblio']['volume'] if data['biblio']['volume'] is not None else "",
        'issue':data['biblio']['issue'] if data['biblio']['issue'] is not None else "",
        'pdf_link_primary':prim_pdf,
        'openaccess':data['open_access']['oa_status'],
        'published_print':crossrefdates['published_print'],
        'published_online':crossrefdates['published_online'],
        'published':crossrefdates['published'],
        'issued':crossrefdates['issued'],
        'taverne_date':tavernedate,
        'apc_listed_value':apc_data[0],
        'apc_listed_currency':apc_data[1],
        'apc_listed_value_usd':apc_data[2],
        'apc_listed_value_eur':apc_data[3],
        'apc_paid_value':apc_data[4],
        'apc_paid_currency':apc_data[5],
        'apc_paid_value_usd':apc_data[6],
        'apc_paid_value_eur':apc_data[7],
    }
    if fulldict['primary_link'] is None:
        fulldict['primary_link'] = ""
    work=Paper(**fulldict)
    work.journal = getJournals(data)
    work.save()
    locationdata = add_locations(data)
    if locationdata:
        for location in locationdata:
            work.locations.add(location)

    keywords=add_keywords(data['keywords'])
    if keywords:
        for keyword in keywords:
            work.keywords.add(keyword)
    authorships=get_authorships_data(data['authorships'])
    for authorship in authorships:
        if isinstance(authorship['author']):
            with transaction.atomic():
                work.authors.add(authorship['author'], through_defaults={
                    'position': authorship['position'],
                    'corresponding': authorship['corresponding'],
                })

    work.ut_keyword_suggestion=calculateUTkeyword(data, work, authorships)
    work.is_in_pure = determineIsInPure(work)
    work.save()

def check_data(data, source):
    cleaneddata={}

    if source=='openalex_work':
        sourcecolumns=OA_WORK_COLUMNS
    elif source=='crossref_work':
        sourcecolumns=CR_WORK_COLUMNS

    for key in sourcecolumns:
        if key in data.keys():
            if data[key] is not None and data[key] != "":
                if data[key] != []:
                    if data[key] != {}:
                        cleaneddata[key]=data[key]
                    else:
                        cleaneddata[key]={}
                else:
                    cleaneddata[key]=[]
            else:
                cleaneddata[key]=""
        else:
            cleaneddata[key]=""

    return cleaneddata

def add_abstract(inverted_abstract):
    try:
        word_index = []
        for k, v in inverted_abstract.items():
            for index in v:
                word_index.append([k, index])
        word_index = sorted(word_index, key=lambda x: x[1])
        text = " ".join(word[0] for word in word_index)
    except Exception:
        text=""
    return text

def add_keywords(keyworddata):
    keywords=[Keyword(keyword=x['keyword'], score=x['score'], data_source='OpenAlex') for x in keyworddata]
    with transaction.atomic():
        keywords=Keyword.objects.bulk_create(keywords)
    return keywords

def getJournals(work):
    """
    Stores the journal data for a given work in the Journal model.

    Parameters:
        Work (pyalex Work object): the result of a pyalex Works() query.

    Returns:
        journal (Journal): The created Journal object.
    """

    if work["primary_location"]["source"] is None:
        journal = None
    else:
        try:
            e_issn = (
                work["primary_location"]["source"]["issn_l"]
                if work["primary_location"]["source"]["issn_l"] is not None
                else ""
            )
            issn = e_issn
            if work["primary_location"]["source"]["issn"] is not None:
                for issn in work["primary_location"]["source"]["issn"]:
                    if issn != e_issn:
                        issn = issn
                        break

            journal_data = {
                "name": work["primary_location"]["source"]["display_name"]
                if work["primary_location"]["source"]["display_name"] is not None
                else "",
                "e_issn": e_issn,
                "issn": issn,
                "host_org": work["primary_location"]["source"][
                    "host_organization_lineage_names"
                ][0]
                if len(
                    work["primary_location"]["source"][
                        "host_organization_lineage_names"
                    ]
                )
                > 0
                and work["primary_location"]["source"][
                    "host_organization_lineage_names"
                ]
                is not None
                else "",
                "doaj": work["primary_location"]["source"]["is_in_doaj"]
                if work["primary_location"]["source"]["is_in_doaj"] is not None
                else "",
                "is_oa": work["primary_location"]["source"]["is_oa"]
                if work["primary_location"]["source"]["is_oa"] is not None
                else "",
                "type": work["primary_location"]["source"]["type"]
                if work["primary_location"]["source"]["type"] is not None
                else "",
            }
            with transaction.atomic():
                journal, created = Journal.objects.get_or_create(**journal_data)
                if created:
                    journal.save()
        except Exception:
            journal = None

    return journal

def add_locations(data):
    locations=[]
    is_best_oa=False
    is_primary=False
    for location in data['locations']:
        if isinstance(data['primary_location'],dict):
            if location['landing_page_url'] == data['primary_location']['landing_page_url']:
                is_primary=True
        if isinstance(data['best_oa_location'],dict):
            if location['landing_page_url'] == data['best_oa_location']['landing_page_url']:
                is_best_oa=True
        source=None
        sourced=location['source']
        if sourced:
            if 'id' in sourced.keys():
                if Source.objects.filter(openalex_url=sourced['id']).exists():
                    source=Source.objects.get(openalex_url=sourced['id'])
                else:
                    eissn=None
                    issn=None
                    if 'issn' in sourced.keys() and 'issn_l' in sourced.keys():
                        if sourced['issn'] and sourced['issn_l']:
                            issn=sourced['issn_l']
                            for issn_list in sourced['issn']:
                                if issn_list != sourced['issn_l']:
                                        eissn=issn_list
                    sourcedict={
                        'openalex_url':sourced['id'],
                        'homepage_url':'',
                        'display_name':sourced['display_name'],
                        'issn':issn,
                        'e_issn':eissn,
                        'host_org':sourced['host_organization_name'] if sourced['host_organization_name']!='' and sourced['host_organization_name'] is not None else '',
                        'type':sourced['type'],
                        'is_in_doaj':sourced['is_in_doaj'],
                    }

                    source=Source(**sourcedict)
                    with transaction.atomic():
                        source.save()
        locdict={
            'is_oa':location['is_oa'],
            'landing_page_url':location['landing_page_url'] if location['landing_page_url'] else '',
            'pdf_url':location['pdf_url'] if location['pdf_url'] else '',
            'license':location['license'] if location['license'] else '',
            'is_accepted':location['is_accepted'],
            'is_published':location['is_published'],
            'is_primary':is_primary,
            'is_best_oa':is_best_oa,
        }
        if source:
            locdict['source']=source
        loc=Location(**locdict)
        with transaction.atomic():
            loc.save()
        locations.append(loc)
    return locations

def get_organizations_data(orgdata):
    organizations=[]
    is_ut=False
    if not isinstance(orgdata, list):
        orgdata=[{'institution':orgdata}]
    for entry in orgdata:
        org=entry['institution']
        tmp={}
        tmp['openalex_url']=org['id']
        tmp['name']=org['display_name']
        if 'twente' in tmp['name'].lower():
            is_ut=True
        tmp['type']=org['type'] if org['type'] else ''
        tmp['ror']=''
        tmp['country_code']=''
        if 'ror' in org.keys():
            tmp['ror']=org['ror'] if org['ror'] else ''
        if 'country_code' in org.keys():
            tmp['country_code']=org['country_code'] if org['country_code'] else ''
        if not Organization.objects.filter(name=tmp['name'],country_code=tmp['country_code']).exists():
            with transaction.atomic():
                orgobj = Organization.objects.create(**tmp)
                orgobj.save()
        else:
            orgobj=Organization.objects.get(name=tmp['name'],country_code=tmp['country_code'])
            if orgobj.ror == "" and tmp['ror']!='':
                orgobj.ror=tmp['ror']
                with transaction.atomic():
                    orgobj.save()
        if 'years' in entry.keys():
            years=entry['years']
        else:
            years=[]
        organizations.append({'data':orgobj,'years':years})
    return organizations,is_ut


def get_authorships_data(authordata):
    def get_more_author_data(author_data):

        # author_data: list of dicts with base author info from openalex work
        # in this function, retrieve detailed author data
        # either get the data from mongodb or do a openalex api call to get it
        # same for ORCID data
        # return a dict with the extra data, use openalex id or ORCID as key

        extra_data = {}
        authors_openalex=db['api_responses_authors_openalex']
        authors_orcid=db['api_responses_orcid']

        for authordict in author_data:
            author=authordict['author']
            if 'orcid' in author.keys():
                if author['orcid'] != '' and author['orcid'] is not None:
                    searchresult=authors_orcid.find_one({'orcid':author['orcid']})
                    if searchresult:
                        extra_data[author['orcid']]={'data':searchresult}
                    else:
                        #call api
                        ...
            if 'id' in author.keys():
                if 'openalex' in author['id']:
                    searchresult=authors_openalex.find_one({'id':author['id']})
                    if not searchresult:
                        searchresult=db['api_responses_UT_authors_openalex'].find_one({'id':author['id']})
                    if searchresult:
                        extra_data[author['id']]={'data':searchresult}
                    else:
                        #call api
                        ...
        return extra_data
    def get_ut_data(id):
        # use openalex id to grab data from mongodb containing
        # people page data and any other relevant data
        # for an UT author.
        utdata={
            'employee_id':'',
            'email':'',
            'employment_history':'',
            'position':'',
            'faculty':'',
            'group':'',
            'people_page_url':'',
            'avatar':'',
        }
        peoplepagedata=db['api_responses_UT_authors_peoplepage'].find_one({'id':id})
        data=None
        peopledata={}
        if peoplepagedata:
            group=""
            faculty=""
            if len(peoplepagedata['grouplist'])>1:
                for entry in peoplepagedata['grouplist']:
                    if entry['faculty'] in FACULTIES:
                        if group=="":
                            group=entry['group']
                            faculty=entry['faculty']
                        else:
                            if entry['group']=='':
                                continue

            elif len(peoplepagedata['grouplist'])==1:
                group=peoplepagedata['grouplist'][0]['group']
                faculty=peoplepagedata['grouplist'][0]['faculty']

            if group=="" and faculty=="":
                if len(peoplepagedata['grouplist'])>0:
                    group=peoplepagedata['grouplist'][0]['group']
                    faculty=peoplepagedata['grouplist'][0]['faculty']

            peopledata = {
                'avatar':peoplepagedata['avatar_url'],
                'people_page_url':peoplepagedata['profile_url'],
                'position': peoplepagedata['position'],
                'email': peoplepagedata['email'],
                'group': group,
                'faculty': faculty,
            }
            for key, value in peopledata.items():
                utdata[key]=value

            data={'data':utdata}
        #if puredata:
        # TODO add code here

        return data

    extradata=get_more_author_data(authordata)
    authors=[]
    for authordict in authordata:
        try:
            authorobject=None
            author=authordict['author']
            if Author.objects.filter(openalex_url=author['id']).exists():
                authorobject=Author.objects.filter(openalex_url=author['id']).first()
            elif author['id'] == 'https://openalex.org/A9999999999':
                raise Exception("Skipping OpenAlex id: https://openalex.org/A9999999999")
            else:
                if 'affiliations' not in extradata[author['id']]['data'].keys():
                    affldata=extradata[author['id']]['data']['last_known_institution']
                else:
                    affldata=extradata[author['id']]['data']['affiliations']

                affiliations, is_ut=get_organizations_data(affldata)

                hname=HumanName(author['display_name'])
                data = {
                    'name': author['display_name'],
                    'first_name': hname.first,
                    'last_name': hname.last,
                    'middle_name': hname.middle,
                    'initials': hname.initials(),
                    'known_as':extradata[author['id']]['data']['display_name_alternatives'],
                    'openalex_url':author['id'],
                    'scopus_id':extradata[author['id']]['data']['ids']['scopus'] if 'scopus' in extradata[author['id']]['data']['ids'].keys() else None,
                    'orcid':author['orcid'] if author['orcid'] and author['orcid'] != "" else None,
                }
                if is_ut:
                    utdata=get_ut_data(author['id'])
                    if utdata:
                        data.update(utdata['data'])

                authorobject=Author(**data)
                with transaction.atomic():
                    authorobject.save()

                for affiliation in affiliations:
                    affiliation['data'] # figure out how this dict looks; put in employee_history!

                with transaction.atomic():
                    authorobject.save()

            if authorobject:
                position=''
                corresponding=None
                if 'author_position' in authordict.keys():
                    position = authordict['author_position'] if authordict['author_position'] else ''
                if 'is_corresponding' in authordict.keys():
                    corresponding = authordict['is_corresponding'] if authordict['is_corresponding'] else None
                authorship={
                    'author':authorobject,
                    'position':position,
                    'corresponding':corresponding,
                }
                authors.append(authorship)
            else:
                pass
        except Exception:
            pass


    return authors


def calc_pagedata(data, crossrefdata):
    biblio=data['biblio']
    try:
        pagescount = (
            1 + int(biblio["last_page"]) - int(biblio["first_page"])
        )
    except Exception :
        pagescount = None

    if 'pages' in crossrefdata.keys():
        if crossrefdata["pages"] is not None:
            pages = crossrefdata["pages"]
    else:
        if pagescount is not None:
            if pagescount > 1:
                pages = f"{biblio['first_page']}-{biblio['last_page']}"
            elif pagescount == 1:
                pages = f"{biblio['first_page']}"
            else:
                pages = ""
        else:
            pages = ""
    return pagescount,pages

def calc_crossref_dates(crossrefdata):
    dates={}
    try:
        published_print = (
            crossrefdata["published-print"]["date-parts"][0]
            if crossrefdata["published-print"]["date-parts"] is not None
            else ""
        )
        if len(published_print) == 3:
            published_print = date(
                published_print[0], published_print[1], published_print[2]
            )
        else:
            published_print = date(published_print[0], published_print[1], 1)
    except Exception:
        published_print = None
    try:
        issued = (
            crossrefdata["issued"]["date-parts"][0]
            if crossrefdata["issued"]["date-parts"] is not None
            else ""
        )
        if len(issued) == 3:
            issued = date(issued[0], issued[1], issued[2])
        else:
            issued = date(issued[0], issued[1], 1)
    except Exception:
        issued = None
    try:
        published = (
            crossrefdata["published"]["date-parts"][0]
            if crossrefdata["published"]["date-parts"] is not None
            else ""
        )
        if len(published) == 3:
            published = date(published[0], published[1], published[2])
        else:
            published = date(published[0], published[1], 1)
    except Exception:
        published = None
    try:
        published_online = (
            crossrefdata["published-online"]["date-parts"][0]
            if crossrefdata["published-online"]["date-parts"] is not None
            else ""
        )
        if len(published_online) == 3:
            published_online = date(
                published_online[0], published_online[1], published_online[2]
            )
        else:
            published_online = date(published_online[0], published_online[1], 1)
    except Exception:
        published_online = None

    dates={
        'published_print':published_print,
        'issued':issued,
        'published':published,
        'published_online':published_online
    }
    return dates

def calculateUTkeyword(work, paper, authorships):
    keyword = ""
    dealstatus = ""
    license = ""
    oatypejournal = ""
    ut_corresponding = False
    ut_author = False
    corresponders = []
    # determine keyword to add based on flowchart
    # work --> openalex api response
    # paper --> Paper object
    # authorships --> dict with authorship data
    license = paper.license
    paper.openaccess
    is_oa = paper.is_oa
    paper.is_in_pure
    paper.has_pure_oai_match
    taverne_date = paper.taverne_date
    for author in authorships:
        if author["author"].is_ut:
            ut_author = True
            if author["corresponding"]:
                ut_corresponding = True
                corresponders.append(author["author"].name)
    if not ut_author:
        keyword += " (no UT author found) "
    if not ut_corresponding:
        keyword += " (no corresponding UT author found) "
    if paper.journal is not None:
        dealdata = DealData.objects.filter(journal=paper.journal)
        if dealdata.exists():
            dealstatus = dealdata.first().deal_status
            oatypejournal = dealdata.first().oa_type
    if "100% APC discount for UT authors" in dealstatus:
        if is_oa:
            if (
                oatypejournal
                == "Hybrid Open Access. Journal supports Open Access publishing on request"
            ):
                keyword += " UT-Hybrid-D "
            if (
                oatypejournal
                == "Full Open Access. All articles in this journal are Open Access"
            ):
                keyword += " UT-Gold-D "
        else:
            keyword += " Missed deal. Email authors to notify. "
    elif license in LICENSESOA:
        keyword += " Has open acces license - no keyword needed - OA status Open "
    elif taverne_date is not None:
        if datetime.today().date() >= taverne_date:
            keyword += f" Taverne with keyword {datetime.today().year} OA Procedure "

    return keyword


def getAPCData(work):
    publication_date = date.fromisoformat(work["publication_date"])

    try:
        apc_list = work["apc_list"]
        if apc_list is None:
            listed_value = 0
            listed_currency = ""
            listed_value_usd = 0
            listed_value_eur = 0
        else:
            listed_value = int(apc_list["value"])
            listed_currency = apc_list["currency"]
            listed_value_usd = int(apc_list["value_usd"])
            listed_value_eur = convertToEuro(
                listed_value, listed_currency, publication_date
            )

    except Exception:
        listed_value = 0
        listed_currency = ""
        listed_value_usd = 0
        listed_value_eur = 0

    try:
        apc_paid = work["apc_paid"]
        if apc_paid is None:
            paid_value = 0
            paid_currency = ""
            paid_value_usd = 0
            paid_value_eur = 0
        else:
            paid_value = int(apc_paid["value"])
            paid_currency = apc_paid["currency"]
            paid_value_usd = int(apc_paid["value_usd"])
            paid_value_eur = convertToEuro(paid_value, paid_currency, publication_date)
    except Exception:
        paid_value = 0
        paid_currency = ""
        paid_value_usd = 0
        paid_value_eur = 0

    return [
        listed_value,
        listed_currency,
        listed_value_usd,
        listed_value_eur,
        paid_value,
        paid_currency,
        paid_value_usd,
        paid_value_eur,
    ]
    '''