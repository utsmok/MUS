from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from .models import Paper, viewPaper, Author
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist
from .data_add import addPaper
from .data_view import generateMainPage, getPapers, getAuthorPapers, open_alex_autocomplete, get_raw_data, generate_chart, read_log, generate_oa_chart
from django.conf import settings
from .data_helpers import processDOI
from django.views.decorators.cache import cache_page
from loguru import logger
from datetime import datetime
from io import StringIO
import plotly.graph_objects as go
from rich import print
import ast


CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)



# TODO: Add caching
# TODO: implement messaging system to frontend -- with history?

# TODO: Fix articlenumber / pagenumber stuff
# TODO: Fix available locations/pdf
# TODO: Fix PureEntries view template

# TODO: run scheduled updates

# TODO: proper update bookmark count on frontend
# TODO: fix filtertable not working more than once
# TODO: add serverside rendering of tables? paginate, filter, sort
# TODO: get from apis: worldcat, semanticscholar, scopus, opencitations, orcid, zenodo, CORE/BASE

# TODO: easy/quick open or view pdf(s)
# TODO: add funding/grant data
# TODO: import DBLP papers to postgres from mongo
# TODO: import data from pure report -> authors + paperlist for tcs

# TODO: make plots page


@login_required
def home(request):
    logger.info("[url] / [user] {}", request.user.username)
    _, stats, _ = getPapers('marked', 'all', request.user)
    return render(request, "home.html", {"stats": stats})

@login_required
def dbinfo(request):
    logger.info("[url] /dbinfo [user] {}", request.user.username)
    total, faculties = generateMainPage(request.user)
    return render(request, "dbinfo.html", {"total": total, "faculties": faculties})

@login_required
def addarticle(request,doi):
    status, message, openalex_url = addPaper(doi, request.user)
    logger.info("addarticle [doi] {} [user] {} [status] {} [message] {}", doi, request.user.username, status, message)
    return render(request, 'message.html', {"status": status,"message":message, 'openalex_url': openalex_url, 'time': datetime.now().strftime("%H:%M:%S")})

@login_required
def searchpaper(request):
    query = request.GET.get('doi', '').strip()

    if not query or len(query) < 3:
        logger.info("searchpaper [query] |invalid| [user] {}",request.user.username)
        return render(request, 'search_results.html', {'db_items': [], 'db_count': 0, 'oa_items': [], 'oa_count': 0})

    logger.info("searchpaper [query] {} [user] {}",query, request.user.username)

    all_papers = Paper.objects.all().only('id','doi', 'title', 'openalex_url').prefetch_related('authors')

    if query.startswith('http') or query[0].isdigit() or 'doi' in query.lower():
        query = processDOI(query)
        query2 = query.replace('https://doi.org/', '')
        papers = all_papers.filter( Q(doi__icontains=query) | Q(title__icontains=query) | Q(doi__icontains=query2) | Q(title__icontains=query2))
    else:
        papers = all_papers.filter( Q(title__icontains=query) | Q(authors__name__icontains=query))

    papers_count = papers.count()
    papers = list(papers[:5])

    oa_items=[]
    oa_found_count=0
    oa_count=0
    oa_results = open_alex_autocomplete(query)
    if oa_results:
        oa_count=oa_results['count']
        for item in oa_results['results']:
            if item['id'] in [ paper.openalex_url for paper in papers ]:
                oa_found_count += 1
            elif all_papers.filter(openalex_url=item['id']).exists():
                oa_found_count += 1
            else:
                try:
                    oa_items.append({'item':item,'type':item['entity_type']})
                except Exception:
                    logger.warning('[searchpaper] error while trying to add oa_results to final list')
                    pass

    return render(request, 'search_results.html', {'db_items': papers, 'db_count': papers_count, 'oa_items': oa_items, 'oa_count': oa_count, 'oa_found_count': oa_found_count})

