from .models import (
    Paper,
)
from django.db.models import Prefetch, Exists, OuterRef
from .constants import FACULTYNAMES
from loguru import logger
from io import StringIO
from rich import print
from pymongo import MongoClient
from django.conf import settings
import json

def generateMainPage(user):
    """
    returns:
    dict total with keys articles = num of papers and oa = % of papers where is_oa==true
    list faculties, each entry is dict with keys name,articles,oa; self explanatory
    """
    facultynamelist = ["EEMCS", "BMS", "ET", "ITC", "TNW", "marked", "Other groups"]
    total = {
        "articles": 1,
        "oa": 0,
        "numoa": 0,
        "inpure": 0,
        "inpure_percent": 0,
        "inpurematch": 0,
    }
    faculties = []
    for faculty in facultynamelist:
        facultyname, stats, _ = getPapers(faculty, "all", user)
        total["articles"] += stats["num"]
        total["numoa"] += stats["numoa"]
        total["inpure"] += stats["articlesinpure"]
        total["inpurematch"] += stats["articlesinpurematch"]
        faculties.append(
            {
                "name": facultyname,
                "articles": stats["num"],
                "oa": stats["oa_percent"],
                "inpure": stats["articlesinpure"],
                "inpure_percent": stats["articlesinpure_percent"],
                "inpurematch": stats["articlesinpurematch"],
                "inpurematch_percent": stats["articlesinpurematch_percent"],
            }
        )
    total["oa"] = round(total["numoa"] / total["articles"] * 100, 2)
    total["inpure_percent"] = round(total["inpure"] / total["articles"] * 100, 2)
    total["inpurematch_percent"] = round(
        total["inpurematch"] / total["articles"] * 100, 2
    )
    total['articles'] += -1
    return total, faculties
def getPapers(name, filter="all", user=None):
    facultyname = ""
    listpapers = []
    if user is None:
        username = "none"
    else:
        username = user.username
    if isinstance(name, int):
        logger.info("getpaper [id] {} [user] {}", name, username)
        paperid = name
        facultyname = "single"
        listpapers = Paper.objects.get_single_paper_data(paperid,user)
        stats = None
        return facultyname, stats, listpapers
    else:
        logger.info("getpapers [name] {} [filter] {} [user] {}", name, filter, username)
        if filter == 'author':
            facultyname = name+" [Author]"
            filterpapers = Paper.objects.get_author_papers(name)
            filter = [['all','']]
        elif name == "marked" or name == "Marked papers":
            facultyname = "Marked papers"
            filterpapers=Paper.objects.get_marked_papers(user)
            if isinstance(filter, str):
                filter = [[str(filter),""]]
        else:
            filterpapers = Paper.objects.all().distinct()
            if name == "all" or name == "All items":
                facultyname = "All MUS papers"
                name = 'all'
                if isinstance(filter, str):
                    filter = [[str(filter),""]]
            else:
                if name not in FACULTYNAMES:
                    facultyname = "Other groups"
                    name = 'other'
                else:
                    facultyname = name
                if isinstance(filter, str):
                    filter = [[str(filter),""],['faculty',name]]
                if isinstance(filter, list):
                    if ['faculty', name] not in filter:
                        filter.append(['faculty',name])

    listpapers = filterpapers.get_table_data(filter,user)
    stats = listpapers.get_stats()
    return facultyname, stats, listpapers
