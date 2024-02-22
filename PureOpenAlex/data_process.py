from django.conf import settings

import pyalex
from pyalex import Works, Sources
from datetime import timedelta, date
import urllib.request
from bs4 import BeautifulSoup
from urllib.request import urlopen
from nameparser import HumanName
from .namematcher import NameMatcher
import time
import asyncio
import requests
from unidecode import unidecode
import re
import logging
from .models import (
    UTData,
    Organization,
    Author,
    Paper,
    Journal,
    DealData,
    Location,
    Source,
    Keyword,
)
from django.db import transaction
from habanero import Crossref
import httpx

from .data_helpers import (
    determineIsInPure,
    convertToEuro,
    invertAbstract,
    calculateUTkeyword,
    TWENTENAMES,
    ORCID_RECORD_API,
    APILOCK,
)

SCORETHRESHOLD = 0.98  # for namematching authors on UT peoplepage
APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")
pyalex.config.email = APIEMAIL

name_matcher = NameMatcher()
logger = logging.getLogger(__name__)

@transaction.atomic
def processPaperData(work):
    """
    This function processes the given OpenAlex Work data and saves it to the database.
    The processing is split out into separate functions to make it easier to test and debug.

    Args:
        Work (pyalex Work object): the result of a pyalex Works() query.
    Returns:
        None -- all data is inserted directly into the database.
    """
    logger.info("Starting processData for doi %s", work["doi"])
    timelist = []
    start_time_total = time.time()

    start_time = time.time()
    crossrefdata = getCrossrefData(work)
    logger.debug("Got Crossrefdata for doi %s", work["doi"])
    timelist.append(
        f"       getCrossrefData: {time.strftime('%M:%S',time.gmtime(time.time()-start_time))} s"
    )

    try:
        pagescount = (
            1 + int(work["biblio"]["last_page"]) - int(work["biblio"]["first_page"])
        )
    except Exception:
        pagescount = None

    if crossrefdata["pages"] is not None:
        pages = crossrefdata["pages"]
    else:
        if pagescount is not None:
            if pagescount > 1:
                pages = f"{work['biblio']['first_page']}-{work['biblio']['last_page']}"
            elif pagescount == 1:
                pages = f"{work['biblio']['first_page']} (article number)"
            else:
                pages = None
        else:
            pages = ""

    start_time = time.time()
    apc_data = getAPCData(work)

    logger.debug("Got APCdata for doi %s", work["doi"])
    timelist.append(
        f"            getAPCData: {time.strftime('%M:%S',time.gmtime(time.time()-start_time))} s"
    )

    start_time = time.time()
    journal = getJournals(work)

    logger.debug("Got Journaldata for doi %s", work["doi"])
    timelist.append(
        f"        getJournalData: {time.strftime('%M:%S',time.gmtime(time.time()-start_time))} s"
    )

    if not DealData.objects.filter(journal=journal).exists():
        start_time = time.time()
        getOADealData(journal)

        logger.debug("Got OADealdata for doi %s", work["doi"])
        timelist.append(
            f"           getOADealData: {time.strftime('%M:%S',time.gmtime((time.time()-start_time)))}"
        )

    start_time = time.time()
    authorships = getAuthorships(work)

    logger.debug("Got Authorships for doi %s", work["doi"])
    timelist.append(
        f"         getAuthorships: {time.strftime('%M:%S',time.gmtime(time.time()-start_time))} s"
    )

    start_time = time.time()
    keywords = getKeywords(work)

    logger.debug("Got Keywords for doi %s", work["doi"])
    timelist.append(
        f"            getKeywords: {time.strftime('%M:%S',time.gmtime(time.time()-start_time))} s"
    )


    license = ""
    openaccess = ""
    if work["best_oa_location"] is not None:
        license = (
            work["best_oa_location"].get("license")
            if work["best_oa_location"].get("license") is not None
            else ""
        )
    if work["open_access"] is not None:
        openaccess = (
            work["open_access"].get("oa_status")
            if work["open_access"].get("oa_status") is not None
            else ""
        )

    dates = [
        date
        for date in [
            crossrefdata["issued"],
            crossrefdata["published"],
            crossrefdata["published_online"],
            crossrefdata["published_print"],
        ]
        if date is not None
    ]
    if dates != []:
        earliestdate = min(dates)
        tavernedate = earliestdate + timedelta(days=184)
    else:
        earliestdate = None
        tavernedate = None

    logger.debug(
        "earliest found date is %s, calculated tavernedate is %s",
        earliestdate,
        tavernedate,
    )

    logger.debug(
        "initial data processed for doi %s, now inserting paper in db", work["doi"]
    )
    with transaction.atomic():
        paper, created = Paper.objects.get_or_create(
            openalex_url=work.get("id"),
            title=work.get("title"),
            doi=work.get("doi"),
            year=work.get("publication_year"),
            citations=int(work.get("cited_by_count", 0))
            if work.get("cited_by_count") is not None
            else 0,
            openaccess=openaccess,
            primary_link=work["primary_location"].get("landing_page_url")
            if work["primary_location"].get("landing_page_url") is not None
            else "",
            itemtype=work.get("type_crossref")
            if work.get("type_crossref") is not None
            else "",
            date=work.get("publication_date")
            if work.get("publication_date") is not None
            else "",
            language=work.get("language") if work.get("language") is not None else "",
            abstract=invertAbstract(work.get("abstract_inverted_index"))
            if work.get("abstract_inverted_index") is not None
            else "",
            pages=pages,
            pagescount=pagescount,
            volume=work["biblio"].get("volume")
            if work["biblio"].get("volume") is not None
            else "",
            issue=work["biblio"].get("issue")
            if work["biblio"].get("issue") is not None
            else "",
            is_oa=bool(work["open_access"].get("is_oa"))
            if work["open_access"].get("is_oa") is not None
            else False,
            license=license,
            pdf_link_primary=work["primary_location"]["pdf_url"]
            if work["primary_location"]["pdf_url"] is not None
            else "",
            journal=journal,
            apc_listed_value=apc_data[0],
            apc_listed_currency=apc_data[1],
            apc_listed_value_usd=apc_data[2],
            apc_listed_value_eur=apc_data[3],
            apc_paid_value=apc_data[4],
            apc_paid_currency=apc_data[5],
            apc_paid_value_usd=apc_data[6],
            apc_paid_value_eur=apc_data[7],
            issued=crossrefdata["issued"],
            published=crossrefdata["published"],
            published_online=crossrefdata["published_online"],
            published_print=crossrefdata["published_print"],
            taverne_date=tavernedate,
        )
        if created:
            paper.save()

    start_time = time.time()
    locations = getLocations(work)

    logger.debug("Got locations for doi %s", work["doi"])
    timelist.append(
        f"            getLocations: {time.strftime('%M:%S',time.gmtime(time.time()-start_time))} s"
    )

    for location in locations:
        with transaction.atomic():
            paper.locations.add(location)

    with transaction.atomic():
        paper.is_in_pure = determineIsInPure(paper)

    """ TODO: add this to crossrefdata and integrate in authorships
        crossrefdata['author'] - list with dicts
        each item is 1 author
        each author can have keys:
            given, family, sequence, affiliation (list), ORCID, authenticated-orcid,
    """

    for author in authorships:
        with transaction.atomic():
            paper.authors.add(
                author["author"],
                through_defaults={
                    "paper": paper,
                    "position": author["position"],
                    "corresponding": author["corresponding"],
                },
            )

    for keyword in keywords:
        with transaction.atomic():
            paper.keywords.add(keyword)

    with transaction.atomic():
        paper.ut_keyword_suggestion = calculateUTkeyword(work, paper, authorships)

    with transaction.atomic():
        paper.save()

    timelist.append(
        f"    Total time taken:     {time.strftime('%M:%S',time.gmtime((time.time() - start_time_total)))} s"
    )
    logger.info(
        "%s for Paper with doi %s and title %s",
        timelist[-1],
        work["doi"],
        work["display_name"],
    )
    logger.debug("Time taken for each step:")

    for timing in timelist:
        if "Total" in timing:
            logger.debug(
                "------------------------------------------------------------------"
            )
        logger.debug(timing)


