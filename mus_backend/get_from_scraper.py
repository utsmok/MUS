'''
This script reads in data from websites by using webscraping,
lightly processes it to structure the data, and stores it into mongoDB.

The data can then be used to create the main entries in the django SQL database.

Example data/sites:
people.utwente.nl for UT author data
journal browser for OA deal data

'''

import asyncio
import urllib.request
from bs4 import BeautifulSoup
from urllib.request import urlopen
from nameparser import HumanName
import httpx
from unidecode import unidecode
from fuzzywuzzy import process, fuzz
from pymongo import MongoClient
from django.conf import settings
from loguru import logger
from typing import Coroutine, List, Sequence

def _limit_concurrency(
    coroutines: Sequence[Coroutine], concurrency: int
) -> List[Coroutine]:
    """
    Decorate coroutines to limit concurrency.
    Enforces a limit on the number of coroutines that can run concurrently in higher
    level asyncio-compatible concurrency managers like asyncio.gather(coroutines) and
    asyncio.as_completed(coroutines).
    from https://gist.github.com/benfasoli/650a57923ab1951e1cb6355f033cbc8b
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def with_concurrency_limit(coroutine: Coroutine) -> Coroutine:
        async with semaphore:
            return await coroutine

    return [with_concurrency_limit(coroutine) for coroutine in coroutines]

MONGOURL = getattr(settings, "MONGOURL")

MONGODB = MongoClient(MONGOURL)
db=MONGODB["mus"]

async def getUTPeoplePageData(author, names):


    async def processUTPeoplePageData(author,searchname,data):
        """
        Asynchronously processes the retrieved UT people page data.

        Args:
            author: openalex ID of author.
            searchname: The name used in this search.
            data: The input data to be processed - consists of 1 entry per row in the search result

        Returns:
            A list of dicts containing the processed data.
        """
        output=[]
        foundnames=[]
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
                deptlist.append({"group": dept_name, "faculty": dept_faculty})
            tmp = {
                    "searchname": searchname,
                    "foundname": name,
                    "position": jobtitle,
                    "avatar_url": avatar,
                    "profile_url": profile_url,
                    "email": email,
                    "grouplist": deptlist,
                    "id":author
                }
            foundnames.append(name)
            output.append(tmp)
        return output
    
    """
    Asynchronous function to fetch data from UT people page for a single author.
    Params:
        author: author's openalex ID
        names: List[str] - list of names associated with this author
    Returns:
        dict or None - details for the best matched name, or None if no match is found
    """
    authors_ut_people = db["api_responses_UT_authors_peoplepage"]

    url = "https://people.utwente.nl/data/search"
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Host": "people.utwente.nl",
        "Referer": "https://people.utwente.nl",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
    }
    results=[]

    for name in names:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, params={"query": name}, headers=headers)
        except Exception:
            continue
        try:
            data = r.json()
        except Exception:
            continue
        try:
            tmp = await processUTPeoplePageData(author, name, data["data"])
            results.append(tmp)
        except Exception:
            continue
    if not results:
        return None
    
    foundnames={}
    for result in results:
        for item in result:
            if item["foundname"] not in foundnames.keys():
                foundnames[item["foundname"]]=item    
    score=0
    foundname=None

    for name in names:
        hname=HumanName(unidecode(name))
        checkname=f"{hname.last}, {hname.initials()} ({hname.first})"
        try:
            matchdata=process.extractOne(checkname, foundnames.keys())
            if matchdata[1]>score and matchdata[1]>80:
                cname=HumanName(matchdata[0])
                if fuzz.token_set_ratio(cname.last,hname.last)>95:
                    score=matchdata[1]
                    foundname=matchdata[0]
                else:
                    ... # matchscore above 80 but secondary score below 95: 'maybe' match?
                        # left blank: possible to add fallback matching options here.
            else:
                ... # matchscore below 80 OR there is already a higher score
                    # left blank; probably not needed to add code here.
        except Exception:
            # this is here for cases where there is no match found at all -- or if there's another error
            continue
    if not foundname:
        return None
    if foundname is not None:
        foundnames[foundname]["score"]=score
        logger.info(f'found match for {foundname}')
        authors_ut_people.insert_one(foundnames[foundname])
        return True

async def fillUTPeopleData():
    """
    This function fills the UT people data by:
    retrieving all unique authors from the 'api_responses_authors_openalex' collection
    then batches them for scraping while checking if there is already an entry for this ID in the target collection
    so if not in collection + unique: add to batch

    Then call getUTPeoplePageData on each batch, and add the results to the 'api_responses_authors_ut_people' collection

    return nothing; writes directly to mongodb.
    """

    authors_openalex = db["api_responses_UT_authors_openalex"]
    authors_ut_people = db["api_responses_UT_authors_peoplepage"]

    authors={}
    added=0
    already_added=0
    for author in authors_openalex.find():
        if author['id'] not in authors.keys():
            authors[author['id']]=author['display_name_alternatives']

    logger.info(f'checking {len(authors.keys())} ut authors if they already have UT people page data')
    finallist={}
    for key, value in authors.items():
        if not authors_ut_people.find_one({'id':key}):
            finallist[key]=value
        else:
            already_added=already_added+1
    logger.info(f'{already_added} ut authors already have UT people page data')
    logger.info(f'scraping data for {len(finallist.keys())} ut authors ')
    tasks=[]

    for author, names in finallist.items():
        tasks.append(getUTPeoplePageData(author,names))
        
    result = await asyncio.gather(*_limit_concurrency(tasks, concurrency=50))
    result = [item for item in result if item]
    added = len(result)
        
    logger.info(f"Done scraping people page. Already in db: {already_added}. Added: {added}. Failed: {len(finallist.keys())-added}")
    return {
        'update_source': "UTPeoplePage",
        'update_type': "fillUTPeopleData",
        'details': {
            'added_count': added,
            'skipped_count': already_added,
            'failed_count': len(finallist.keys()) - added
        }
    }


async def getJournalBrowserData(journals):
    async def getOADealData(journalid, journaldata):
        """
        Retrieves Open Access data from the UT journal browser @ library.wur.nl.
        Scrapes the search engine using bs4.
        Input: Journal name as string
        returns a list of dicts with data for found matches.

        """
        import time
        start=time.time()
        soup = {}
        journalapc = {}
        journal_title = journaldata['name']
        paging = 0
        j=0
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
        except Exception as e:
            # no results?
            print(f"error {e} at first soup parse")
            return None
        try:
            i=0
            while paging < max and journalapc == {}:
                i=i+1
                if i > 1:
                    print(f"[{journal_title}] page {i}")
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
                    j=j+1
                    if journal_title.lower() in title[0].lower():
                        if keyword == []:
                            keyword = ""

                        journalapc ={
                                "id":journalid,
                                "oa_display_name": journaldata['name'],
                                "oa_issn_l":journaldata['issn_l'],
                                "title": title[0],
                                "APCDeal": apc[0],
                                "publisher": publish[0],
                                "keywords": [x.strip() for x in keyword[0].split("-") if x.strip() != ""],
                                "issns": [x.strip() for x in issn[0].strip("ISSN:").strip(')').strip().split('(') if x.strip() != ""],
                                "journal_browser_url": "".join(
                                    ["https://library.wur.nl/WebQuery/", url]
                                ),
                                "oa_type": oa_type,
                                "scrape_time": time.time()-start,
                            }
                        break
                    else:
                        continue

                if max - paging > 200:
                    paging = paging + 200
                else:
                    paging = paging + (max - paging)
        except Exception as e:
            print(f"error {e} at last exception")
            return None
        return journalapc


    tasks=[]
    logger.info(f'scraping {len(journals.keys())} journals for dealdata')
    for key, value in journals.items():
        task = asyncio.create_task(getOADealData(key, value))
        tasks.append(task)

    results = await asyncio.gather(*tasks)
    return results

def fillJournalData():
    '''
    get all journals listed in journal collection
    for every journal scrape dealdata and add to new collection

    '''
    MONGODB = MongoClient('mongodb://smops:bazending@192.168.2.153:27017/')
    db=MONGODB["mus"]

    journals_openalex = db["api_responses_journals_openalex"]
    journals_dealdata_scraped = db["api_responses_journals_dealdata_scraped"]
    journals={}
    for journal in journals_openalex.find():
        journals[journal['id']]= {
            'name':journal['display_name'],
            'issn_l':journal['issn_l'],
        }

    journalbatch={}
    batchsize=25
    batchtotal=0
    total=0
    already_added=0
    logger.info(f"scraping & adding for {len(journals.keys())} journals")
    for key, value in journals.items():
        if journals_dealdata_scraped.find_one({'id':key}):
            already_added=already_added+1
            continue
        else:
            journalbatch[key]=value
        if len(journalbatch.keys()) == batchsize:
            result=asyncio.run(getJournalBrowserData(journalbatch))
            for item in result:
                if item is not None and isinstance(item,dict) and item != {}:
                    if 'scrape_time' in item.keys():
                        journals_dealdata_scraped.insert_one(item)
                        total=total+1
            batchtotal=batchtotal+batchsize
            logger.debug(f'added {total}/{batchtotal} rows of journal dealdata [{already_added} skipped]')
            journalbatch={}


    result=asyncio.run(getJournalBrowserData(journalbatch))
    for item in result:
        if item is not None and isinstance(item,dict) and not {}:
            journals_dealdata_scraped.insert_one(item)
            total=total+1
    batchtotal=batchtotal+len(journalbatch.keys())
    logger.debug(f'added {total}/{batchtotal} rows of journal dealdata [{already_added} skipped]')