def open_alex_autocomplete(query, types=['works','authors'], amount=5):
    '''
    Uses the OpenAlex autocomplete API to fetch data
    https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/autocomplete-entities
    Parameters:
        query: string to search for
        type: list of strings that denotes the itemtype(s) to search for. Defaults to ['works', 'authors'].
            Choices are: 'works', 'authors', 'sources', 'institutions', 'concepts', 'publishers', 'funders'
        amount: number of results to return, defaults to 5
    Returns:
        response: json response from OpenAlex with 'count' and 'results' fields
            count: number of results total
            results: list of first <amount> found results with the following fields:
            ------------------------------------------------------------------------------------
                'id'                openalex id -- use this to find items in mus database!
                'display_name'      name of item
                'entity_type'       openalex entity type, should match parameter type
                'cited_by_count'    # of citations for Work or sum of all works related to item if not Work
                'works_count'       # of associated works; always 0 for Works
                'hint'              Depends on type - Work: author names, Author: last known institution, Source: host org, Institution: location, Concept: description
                'external_id'       ROR, ORCID, DOI, that sort of thing
                'filter_key'        points to field in openalex work that holds this type of item
            ------------------------------------------------------------------------------------

    '''


    '''
    Call the OpenAlex autocomplete API.
    Returns json with meta, results as root keys.
    meta has fields 'count', 'db_response_time_ms', 'page', 'per_page'.
    results is list of dicts with fields as shown above.
    '''
    import httpx

    tresults={}
    for oa_type in types:
        query = query.replace(' ', '+')
        if oa_type=='works':
            url = f"https://api.openalex.org/autocomplete/{oa_type}?q={query}"
        else:
            url = f"https://api.openalex.org/autocomplete/{oa_type}?q={query}"
        result= {
        'count':0,
        'results':[]
        }

        response = httpx.get(url)
        response.raise_for_status()
        data=response.json()

        result['count']=data['meta']['count']
        if result['count']==0:
            print('no results (?)')
            return None
        result['type']=[oa_type]
        if result['count']>=5:
            result['results']=data['results'][:6]
        else:
            result['results']=data['results']
        tresults[oa_type]=result

    maxlen=0
    most_results_type=''
    for key, value in tresults.items():
        if value['count']>maxlen:
            maxlen=value['count']
            most_results_type=key
    if most_results_type=='':
        return None
    if tresults[most_results_type]['count']>=5:
        result=tresults[most_results_type]
    else:
        result=tresults[most_results_type]
        for oa_type in types:
            if oa_type==most_results_type:
                continue
            elif oa_type in tresults and tresults[oa_type]['count']>0:
                result['results'].extend(tresults[oa_type]['results'][:(5-len(result['results']))])
                result['count']+=tresults[oa_type]['count']
                result['type']=result['type'].append(oa_type)
            if result['count']>=5:
                break
    return result

def getAuthorPapers(display_name, user=None):
    logger.info("authorpapers [author] {} [user] {}", display_name, user.username)
    return getPapers(display_name, 'author', user)

def get_raw_data(article_id, user=None):
    article=Paper.objects.get_single_paper_data(article_id, user)
    if not article:
        return None, None, None

    openalexid=article.openalex_url
    doi = article.doi
    title = article.title

    if not any([openalexid, doi, title]):
        return None, None, None

    author_openalexids = []
    for author in article.authors.all():
        author_openalexids.append(author.openalex_url)
    source_openalexids = []
    for location in article.locations.all():
        try:
            source_openalexids.append(location.source.openalex_url)
        except Exception:
            pass

    raw_data={}
    fulljson = {}
    client=MongoClient(getattr(settings, 'MONGOURL', None))
    db=client['mus']
    cutdoi = doi.replace('https://doi.org/','')
    pure_works=db['api_responses_pure']

    if openalexid:
        openalex_works=db['api_responses_works_openalex']
        mongo_openaire_results = db['api_responses_openaire']

        raw_data['openalex_work']=openalex_works.find_one({'id':openalexid})
        raw_data['openaire']=mongo_openaire_results.find_one({'id':openalexid})
    if doi:
        crossref_info=db['api_responses_crossref']
        datacite_info=db['api_responses_datacite']
        raw_data['crossref']=crossref_info.find_one({'DOI':cutdoi})
        raw_data['datacite']=datacite_info.find_one({'doi':cutdoi})
        if raw_data.get('datacite'):
            del raw_data['datacite']['_id']
        if article.has_pure_oai_match:
            raw_data['pure']=pure_works.find_one({'identifier':{'doi':cutdoi}})
            if not raw_data.get('pure'):
                raw_data['pure']=pure_works.find_one({'identifier':{'doi':doi}})
    if article.has_pure_oai_match and not raw_data.get('pure'):
        raw_data['pure']=pure_works.find_one({'title':article.pure_entries.first().title})
    if author_openalexids != []:
        raw_data['authors']={}
        openalex_ut_authors = db['api_responses_UT_authors_openalex']
        openalex_authors = db['api_responses_authors_openalex']
        peoplepage_results = db['api_responses_UT_authors_peoplepage']
        for author_openalexid in author_openalexids:
            raw_data['authors'][author_openalexid]={}
            raw_data['authors'][author_openalexid]['openalex_author']=openalex_ut_authors.find_one({'id':author_openalexid})
            if not raw_data['authors'][author_openalexid]['openalex_author']:
                raw_data['authors'][author_openalexid]['openalex_author']=openalex_authors.find_one({'id':author_openalexid})
            raw_data['authors'][author_openalexid]['peoplepage']=peoplepage_results.find_one({'id':author_openalexid})
    if source_openalexids != []:
        openalex_journals = db['api_responses_journals_openalex']
        dealdata = db['api_responses_journals_dealdata_scraped']
        raw_data['locations']={}
        for source_openalexid in source_openalexids:
            raw_data['locations'][source_openalexid]={}
            raw_data['locations'][source_openalexid]['openalex_journal']=openalex_journals.find_one({'id':source_openalexid})
            raw_data['locations'][source_openalexid]['dealdata']=dealdata.find_one({'id':source_openalexid})



    fulljson=json.dumps(raw_data, default=str)

    return article, fulljson, raw_data