def getLocations(work):
    locations = []
    if work["best_oa_location"] is not None:
        best_oa = work["best_oa_location"]
    else:
        best_oa = None
    if work["primary_location"] is not None:
        primary = work["primary_location"]
    else:
        primary = None

    for location in work["locations"]:
        is_primary = False
        is_best_oa = False
        if location == primary:
            is_primary = True
        if location == best_oa:
            is_best_oa = True
        if location["license"] is not None:
            license = location["license"]
        else:
            license = ""
        if location["is_accepted"] is not None:
            is_accepted = location["is_accepted"]
        else:
            is_accepted = None
        if location["pdf_url"] is not None:
            pdf_url = location["pdf_url"]
        else:
            pdf_url = ""
        if location["is_oa"] is not None:
            is_oa = location["is_oa"]
        else:
            is_oa = None
        if location["is_published"] is not None:
            is_published = location["is_published"]
        else:
            is_published = None
        if location["landing_page_url"] is not None:
            landing_page_url = location["landing_page_url"]
        else:
            landing_page_url = ""

        if location["source"] is not None:
            source = location["source"]
            APILOCK.acquire()
            fullsource = Sources()[source["id"]]
            try:
                APILOCK.release()
            except Exception:
                pass
            if fullsource["homepage_url"] is not None:
                homepage_url = fullsource["homepage_url"]
            else:
                homepage_url = ""
            if fullsource["host_organization_name"] is not None:
                host_org = fullsource["host_organization_name"]
            else:
                host_org = ""
            if fullsource["issn_l"] is not None:
                e_issn = fullsource["issn_l"]
            else:
                e_issn = ""
            issn = e_issn
            if fullsource["issn"] is not None:
                for issn in fullsource["issn"]:
                    if issn != e_issn:
                        issn = issn
                        break
            with transaction.atomic():
                sourceclass, created = Source.objects.get_or_create(
                    openalex_url=fullsource["id"],
                    homepage_url=homepage_url,
                    host_org=host_org,
                    is_in_doaj=fullsource["is_in_doaj"],
                    type=fullsource["type"],
                    display_name=fullsource["display_name"],
                    issn=issn,
                    e_issn=e_issn,
                )
                if created:
                    sourceclass.save()

            # commented out because its taking a lot of time
            """
            data={}
            if fullsource['x_concepts'] is not None:
                data['concepts']=fullsource['x_concepts']
                concepts=prepConcepts(data)
                db_lock.acquire()
                for concept in concepts:
                    sourceclass.concepts.add(concept)
                sourceclass.save()
                db_lock.release()

            """
        else:
            sourceclass = None

        with transaction.atomic():
            locationclass, created = Location.objects.get_or_create(
                is_accepted=is_accepted,
                is_oa=is_oa,
                is_published=is_published,
                license=license,
                landing_page_url=landing_page_url,
                source=sourceclass,
                is_primary=is_primary,
                is_best_oa=is_best_oa,
                pdf_url=pdf_url,
            )
            if created:
                locationclass.save()
            locations.append(locationclass)

    return locations


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
            logger.error("Failed to store journal data for doi %s ", work["doi"])
            logger.debug("Journal data: %s", work["primary_location"]["source"])
            journal = None

    return journal


