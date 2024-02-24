import logging
from .models import (
    Location,
    Author,
    Journal,
    Paper,
    Authorship,
    Keyword,
    viewPaper,
    DealData,

)
from django.db.models import Count, Q, Prefetch, Exists, OuterRef
from .data_helpers import TCSGROUPS, TCSGROUPSABBR
import regex as re
from datetime import datetime
logger = logging.getLogger(__name__)


def generateMainPage(user):
    """
    returns:
    dict total with keys articles = num of papers and oa = % of papers where is_oa==true
    list faculties, each entry is dict with keys name,articles,oa; self explanatory
    """
    facultynamelist = ["EEMCS", "BMS", "ET", "ITC", "TNW", "marked", "Other groups"]
    total = {
        "articles": 0,
        "oa": 0,
        "numoa": 0,
        "inpure": 0,
        "inpure_percent": 0,
        "inpurematch": 0,
    }
    faculties = []
    for faculty in facultynamelist:
        facultyname, stats, listpapers = getPapers(faculty, "all", user)
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
    return total, faculties


def getPapers(name, filter="all", user=None):
    if isinstance(name, int):
        logger.info("getpaper [id] %s [user] %s", name, user.username)
    else:
        logger.info("getpapers [name] %s [filter] %s [user] %s", name, filter, user.username)

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

    def applyFilter(listpapers, filter, value=""):
        logger.debug("[filter] %s [value] %s", filter, value)
        if filter == "pure_match":
            newlist = listpapers.filter(has_pure_oai_match=True)
        if filter == "no_pure_match":
            newlist = listpapers.filter(
                has_pure_oai_match=False
            ) | listpapers.filter(has_pure_oai_match__isnull=True)
        if filter == "has_pure_link":
            newlist = listpapers.filter(is_in_pure=True)
        if filter == "no_pure_link":
            newlist = listpapers.filter(is_in_pure=False) | listpapers.filter(is_in_pure__isnull=True)
        if filter == "hasUTKeyword":
            newlist = listpapers.filter(
            pure_entries__ut_keyword__gt=''
            ).distinct().prefetch_related('pure_entries').order_by("title")
        if filter == "hasUTKeywordNLA":
            newlist = listpapers.filter(pure_entries__ut_keyword="NLA").prefetch_related('pure_entries')
        if filter == 'openaccess':
            newlist = listpapers.filter(is_oa=True)
        if filter == 'apc':
            newlist = listpapers.filter(apc_listed_value__isnull=False).exclude(apc_listed_value='')
        if filter == 'TCS':
            # get all papers where at least one of the authors has a linked AFASData entry that has 'is_tcs'=true
            # also get all papers where at least one of the authors has a linked UTData entry where current_group is in TCSGROUPS or TCSGROUPSABBR
            tcscheck = TCSGROUPS + TCSGROUPSABBR
            newlist = listpapers.filter(
                Q(authorships__author__afas_data__is_tcs=True)
                | Q(authorships__author__utdata__current_group__in=tcscheck)
            )
        if filter == 'author':
            author = Author.objects.get(name = name)
            newlist = listpapers.filter(
                authorships__author=author
            )
        if filter == 'group':
            group = value
            newlist = listpapers.filter(
                authorships__author__utdata__current_group=group
            )
        if filter == 'journal':
            journal = Journal.objects.get(name = value)
            newlist = listpapers.filter(
                journal=journal
            ).select_related('journal')
        if filter == 'publisher':
            publisher = DealData.objects.get(publisher = value).prefetch_related('journal')
            journals = publisher.journal.all()
            newlist = listpapers.filter(
                journal__in=journals
            ).select_related('journal')
        if filter == 'start_date':
            start_date = value
            # should be str in format YYYY-MM-DD
            datefmt=re.compile(r"^\d{4}-\d{2}-\d{2}$")
            if datefmt.match(start_date):
                newlist = listpapers.filter(
                    date__gte=start_date
                )
            else:
                raise ValueError("Invalid start_date format")

        if filter == 'end_date':
            end_date = value

            # should be str in format YYYY-MM-DD
            datefmt=re.compile(r"^\d{4}-\d{2}-\d{2}$")
            if datefmt.match(end_date):
                newlist = listpapers.filter(
                    date__lte=end_date
                )
            else:
                raise ValueError("Invalid end_date format")

        if filter == 'type':

            itemtype = value
            ITEMTYPES = ['journal-article', 'proceedings-article','book', 'book-chapter']
            if itemtype != 'other':
                if itemtype == 'book' or itemtype == 'book-chapter':
                    newlist = listpapers.filter(Q(itemtype='book')|Q(itemtype='book-chapter'))
                else:
                    newlist = listpapers.filter(itemtype=itemtype)
            else:
                newlist = listpapers.exclude(
                    itemtype__in=ITEMTYPES
                )

        if filter == 'faculty':
            faculty=value
            if faculty in facultynamelist:
                faculty = faculty.upper()
                newlist = listpapers.filter(
                    authorships__author__utdata__current_faculty=faculty
                )
            else:
                authors = Author.objects.filter(utdata__isnull=False).filter(~Q(utdata__current_faculty__in=facultynamelist)).select_related('utdata')
                newlist = listpapers.filter(authorships__author__in=authors)

        if filter == 'taverne_passed':
            date = datetime.today().strftime('%Y-%m-%d')
            newlist = listpapers.filter(
                taverne_date__lt=date
            )

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
        keyword_prefetch = Prefetch(
            "keywords",
            queryset=Keyword.objects.filter(papers__in=filterpapers),
            to_attr="keywords_prefetch",
        )
        journal_prefetch = Prefetch(
            "journal",
            queryset=Journal.objects.filter(papers__in=filterpapers).select_related(),
            to_attr="journal_prefetch",
        )
        authors_and_affiliation_prefetch =Prefetch(
            'authors',
            queryset=Author.objects.filter(authorships__paper__in=filterpapers).distinct()
            .prefetch_related('affiliations').select_related('utdata'),
            to_attr="preloaded_authors",
        )
        return [
            authorships_prefetch,
            location_prefetch,
            keyword_prefetch,
            journal_prefetch,
            authors_and_affiliation_prefetch,
        ]

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

    if isinstance(name, int):
        return getSinglePaper()
    elif filter == 'author':
        facultyname = name+" [Author]"
        filterpapers = Paper.objects.all()
    elif name == "marked" or name == "Marked papers":
        facultyname = "Marked papers"
        filterpapers=Paper.objects.filter(view_paper__user=user).order_by("-modified")
    else:
        filterpapers = Paper.objects.all().distinct()
        if name == "all" or name == "All items":
            facultyname = "All MUS papers"
        elif name not in facultynamelist:
            facultyname = "Other groups"
            if isinstance(filter, str):
                filter = {str(filter):'','faculty':'other'}
        else:
            if isinstance(filter, str):
                filter = {str(filter):'','faculty':name}
            facultyname = name
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
    if isinstance(filter, str):
        if filter != "all":
            listpapers = applyFilter(listpapers,filter)
    elif isinstance(filter, list):
        for f in filter:
            if isinstance(f, list):
                if f[0]!='all':
                    listpapers = applyFilter(listpapers, f[0], f[1])
    elif isinstance(filter, dict):
        for f, value in filter.items():
            if f != 'all':
                listpapers = applyFilter(listpapers, f, value)

    stats = getStats(listpapers)
    return facultyname, stats, listpapers

def get_pure_entries(article_id, user):
    article=Paper.objects.get(pk=article_id)
    pure_entries = article.pure_entries.all()
    author_prefetch=Prefetch(
            'authors',
            queryset=Author.objects.filter(pure_entries__in=pure_entries).distinct()
            .prefetch_related('affiliations').select_related('utdata'),
            to_attr="preloaded_authors",
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
    logger.info("authorpapers [author] %s [user] %s", display_name, user.username)
    return getPapers(display_name, 'author', user)
