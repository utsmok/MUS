
from django.conf import settings
from .models import  Keyword, Location, Source, DealData, Author, Paper,  Organization, Journal
from django.db import transaction
from nameparser import HumanName
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from pymongo import MongoClient
from .data_helpers import (
    determineIsInPure,
    convertToEuro,)
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

client=MongoClient(MONGOURL)
db=client['mus']

def processMongoPaper(dataset):
    # TODO
    # check authorships
    # check affiliations
    # run tests using dummy database

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
        'type':data['type'],
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
    
    with transaction.atomic():
        work.journal = getJournals(data)

    with transaction.atomic():
        work.save()


    locationdata = add_locations(data)
    if locationdata:
        for location in locationdata:
            with transaction.atomic():
                work.locations.add(location)

    keywords=add_keywords(data['keywords'])
    if keywords:
        for keyword in keywords:
            with transaction.atomic():
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

    with transaction.atomic():
        work.is_in_pure = determineIsInPure(work)
    with transaction.atomic():
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
    keywords=[Keyword(name=x['keyword'], score=x['score'], source='OpenAlex') for x in keyworddata]
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
    oa_deals=[]
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
                        'host_org':sourced['host_organization_name'] if sourced['host_organization_name']!='' else '',
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
    return locations,oa_deals

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