def getAuthorships(work):
    authorships = []
    utchecklist = []
    orcidlist = []
    for entry in work["authorships"]:
        parsedname = HumanName(unidecode(entry["author"]["display_name"]))
        with transaction.atomic():
            tempAuthor, created = Author.objects.get_or_create(
                name=entry["author"]["display_name"],
                orcid=entry["author"]["orcid"],
                first_name=parsedname.first,
                last_name=parsedname.last,
                middle_name=parsedname.middle,
                defaults={"is_ut": False},
                openalex_url=entry["author"]["id"],
            )
            if created:
                tempAuthor.save()

        if entry["institutions"]:
            for institute in entry["institutions"]:
                if (
                    "Twente" in institute["display_name"]
                    and tempAuthor not in utchecklist
                ):
                    utchecklist.append(tempAuthor)
                country_code = institute.get("country_code", "")
                created = False
                tempaffl = None
                if institute["display_name"] in TWENTENAMES:
                    with transaction.atomic():
                        tempaffl, created = Organization.objects.get_or_create(
                            name="University of Twente",
                            ror="https://ror.org/006hf6230",
                            type="education",
                            country_code="NL",
                        )
                        if created:
                            tempaffl.data_source = "OpenAlex"
                            tempaffl.save()
                        tempAuthor.affiliations.add(tempaffl)
                elif Organization.objects.filter(
                    name=institute["display_name"]
                ).exists():
                    try:
                        currorg = Organization.objects.get(
                            name=institute["display_name"]
                        )
                        if currorg.ror == "" or currorg.ror is None:
                            currorg.ror = institute.get("ror", "")
                        if currorg.type == "" or currorg.type is None:
                            currorg.type = institute.get("type", "")
                        if currorg.country_code == "" or currorg.country_code is None:
                            currorg.country_code = country_code
                        with transaction.atomic():
                            currorg.save()
                            tempaffl = currorg
                            tempAuthor.affiliations.add(tempaffl)
                    except Exception:
                        logger.error(
                            "Org %s already exists, multiple times. Needs manual fix.",
                            institute["display_name"],
                        )
                else:
                    try:
                        with transaction.atomic():
                            tempaffl, created = Organization.objects.get_or_create(
                                name=institute["display_name"],
                                country_code=institute.get("country_code", ""),
                                ror=institute.get("ror", ""),
                                type=institute.get("type", ""),
                            )
                            if created:
                                tempaffl.data_source = "OpenAlex"
                                tempaffl.save()
                            tempAuthor.affiliations.add(tempaffl)
                    except Exception as e:
                        logger.error("Failed to store affiliation data: %s", e)

        if tempAuthor.orcid:
            orcidlist.append(tempAuthor)

        authorships.append(
            {
                "position": entry["author_position"],
                "corresponding": entry["is_corresponding"],
                "author": tempAuthor,
            }
        )

    orcidresult = asyncio.run(getORCIDData(orcidlist, utchecklist))

    for entry in orcidresult:
        utchecklist += entry["utchecklist"]
        utchecklist = list(set(utchecklist))
        if len(entry["affiliations"]) > 0:
            for affiliation in entry["affiliations"]:
                if (
                    not entry["author"]
                    .affiliations.filter(name=affiliation["name"])
                    .exists()
                ):
                    with transaction.atomic():
                        tempaffl, created = Organization.objects.get_or_create(
                            name=affiliation["name"],
                            country_code=affiliation.get("country_code", ""),
                            data_source="ORCID",
                        )
                        if created:
                            tempaffl.save()
                        entry["author"].affiliations.add(tempaffl)

    if utchecklist:
        utdata = asyncio.run(getUTPeoplePageData(utchecklist))
        for match in utdata:
            if not match["match"]:
                continue
            with transaction.atomic():
                match["author"].is_ut = True
                match["author"].save(update_fields=["is_ut"])
            try:
                if len(match["departments"]) == 0:
                    current_faculty = ""
                    current_group = ""
                    employment_data = {}
                else:
                    current_faculty = match["departments"][0]['faculty_abbr']
                    current_group = match['departments'][0]['department']
                    if len(match["departments"]) == 1:
                        employment_data = {'faculty':match["departments"]['faculty_abbr'],'group':match['departments']['department']}
                    else:
                        empllist=[]
                        for entry in match["departments"]:
                            empllist.append({'faculty':entry['faculty_abbr'],'group':entry['department']})
                        employment_data = {'employment':empllist}

                with transaction.atomic():
                    newutdata, created = UTData.objects.get_or_create(
                        employee=match["author"],
                        email=match["email"],
                        avatar=match["avatar"],
                        current_position=match["job_title"],
                        current_group=current_group,
                        current_faculty=current_faculty,
                        employment_data=employment_data
                    )
                    if created:
                        newutdata.save()


            except Exception as e:
                logger.error(
                    f"Error when adding UTData for author {match['author'].name}: {e}"
                )

    return authorships


