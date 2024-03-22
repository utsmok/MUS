from .models import (
    Location,
    Author,
    Paper,
    Authorship,
    viewPaper,
)
from django.db.models import Count, Q, Prefetch, Exists, OuterRef
from .data_helpers import TCSGROUPS, TCSGROUPSABBR, EEGROUPS, EEGROUPSABBR
import regex as re
from datetime import datetime
from loguru import logger
from collections import defaultdict
from io import StringIO
from rich import print
from pymongo import MongoClient
from django.conf import settings
import json

def getTablePrefetches(filterpapers):
    location_prefetch = Prefetch(
        "locations",
        queryset=Location.objects.all().select_related('source'),
        to_attr="pref_locations",
    )
    authors_prefetch =Prefetch(
        'authors',
        queryset=Author.objects.all().select_related('utdata'),
        to_attr="pref_authors",
    )

    return [
        location_prefetch,
        authors_prefetch,
    ]

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
    if user is None:
        username = "none"
    else:
        username = user.username
    if isinstance(name, int):
        logger.info("getpaper [id] {} [user] {}", name, username)
    else:
        logger.info("getpapers [name] {} [filter] {} [user] {}", name, filter, username)

    facultynamelist = ["EEMCS", "BMS", "ET", "ITC", "TNW", 'eemcs', 'bms', 'et', 'itc','tnw']
    facultyname = ""
    listpapers = []

    def getSinglePaper():
        paperid = name
        filterpapers = Paper.objects.filter(id=paperid)
        facultyname = "single"
        listpapers = Paper.objects.filter(id=paperid).prefetch_related(
            *getcommonPrefetches(filterpapers)
        ).select_related('journal').annotate(
                marked=Exists(viewPaper.objects.filter(displayed_paper=OuterRef("pk")))
            )
        stats = None
        return facultyname, stats, listpapers

    def applyFilter(listpapers, filter):
        '''
        listpapers = main list of papers that need filtering
        filter = list of filters
                each entry is another list with:
                    [filtername, value to use when filtering]
                    "" is the default value
        '''

        if len(filter) == 0:
            return listpapers
        if len(filter) == 1:
            if filter[0][0] == 'all':
                return listpapers

        finalfilters = defaultdict(list)
        for item in filter:
            filter=item[0]
            value=item[1]
            logger.debug("[filter] {} [value] {}", filter, value)
            if filter == "pure_match" and value in ['yes', '']:
                finalfilters['bools'].append(Q(has_pure_oai_match=True) )
            if filter == "no_pure_match" or (filter == "pure_match" and value == 'no'):
                finalfilters['bools'].append((Q(
                    has_pure_oai_match=False
                ) | Q(has_pure_oai_match__isnull=True)))
            if filter == "has_pure_link" and value in ['yes', '']:
                finalfilters['bools'].append(Q(is_in_pure=True))
            if filter == "no_pure_link" or (filter == "has_pure_link" and value == 'no'):
                finalfilters['bools'].append((Q(is_in_pure=False) | Q(is_in_pure__isnull=True)))
            if filter == "hasUTKeyword":
                finalfilters['bools'].append(Q(
                pure_entries__ut_keyword__gt=''
                ))
            if filter == "hasUTKeywordNLA":
                finalfilters['bools'].append(Q(pure_entries__ut_keyword="NLA"))
            if filter == 'openaccess':
                if value in ['yes', '', 'true', 'True', True]:
                    finalfilters['bools'].append(Q(is_oa=True))
                if value in ['no', 'false', 'False', False]:
                    finalfilters['bools'].append(Q(is_oa=False))
            if filter == 'apc':
                finalfilters['bools'].append((Q(apc_listed_value__isnull=False) & ~Q(apc_listed_value='')))
            if filter == 'TCS' or filter == 'EE':
                # get all papers where at least one of the authors has a linked AFASData entry that has 'is_tcs'=true
                # also get all papers where at least one of the authors has a linked UTData entry where current_group is in TCSGROUPS or TCSGROUPSABBR
                if filter == 'TCS':
                    grouplist = TCSGROUPS + TCSGROUPSABBR
                elif filter == 'EE':
                    grouplist = EEGROUPS + EEGROUPSABBR
                q_expressions = Q()
                for group_abbr in grouplist:
                    q_expressions |= (
                            Q(
                                authorships__author__utdata__employment_data__contains={'group': group_abbr}
                            )
                        &
                            Q(
                                authorships__author__utdata__employment_data__contains={'faculty':'EEMCS'}
                            )
                    )
                    
                finalfilters['groups'].append(((Q(authorships__author__utdata__current_group__in=grouplist) | q_expressions)) & Q(
                        authorships__author__utdata__current_faculty='EEMCS'
                    ))
            
            if filter == 'author':
                author = Author.objects.get(name = name)
                finalfilters['authors'].append(Q(
                    authorships__author=author
                ))
            if filter == 'group':
                group = value
                finalfilters['groups'].append(Q(
                    authorships__author__utdata__current_group=group
                ))

            if filter == 'start_date':
                start_date = value
                # should be str in format YYYY-MM-DD
                datefmt=re.compile(r"^\d{4}-\d{2}-\d{2}$")
                if datefmt.match(start_date):
                    finalfilters['dates'].append(Q(
                        date__gte=start_date
                    ))
                else:
                    raise ValueError("Invalid start_date format")

            if filter == 'end_date':
                end_date = value

                # should be str in format YYYY-MM-DD
                datefmt=re.compile(r"^\d{4}-\d{2}-\d{2}$")
                if datefmt.match(end_date):
                    finalfilters['dates'].append(Q(
                        date__lte=end_date
                    ))
                else:
                    raise ValueError("Invalid end_date format")

            if filter == 'type':
                itemtype = value
                ITEMTYPES = ['journal-article', 'proceedings', 'proceedings-article','book', 'book-chapter']
                if itemtype != 'other':
                    if itemtype == 'book' or itemtype == 'book-chapter':
                        finalfilters['types'].append(Q(Q(itemtype='book')|Q(itemtype='book-chapter')))
                    else:
                        finalfilters['types'].append(Q(itemtype=itemtype))
                else:
                    finalfilters['types'].append(~Q(
                        itemtype__in=ITEMTYPES
                    ))

            if filter == 'faculty':
                faculty=value
                if faculty in facultynamelist:
                    faculty = faculty.upper()
                    finalfilters['faculties'].append(Q(
                        authorships__author__utdata__current_faculty=faculty
                    ))
                else:
                    authors = Author.objects.filter(utdata__isnull=False).filter(~Q(utdata__current_faculty__in=facultynamelist)).select_related('utdata')
                    finalfilters['faculties'].append(Q(authorships__author__in=authors))

            if filter == 'taverne_passed':
                date = datetime.today().strftime('%Y-%m-%d')
                finalfilters['bools'].append(Q(
                    taverne_date__lt=date
                ))
        boolfilter = Q()
        groupfilter = Q()
        facultyfilter= Q()
        typefilter = Q()
        datefilter = Q()
        authorfilter = Q()

        for qfilt in finalfilters['bools']:
            boolfilter = boolfilter & qfilt
        for qfilt in finalfilters['types']:
            typefilter = typefilter | qfilt
        for qfilt in finalfilters['groups']:
            groupfilter = groupfilter | qfilt
        for qfilt in finalfilters['faculties']:
            facultyfilter = facultyfilter | qfilt
        for qfilt in finalfilters['dates']:
            datefilter = datefilter & qfilt
        for qfilt in finalfilters['authors']:
            authorfilter = authorfilter | qfilt

        finalfilter = boolfilter & typefilter & groupfilter & facultyfilter & datefilter & authorfilter
        newlist = listpapers.filter(finalfilter)
        return newlist

    def aggregrateStats(listpapers):
        stats = listpapers.aggregate(
            num=Count("id"),
            numoa=Count("id", filter=Q(is_oa=True)),
            numpure=Count("id", filter=Q(is_in_pure=True)),
            numpurematch=Count("id", filter=Q(has_pure_oai_match=True)),
            numarticles=Count("id", filter=Q(itemtype="journal-article")),
            articlesinpure=Count(
                "id", filter=Q(is_in_pure=True, itemtype="journal-article")
            ),
            articlesinpurematch=Count(
                "id", filter=Q(has_pure_oai_match=True, itemtype="journal-article")
            ),
            numarticlesoa=Count("id", filter=Q(is_oa=True, itemtype="journal-article")),
        )
        return stats

    def getStats(listpapers, stats=None):
        if not stats:
            stats = aggregrateStats(listpapers)

        stats["oa_percent"] = (
            round((stats["numoa"] / stats["num"]) * 100, 2) if stats["num"] else 0
        )
        stats["numpure_percent"] = (
            round((stats["numpure"] / stats["num"]) * 100, 2) if stats["num"] else 0
        )
        stats["oa_percent_articles"] = (
            round((stats["numarticlesoa"] / stats["numarticles"]) * 100, 2)
            if stats["numarticles"]
            else 0
        )
        stats["articlesinpure_percent"] = (
            round((stats["articlesinpure"] / stats["numarticles"]) * 100, 2)
            if stats["numarticles"]
            else 0
        )
        stats["numpurematch_percent"] = (
            round((stats["numpurematch"] / stats["num"]) * 100, 2)
            if stats["num"]
            else 0
        )
        stats["articlesinpurematch_percent"] = (
            round((stats["articlesinpurematch"] / stats["numarticles"]) * 100, 2)
            if stats["numarticles"]
            else 0
        )
        return stats

    def getcommonPrefetches(filterpapers):
        authorships_prefetch = Prefetch(
            "authorships",
            queryset=Authorship.objects.filter(paper__in=filterpapers).select_related(
                "author"
            ),
            to_attr="preloaded_authorships",
        )
        location_prefetch = Prefetch(
            "locations",
            queryset=Location.objects.filter(papers__in=filterpapers).select_related("source"),
            to_attr="preloaded_locations",
        )
        authors_and_affiliation_prefetch =Prefetch(
            'authors',
            queryset=Author.objects.filter(authorships__paper__in=filterpapers).distinct()
            .prefetch_related('affils').select_related('utdata'),
            to_attr="preloaded_authors",
        )
        return [
            authorships_prefetch,
            location_prefetch,
            authors_and_affiliation_prefetch,
        ]



    if isinstance(name, int):
        return getSinglePaper()
    elif filter == 'author':
        facultyname = name+" [Author]"
        filterpapers = Paper.objects.filter(authors__name=name).distinct().order_by("-modified")
        filter = [['all','']]
    elif name == "marked" or name == "Marked papers":
        facultyname = "Marked papers"
        filterpapers=Paper.objects.filter(view_paper__user=user).order_by("-modified")
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
            if name not in facultynamelist:
                facultyname = "Other groups"
                name = 'other'
            else:
                facultyname = name

            if isinstance(filter, str):
                filter = [[str(filter),""],['faculty',name]]
            if isinstance(filter, list):
                if ['faculty', name] not in filter:
                    filter.append(['faculty',name])
    listpapers = (
        filterpapers
        .prefetch_related(*getTablePrefetches(filterpapers))
        .annotate(
            marked=Exists(viewPaper.objects.filter(displayed_paper=OuterRef("pk")).select_related()),
        )
        .defer('abstract','keywords','pure_entries',
            'apc_listed_value', 'apc_listed_currency', 'apc_listed_value_eur', 'apc_listed_value_usd',
            'apc_paid_value', 'apc_paid_currency', 'apc_paid_value_eur', 'apc_paid_value_usd',
            'published_print', 'published_online', 'issued', 'published',
            'license', 'citations','pages','pagescount', 'volume','issue', 'journal'
            )
        .order_by('-year')
    )
    listpapers = applyFilter(listpapers, filter)
    stats = getStats(listpapers)
    return facultyname, stats, listpapers

def get_pure_entries(article_id, user):
    article=Paper.objects.get(pk=article_id)
    pure_entries = article.pure_entries.all()
    author_prefetch=Prefetch(
            'authors',
            queryset=Author.objects.filter(pure_entries__in=pure_entries).distinct()
            .prefetch_related('affiliations').select_related('utdata'),
        )
    pure_entries=pure_entries.prefetch_related(author_prefetch)

    return article, pure_entries

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
    article=Paper.objects.filter(pk=article_id).prefetch_related('authors').annotate(
            marked=Exists(viewPaper.objects.filter(displayed_paper=OuterRef("pk")).select_related()),
        ).first()
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