@login_required
def single_article(request, article_id):
    '''
    Returns page with all the details for requested Paper id
    '''
    logger.info("[url] /article/{} [user] {}", article_id, request.user.username)
    _, _, paper = getPapers(article_id, "all", request.user)
    response = render(request, "single_article.html", {"article": paper[0]})
    return response

@login_required
def single_article_pure_view(request, article_id):
    '''
    Returns page showing details for all PureEntry models linked to requested Paper id
    '''
    logger.info("[url] /pure_entries/{} [user] {}", article_id, request.user.username)
    article, pure_entries = Paper.objects.get_pure_entries(article_id)
    return render(request, "pure_entries.html", {"article": article, 'pure_entries': pure_entries})

def single_article_raw_data(request, article_id):
    '''
    gets data from mongodb linked to this paper
    '''
    logger.info("[url] /rawdata/{} [user] {}", article_id, request.user.username)
    article, fulljson, raw_data = get_raw_data(article_id, request.user)
    if not article:
        return render(request, "message.html", {"status": "danger", "message": f"Article with {article_id} not found"})
    if not raw_data:
        raw_data=[]
    if not fulljson:
        fulljson = {}
    return render(request, "rawdata.html", {"article": article, 'fulljson':fulljson, 'raw_data':raw_data})
def get_raw_data_json(request, article_id):
    '''
    same as single_article_raw_data but returns json instead of page
    '''
    logger.info("[url] /rawdatajson/{} [user] {}", article_id, request.user.username)
    article, fulljson, raw_data = get_raw_data(article_id, request.user)
    if not article:
        return JsonResponse({"message": f"Article with {article_id} not found"})

    content = StringIO()
    with content as f:
        f.write(fulljson)
        data = content.getvalue()

    response = HttpResponse(data, headers={
        "Content-Type": 'application/json',
        "Content-Disposition": f'attachment; filename="raw_json_{article_id}.json"',
    })
    return response
@login_required
def faculty(request, name="all", filter="all"):
    '''
    Returns a table with all papers for a specific faculty, or all papers, or non-faculty linked papers, or bookmarked papers for user.
    This is an ease-of-use function -- the filtering system could also be used.
    '''

    facultyname, stats, listpapers = getPapers(name, filter, request.user)

    logger.info(
        "[url] /faculty/{} [user] {}",
        name,
        request.user.username,
    )
    filter=filter

    response = render(
        request,
        "faculty.html",
        {"faculty": facultyname, "stats": stats, "articles": listpapers, "filter":filter},
    )

    return response


@login_required
def author(request, name):
    '''
    Returns a table with all papers for a specific author. Uses the same logic as the faculty views. Another convenience function.
    '''
    try:
        _, stats, listpapers = getAuthorPapers(name, request.user)
    except ObjectDoesNotExist:
        name = "Author {} not found" % name
        stats = {}
        listpapers = []

    logger.info("[url] /authorarticles/{} [user] {}", name, request.user.username)
    response = render(
    request,
    "faculty.html",
    {"faculty": name, "stats": stats, "articles": listpapers},)
    return response


@transaction.atomic
@login_required
def removemark(request, id="all"):
    '''
    Removes bookmark(s) for request.user. if id is "all", removes all bookmarks (default), otherwise only paper with id 'id'.
    TODO: move to viewPaperManager
    '''
    logger.info("removemark [id] {} [user] {}", id, request.user.username)
    if id == "all":
        id = "all papers"
        viewPaper.objects.filter(user=request.user).delete()
    else:
        viewPaper.objects.filter(
            displayed_paper=Paper.objects.get(pk=id), user=request.user
        ).delete()
    return JsonResponse(
        {
            "status": "success",
            "message": f"removed mark from {id} for user {request.user}",
        }
    )