'''
CHANGE to OpenAlex Topics instead of Concepts
def getConcepts(work):
    """
    Generates a list of Concept objects based on the given work.

    Args:
        work (dict): A dictionary containing information about the work.

    Returns:
        list: A list of Concept objects generated from the work.
    """
    conceptlist = []
    for concept in work["concepts"]:
        with transaction.atomic():
            tempconcept, created = Concept.objects.get_or_create(
                concept=concept["display_name"],
                level=concept["level"],
                score=concept["score"],
            )
            if created:
                tempconcept.data_source = "OpenAlex"
                tempconcept.save()
            conceptlist.append(tempconcept)
    return conceptlist'''


def getKeywords(work):
    """
    Generate a list of keywords for a given work.

    Parameters:
    - work (dict): The work object containing keyword data.

    Returns:
    - keywords (list): A list of dictionaries representing keywords.
    Each dictionary contains the following keys:
    - 'keyword' (str): The keyword string.
    - 'score' (float): The relevance of the keyword.
    """
    keywords = []
    for keyword in work["keywords"]:
        with transaction.atomic():
            tempKeyword, created = Keyword.objects.get_or_create(
                keyword=keyword["keyword"], score=keyword["score"]
            )
            if created:
                tempKeyword.data_source = "OpenAlex"
                tempKeyword.save()
            keywords.append(tempKeyword)
    return keywords


