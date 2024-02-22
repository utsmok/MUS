from django.shortcuts import render
from django.http import JsonResponse
from .models import Paper, viewPaper
from django.contrib.auth.decorators import login_required
import logging
from django.db import transaction
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist
from .data_add import addPaper
from .data_repair import removeDuplicates
from .data_view import generateMainPage, getPapers, getAuthorPapers, open_alex_autocomplete
from django.conf import settings
from .data_helpers import processDOI
from django.views.decorators.cache import cache_page

CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)
logger = logging.getLogger(__name__)

@cache_page(CACHE_TTL)
@login_required
def home(request):
    logger.info("[url] / [user] %s", request.user.username)
    total, faculties = generateMainPage(request.user)
    return render(request, "home.html", {"total": total, "faculties": faculties})

@login_required
def addarticle(request,doi):
    logger.info("addarticle [doi] %s [user] %s", doi, request.user.username)
    status = addPaper(
            doi,
            event=None,
            people=True,
            recheck=False,
            viewpaper=True,
            user=request.user,
        )
    return JsonResponse({"status": status})

@login_required
def searchpaper(request):
    query = request.GET.get('doi', '').strip()

    if not query or len(query) < 3:
        logger.info("searchpaper [query] |invalid| [user] %s",request.user.username)

        return render(request, 'search_results.html', {'db_items': [], 'db_count': 0, 'oa_items': [], 'oa_count': 0})
    
    logger.info("searchpaper [query] %s [user] %s",query, request.user.username)
    
    all_papers = Paper.objects.all().only('id','doi', 'title', 'openalex_url')

    if query.startswith('http') or query[0].isdigit() or 'doi' in query.lower():
        query = processDOI(query)
        query = query.replace('https://doi.org/', '')
        papers = all_papers.filter( Q(doi__icontains=query) | Q(title__icontains=query))
    else:
        papers = all_papers.filter( Q(title__icontains=query))

    papers_count = papers.count()
    papers = list(papers[:5])

    oa_results = open_alex_autocomplete(query)
    oa_count=oa_results['count']
    oa_items=[]
    oa_found_count=0

    for item in oa_results['results']:
        if item['id'] in [ paper.openalex_url for paper in papers ]:
            oa_found_count += 1
        elif all_papers.filter(openalex_url=item['id']).exists():
            oa_found_count += 1
        else:
            oa_items.append({'item':item,'type':oa_results['type'][0]})

    return render(request, 'search_results.html', {'db_items': papers, 'db_count': papers_count, 'oa_items': oa_items, 'oa_count': oa_count, 'oa_found_count': oa_found_count})

@login_required
def delete_duplicates(request):
    logger.info("[url] /delete_duplicates [user] %s", request.user.username)
    removeDuplicates()
    message = "Succesfully removed duplicates."
    return JsonResponse({"status": "success", "message": message})

@login_required
def single_article(request, article_id):
    logger.info("[url] /article/%s [user] %s", article_id, request.user.username)
    beep, boop, paper = getPapers(article_id, "all", request.user)
    response = render(request, "single_article.html", {"article": paper[0]})
    return response

@cache_page(CACHE_TTL)
@login_required
def faculty(request, name="all", filter="all"):
    facultyname, stats, listpapers = getPapers(name, filter, request.user)
    logger.info(
        "[url] /faculty/%s [user] %s",
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
    #get all papers by author and show them using the faculty view
    try:
        display_name, stats, listpapers = getAuthorPapers(name, request.user)
    except ObjectDoesNotExist:
        name = "Author %s not found" % name
        stats = {}
        listpapers = []

    logger.info("[url] /authorarticles/%s [user] %s", name, request.user.username)
    response = render(
    request,
    "faculty.html",
    {"faculty": name, "stats": stats, "articles": listpapers},)
    return response

@login_required
def facultypaginator(request, name="all", filter="all", sort="year"):
    from django.core.paginator import Paginator

    logger.info("[url] /facultypage/%s [user] %s", name, request.user.username)

    facultyname, stats, listpapers = getPapers(name, filter, request.user)
    paginator = Paginator(listpapers, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    response = render(
        request,
        "faculty_paginator.html",
        {"faculty": facultyname, "stats": stats, "articles": page_obj},
    )
    return response

@transaction.atomic
@login_required
def removemark(request, id="all"):
    logger.info("removemark [id] %s [user] %s", id, request.user.username)
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
    logger.info("addmark [id] %s [user] %s", id, request.user.username)
    viewPaper.objects.create(
        displayed_paper=Paper.objects.get(pk=id), user=request.user
    ).save()
    return JsonResponse(
        {"status": "success", "message": f"added mark to {id} for user {request.user}"}
    )

@login_required
@cache_page(CACHE_TTL)
def customfilter(request):
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
        "has_pure_link":'has_pure_link',
        "in_pure":'pure_match',
        "no_pure_link":'no_pure_link',
        "not_in_pure":'no_pure_match',
    }
    if request.method == "POST":
        filters=[]

        for key, value in request.POST.items():
            print(key, value)
            if key == 'csrfmiddlewaretoken':
                continue
            if key in filtermapping:
                if value == 'true':
                    if filtermapping[key] != 'type' and filtermapping[key] != 'faculty':
                        filters.append([filtermapping[key],True])
                    else:
                        value=key.split('_')[1]
                        filters.append([filtermapping[key],value])
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
        logger.info("customfilter [filters] %s [user] %s",filters, request.user.username)
        print(filters)
        facultyname, stats, listpapers = getPapers('all', filters, request.user)

        print('rendering page')
        return render(request, "faculty.html",{"faculty": facultyname, "stats": stats, "articles": listpapers, "filter":filters}) 