@transaction.atomic
@login_required
def addmark(request, id):
    '''
    Adds bookmark for request.user for paper with id 'id'.
    TODO: move to viewPaperManager
    '''
    logger.info("addmark [id] {} [user] {}", id, request.user.username)
    viewPaper.objects.create(
        displayed_paper=Paper.objects.get(pk=id), user=request.user
    ).save()
    return JsonResponse(
        {"status": "success", "message": f"added mark to {id} for user {request.user}"}
    )

@login_required
def getris(request):
    '''
    returns a ris file with data for all papers marked by the user -> can be used to import data into pure.
    '''

    user = request.user
    filters = None
    if request.POST.items():
        for key, value in request.POST.items():
            try:
                if 'filters' in key:
                    filters = ast.literal_eval(value)
            except Exception:
                pass
    if filters:
        articles = Paper.objects.filter_by(filters)
    else:
        viewpapers = viewPaper.objects.filter(user=user)
        paperids = viewpapers.values_list('displayed_paper_id', flat=True)
        articles = Paper.objects.filter(pk__in=paperids)
    if not filters:
        filters='marked papers'
    logger.info("getris [# papers] {} [filters] {} [user] {}", articles.count(), filters, request.user.username)

    risfile = articles.exportris()
    contentdisp = f'attachment; filename="mus_ris_export_{user.username}_{datetime.now().strftime("%Y-%m-%d")}.ris"'
    response = HttpResponse(risfile, headers={
        "Content-Type": 'application/x-research-info-systems',
        "Content-Disposition": contentdisp,
    })

    return response

@login_required
def getcsv(request):
    '''
    returns a csv file with data for all papers marked by the user
    '''
    user = request.user
    filters = None
    if request.POST.items():
        for key, value in request.POST.items():
            try:
                if 'filters' in key:
                    filters = ast.literal_eval(value)
            except Exception:
                pass
    if filters:
        articles = Paper.objects.filter_by(filters)
    else:
        viewpapers = viewPaper.objects.filter(user=user)
        paperids = viewpapers.values_list('displayed_paper_id', flat=True)
        articles = Paper.objects.filter(pk__in=paperids)
    if not filters:
        filters='marked papers'

    logger.info("getcsv [# papers] {} [filters] {} [user] {}", articles.count(), filters, request.user.username)

    csvfile = articles.get_csv(papers=articles)
    contentdisp = f'attachment; filename="mus_csv_export_{user.username}_{datetime.now().strftime("%Y-%m-%d")}.csv"'
    response = HttpResponse(csvfile, headers={
        "Content-Type": 'text/csv',
        "Content-Disposition": contentdisp,
    })
    #for debugging the query:
    #response = render(request, "csv.html", {"csvfile": csvfile, "contentdisp": contentdisp})

    return response

@login_required
def filtertoolpage(request):
    logger.info("filtertools [user] {}", request.user.username)
    return render(request, "filtertools.html")