def getOpenAccessData():
    """
    Retrieves open access data for a given year.

    Returns:
        A tuple containing the total number of publications, the number of open access publications, the number of closed publications, and the year.
    """
    year = date.today().year
    results, meta = (
        Works()
        .filter(
            authorships={"institutions": {"ror": "006hf6230"}},
            publication_year=year,
            is_paratext="false",
            type="article",
        )
        .group_by("is_oa")
        .get(return_meta=True)
    )
    total = meta["count"]
    numoa = results[0]["count"]
    numclosed = results[1]["count"]

    return (total, numoa, numclosed, year)


def getOADealData(journal):
    """
    Retrieves Open Access data from the UT journal browser @ library.wur.nl.
    Scrapes the search engine using bs4.
    Adds the data directly to the journal object.

    Input: Django journal-object that needs deal data.

    """

    soup = {}
    journalapc = []
    journal_title = journal.name
    paging = 0
    query = (
        'https://library.wur.nl/WebQuery/utbrowser?q="'
        + urllib.parse.quote(f"""{journal_title}""")
        + f'"&wq_srt_desc=refs-and-pubs/referenties/aantal&wq_ofs={paging}&wq_max=200'
    )
    page = urlopen(query)
    html = page.read().decode("utf-8")
    soup[journal_title] = BeautifulSoup(html, "html.parser")
    try:
        max = int(
            soup[journal_title]
            .find("div", class_="navbar-brand")
            .contents[0]
            .split("/")[-1]
        )
    except Exception:
        # no results?
        return None
    else:
        try:
            while paging < max and journalapc == []:
                query = (
                    'https://library.wur.nl/WebQuery/utbrowser?q="'
                    + urllib.parse.quote(f"""{journal_title}""")
                    + f'"&wq_srt_desc=refs-and-pubs/referenties/aantal&wq_ofs={paging}&wq_max=200'
                )
                page = urlopen(query)
                html = page.read().decode("utf-8")
                soup[journal_title] = BeautifulSoup(html, "html.parser")
                titles = [
                    x.contents
                    for x in soup[journal_title].find_all("a", title="more info")
                ]
                apc_deal = [
                    x.contents
                    for x in soup[journal_title].find_all("a", class_="apc_discount")
                ]
                oa_types = [
                    x["title"]
                    for x in soup[journal_title].find_all(
                        "li", class_="open_access opendialog_helpbusinessmodel"
                    )
                ]
                urls = [
                    x["href"]
                    for x in soup[journal_title].find_all("a", class_="apc_discount")
                ]
                keywords = [
                    x.contents
                    for x in soup[journal_title].find_all("div", class_="keywords")
                ]
                publisher = [
                    x.contents
                    for x in soup[journal_title].find_all("div", class_="author")
                ]
                issns = [
                    x.contents
                    for x in soup[journal_title].find_all("div", class_="issns")
                ]

                for title, apc, keyword, publish, issn, url, oa_type in zip(
                    titles, apc_deal, keywords, publisher, issns, urls, oa_types
                ):
                    if title[0].lower() == journal.name.lower():
                        if keyword == []:
                            keyword = ""
                        journalapc.append(
                            {
                                "title": title[0],
                                "APCDeal": apc[0],
                                "publisher": publish[0],
                                "keywords": keyword,
                                "issn": issn[0].strip("ISSN:"),
                                "journal_browser_url": "".join(
                                    ["https://library.wur.nl/WebQuery/", url]
                                ),
                                "oa_type": oa_type,
                            }
                        )
                        break
                    else:
                        continue

                if max - paging > 200:
                    paging = paging + 200
                else:
                    paging = paging + (max - paging)
        except Exception:
            return None

    for dealdata in journalapc:
        if dealdata["title"].lower() == journal.name.lower():
            if dealdata["APCDeal"] is not None:
                with transaction.atomic():
                    deal, created = DealData.objects.get_or_create(
                        deal_status=dealdata["APCDeal"],
                        publisher=dealdata["publisher"],
                        jb_url=dealdata["journal_browser_url"],
                        oa_type=dealdata["oa_type"],
                    )
                    if created:
                        deal.save()
                    deal.journal.add(journal)

                    journal.publisher = dealdata["publisher"]
            else:
                continue
            '''if dealdata["keywords"] != "" and dealdata["keywords"] is not None:
                keywords = dealdata["keywords"][0].split("-")
                for keyword in keywords:
                    try:
                        with transaction.atomic():
                            keyword = keyword.strip()
                            (
                                journalkeyword,
                                created,
                            ) = JournalKeyword.objects.get_or_create(keyword=keyword)
                            if created:
                                journalkeyword.save()
                            journal.keywords.add(journalkeyword)
                    except Exception:
                        pass'''
            journal.save()

            break