def exportris(papers):


    itemtypekey = {
        'journal-article':'JOUR',
        'posted-content':'GEN',
        'dissertation':'THES',
        'monograph':'SER',
        'reference-entry':'GEN',
        'proceedings-article':'CONF',
        'report':'RPRT',
        'book':'BOOK',
        'dataset':'DATA',
        'reference-book':'GEN',
        'journal-issue':'JOUR',
        'peer-review':'GEN',
        'report-series':'SER',
        'proceedings':'CONF',
        'other':'GEN',
        'book-chapter':'CHAP',
    }
    fullrisdata = []
    for paper in papers:
        # this is how the ris fields are imported in Pure
        mapping_ris_to_pure = {
            'T1': 'Title',
            'T2': 'Subtitle or Event name',
            'AU': 'Contributor',
            'N1': 'Bibliographic Note',
            'PY': 'Publication Date',
            'Y1': 'Publication Date',
            'Y2': 'Event Date',
            'AB': 'Abstract',
            'N2': 'Abstract',
            'KW': 'Keyword',
            'UR': 'Other Links',
            'U2': 'DOI',
            'DO': 'DOI',
            'M3': 'Research Output Type',
            'AN': 'Publication Import ID',
            'VL': 'Volume',
            'JO': 'Journal name',
            'JF': 'Journal name',
            'SN': 'ISSN or ISBN',
            'IS': 'Issue',
            'M1': 'Article Number',
            'SP': 'Pages (begin)',
            'EP': 'Pages (end)',
            'BT': 'Host Publication',
            'CY': 'Place of Publication',
        }
        #this is the mus data that is used to build the ris file
        mapping_ris_to_mus = {
            "TY",itemtypekey[paper.itemtype],
            "TI",paper.title,
            "AU",[(author.last_name+', '+author.first_name) for author in paper.authors.all().only('last_name','first_name').values()],
            "PY",paper.date,
            "Y1",paper.year,
            'N2',paper.abstract,
            'N1',paper.abstract,
            'KW',[keyword.get('keyword') for keyword in paper.keywords] if paper.keywords else '',
            'UR',[link.landing_page_url for link in paper.locations.all()],
            'U2',paper.doi.replace('https://doi.org/',''),
            'DO',paper.doi.replace('https://doi.org/',''),
            'M3',paper.itemtype,
            'VL',paper.volume,
            'JO',paper.journal.name,
            'JF',paper.journal.name,
            'SN',paper.journal.issn,
            'IS',paper.issue,
            'M1',paper.pages,
            'SP',paper.pages.split('-')[0],
            'EP',paper.pages.split('-')[1],
            #'BT', get host publication name from locations -> is primary -> source -> name or something; or from journal name?
        }


        risdata =[
            ["TY",itemtypekey[paper.itemtype]],
            ["T1",paper.title]
        ]

        for author in paper.authors.all():
            risdata.append(['AU',author.last_name+', '+author.first_name])
        risdata.append(["PY",paper.year])
        risdata.append(["Y1",paper.year])
        risdata.append(["N2",paper.abstract])
        risdata.append(["AB",paper.abstract])

        if paper.keywords != []:
            for keyword in paper.keywords:
                risdata.append(['KW',keyword.get('keyword')])

        for location in paper.locations.all():
            if location.landing_page_url and location.landing_page_url != '':
                risdata.append(['UR',location.landing_page_url])


        risdata.append(["U2",paper.doi.replace('https://doi.org/', '')])
        risdata.append(["DO",paper.doi.replace('https://doi.org/', '')])
        risdata.append(["M3",paper.itemtype])
        if paper.journal:

            risdata.append(["VL",paper.volume])
            risdata.append(["JO",paper.journal.name])
            risdata.append(["JF",paper.journal.name])
            risdata.append(["SN",paper.journal.issn])

            if paper.pages:
                if '-' in paper.pages:
                    pages = paper.pages.split('-')[0]
                else:
                    pages = paper.pages
                risdata.append(["M1",pages])

        risdata.append(["ER",''])
        fullrisdata.append(risdata)

    content = StringIO()
    with content as f:
        for risentry in fullrisdata:
            for item in risentry:
                f.write(str(item[0])+'  - '+str(item[1])+'\n')
        return content.getvalue()