@login_required
def customfilter(request):
    '''
    Returns a table with papers based on requested filters.
    Needs more testing, code needs cleanup.
    '''
    message = ""
    filtermapping={
        "type_journal":'type',
        "type_conf":'type',
        "type_book":'type',
        "type_other":'type',
        "faculty_eemcs":'faculty',
        "faculty_bms":'faculty',
        "faculty_itc":'faculty',
        "faculty_et":'faculty',
        "faculty_tnw":'faculty',
        "is_oa":'openaccess',
        "has_apc":'apc',
        "taverne_passed":'taverne_passed',
        "group_tcs":'TCS',
        "group_ee":'EE',
        "has_pure_link":'has_pure_link',
        "in_pure":'pure_match',
        "no_pure_link":'no_pure_link',
        "not_in_pure":'no_pure_match',
    }
    if request.method == "POST":
        filters=[]

        for key, value in request.POST.items():
            usetypes = []
            if key == 'csrfmiddlewaretoken':
                continue
            if key in filtermapping:
                if value == 'true':
                    if filtermapping[key] != 'type' and filtermapping[key] != 'faculty':
                        filters.append([filtermapping[key],True])
                    if filtermapping[key] == 'type':
                        if key == 'type_journal':
                            usetypes.append('journal-article')
                        if key == 'type_conf':
                            usetypes.append('proceedings-article')
                            usetypes.append('proceedings')
                        if key == 'type_book':
                            usetypes.append('book')
                            usetypes.append('book-chapter')
                    else:
                        value=key.split('_')[1]
                        filters.append([filtermapping[key],value])
            if len(usetypes)>0:
                for t in usetypes:
                    filters.append(['type',t])

            if key == 'year_start':
                if value != '' and value is not None:
                    if len(value)==4:
                        if int(value) > 2000:
                            month = str(request.POST['month_start'])
                            passed=False
                            if month != '' and month is not None:
                                if int(month) > 0 and int(month) < 13:
                                    passed= True
                            if not passed:
                                month = '01'
                                message += "- Invalid start month, defaulting to January"
                            if len(month)==1:
                                month = '0'+month
                            filters.append(['start_date',"-".join([str(request.POST['year_start']),month,'01'])])
            if key == 'year_end':
                if value != '' and value is not None:
                    if len(value)==4:
                        if int(value) > 2000:
                            month = str(request.POST['month_end'])
                            passed=False
                            if month != '' and month is not None:
                                if int(month) > 0 and int(month) < 13:
                                    passed= True
                            if not passed:
                                month = '01'
                                message += "- Invalid end month, defaulting to January. "
                            if len(month)==1:
                                month = '0'+month
                            filters.append(['end_date',"-".join([str(request.POST['year_end']),month,'01'])])

        logger.info("customfilter [filters] {} [user] {}",filters, request.user.username)
        facultyname, stats, listpapers = getPapers('all', filters, request.user)
        return render(request, "faculty_table.html",{"faculty": facultyname, "stats": stats, "articles": listpapers, "filter":filters})

@login_required
def load_affils(request,author_id):
    affils = Author.objects.get_affiliations(author_id)
    logger.info("load_affils [author_id] {} [user] {}",author_id, request.user.username)
    return render(request, "affiliations.html",{"affiliations": affils, "author_id": author_id})


@login_required
def chart(request):
    logger.info("chart [parameters] {} [user] {}", request.POST, request.user.username)
    return render(request, "chart.html", {"chart": generate_chart(request.POST, request.user)})

def oa_chart(request):
    logger.info("oachart [user] {}", request.POST, request.user.username)
    return render(request, 'chart.html', {'chart': generate_oa_chart()})

@login_required
def customchart(request):
    '''
    Make a custom chart based on the user's selections
    request.POST contains the user's selections:
    - grouping: how to group the results
    - filters: uses the same logic as customfilter to generate the list of papers that contain the data for the chart

    returns a rendered chart
    '''
    fig = go.Figure()
    if request.method == "POST":
        filters = []
        grouping = []
        for key, value in request.POST.items():
            print(key, value)
            if key == 'csrfmiddlewaretoken':
                continue
            if key == 'grouping':
                # determine how to group the data
                grouping = value
            elif key == 'filters':
                # check if filters are valid, process them, and call getPapers with the filters
                for key, value in value.items():
                    filters.append((key, value))
                facultyname, stats, listpapers = getPapers('all', filters, request.user)
            else:
                print('unknown key', key)

    # determine the chart type based on grouping & filters
    # then generate the chart
    # export it to html & return the render
    chart = fig.to_html()

    return render(request, "chart.html", {"chart": chart})

@login_required
def viewlog(request, file='log'):
    if request.user.username != 'sam':
        logger.info("viewlog [user] {}",request.user.username)
    if file=='cron':
        filename = 'cron_update.log'
    if file=='log':
        filename = 'log_mus.log'
    if file=='dbupdates':
        filename = 'db_updates.log'
    return render(request, "viewlog.html", {"log": read_log(filename)})