async def getUTPeoplePageData(authors):
    logger.debug("getting UTPeoplePageData for %s authors.", len(authors))

    async def getData(author):
        logger.debug("retrieving ut people page data for author %s", author.name)
        orig_name = re.sub(r"\W+", " ", author.name)
        name = HumanName(unidecode(orig_name))
        url = "https://people.utwente.nl/data/search"
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Host": "people.utwente.nl",
            "Referer": "https://people.utwente.nl",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br",
        }
        async with httpx.AsyncClient() as client:
            r = await client.get(url, params={"query": name.last}, headers=headers)

        data = r.json()
        return await processUTPeoplePageData(author, name, data["data"])

    async def processUTPeoplePageData(author, origname, data):
        output = {"match": False, "author": author}
        highscore = 0
        for entry in data:
            name = entry["name"] if entry["name"] is not None else ""
            jobtitle = entry["jobtitle"] if entry["jobtitle"] is not None else ""
            avatar = entry["avatar"] if entry["avatar"] is not None else ""
            profile_url = entry["profile"] if entry["profile"] is not None else ""
            email = entry["email"] if entry["email"] is not None else ""
            deptlist = []
            for dept in entry["organizations"]:
                dept_faculty = (
                    dept["department"] if dept["department"] is not None else ""
                )
                dept_name = dept["section"] if dept["section"] is not None else ""
                deptlist.append({"department": dept_name, "faculty_abbr": dept_faculty})
            procname = HumanName(unidecode(name))
            score = name_matcher.match_names(
                origname.first + " " + origname.last,
                procname.first + " " + procname.last,
            )

            if score > SCORETHRESHOLD and score > highscore:
                output = {
                    "match": True,
                    "author": author,
                    "name": name,
                    "job_title": jobtitle,
                    "avatar": avatar,
                    "profile_url": profile_url,
                    "email": email,
                    "departments": deptlist,
                }
                highscore = score
        return output

    tasks = []
    for author in authors:
        task = asyncio.create_task(getData(author))
        tasks.append(task)

    results = await asyncio.gather(*tasks)
    return results


async def getORCIDData(authors, utchecklist):
    logger.debug("getting ORCIDData for %s authors.", len(authors))

    async def apiCall(author, utchecklist):
        logger.debug(" retrieving ORCID data for author %s", author.name)
        affiliations = []
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url=requests.utils.requote_uri(
                        ORCID_RECORD_API + author.orcid.split("orcid.org/")[1]
                    ),
                    headers={"Accept": "application/json"},
                )
            if response.status_code != 200:
                raise Exception(f"ORCID API response code {response.status_code}")
            else:
                result = response.json()
                for affiliation in result["activities-summary"]["employments"][
                    "affiliation-group"
                ]:
                    orgname = (
                        affiliation["summaries"][0]["employment-summary"][
                            "organization"
                        ]["name"]
                        or ""
                    )
                    orgcountry = (
                        affiliation["summaries"][0]["employment-summary"][
                            "organization"
                        ]["address"]["country"]
                        or ""
                    )
                    if orgname in TWENTENAMES:
                        affiliations.append(
                            {
                                "name": "University of Twente",
                                "ror": "https://ror.org/006hf6230",
                                "type": "education",
                                "country_code": "NL",
                            }
                        )
                        if author not in utchecklist:
                            utchecklist.append(author)
                    else:
                        affiliations.append(
                            {
                                "name": orgname,
                                "country_code": orgcountry,
                                "data_source": "ORCID",
                            }
                        )
                return {
                    "author": author,
                    "affiliations": affiliations,
                    "utchecklist": utchecklist,
                }

        except Exception as e:
            logger.error(
                f"Error while fetching ORCID data for author {author.name}: {e}"
            )
            return {
                "author": author,
                "affiliations": affiliations,
                "utchecklist": utchecklist,
            }

    tasks = []
    results = []
    async with asyncio.TaskGroup() as tg:
        for author in authors:
            temptask = tg.create_task(apiCall(author, utchecklist))
            tasks.append(temptask)
    for task in tasks:
        results.append(task.result())
    return results


def getCrossrefData(work):
    """
    Grabs crossref data based on DOI, returns the data that could be useful as a dict back to the main function.
    """
    cr = Crossref(mailto=APIEMAIL)
    crossrefdata = {}
    try:
        doi = work["doi"].split("org/")[1]
    except Exception:
        doi = work["doi"]
    try:
        res = cr.works(ids=[doi])
    except Exception:
        res = None
    if isinstance(res, dict) and res["message-type"] == "work":
        crossrefdata = res["message"]
        response = crossrefdata
    else:
        crossrefdata = None
        pages = None
        published_print = None
        issued = None
        published = None
        published_online = None
        crossrefdata = {
            "response": None,
            "pages": pages,
            "published_print": published_print,
            "issued": issued,
            "published": published,
            "published_online": published_online,
        }
        return crossrefdata
    """
        l=0
        for x in crossrefdata.keys():
            if len(x)>l:
                l=len(x)

        for x in crossrefdata.keys():
            sep="-"*(l-len(x))
            print(f'{x} {sep} {crossrefdata[x]}')
    """
    """
    crossrefdata['author'] - list with dicts
        each item is 1 author
        each author can have keys:
            given, family, sequence, affiliation (list), ORCID, authenticated-orcid,

    crossrefdata['pages'] - pages in format I need, can be used instead of calculation in main function

    fields with date info:
    crossrefdata['published-print']
    crossrefdata['license']
    crossrefdata['issued']
    crossrefdata['published']
    crossrefdata['published-online']

    crossrefdata['subject'] has keywords?
    """
    pages = None
    try:
        if crossrefdata["pages"] is not None and crossrefdata["pages"] != "":
            pages = crossrefdata["pages"]
    except Exception:
        pass
    try:
        if crossrefdata["page"] is not None and crossrefdata["page"] != "":
            pages = crossrefdata["page"]
    except Exception:
        pass
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

    crossrefdata = {
        "response": response,
        "pages": pages,
        "published_print": published_print,
        "issued": issued,
        "published": published,
        "published_online": published_online,
    }
    return crossrefdata
