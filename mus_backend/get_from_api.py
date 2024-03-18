'''
This script contains everything needed to retrieve bibliographical data from external APIs.
Ex: Crossref, OpenAlex, Datacite, Openaire, Pure, ...

This data is initially stored in mongodb -- preferably the raw data received, or as close as possible.
Minor changes to the data will be made for convience.
This data can then be used to create the main entries in the SQL database,
and to check consistency or retrieve additional information later on.
To enable this, each SQL entry must have a mongo_link field pointing to the corresponding mongodb entry or entries.
'''
import requests
import xml.etree.ElementTree as ET
from more_itertools import batched
from itertools import chain
from habanero import Crossref
from pyalex import Works, Authors, Journals
import pyalex
from pymongo import MongoClient
from django.conf import settings
import httpx
from datetime import datetime, timedelta
from PureOpenAlex.models import Paper, DBUpdate
import xmltodict
from loguru import logger
from collections import defaultdict
from PureOpenAlex.data_add import addOpenAlexWorksFromMongo, addPureWorksFromMongo, addOpenAireWorksFromMongo
MONGOURL = getattr(settings, "MONGOURL")
APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")
OPENAIRETOKEN = getattr(settings, "OPENAIRETOKEN", "")

MONGODB=MongoClient(MONGOURL)
db=MONGODB["mus"]
pyalex.config.email = APIEMAIL
cr = Crossref(mailto=APIEMAIL)

UTKEYWORD=["UT-Hybrid-D", "UT-Gold-D", "NLA", "N/A OA procedure", "n/a OA procedure"]

start_year = 2000
end_year = 2030

for year in range(start_year, end_year + 1):
    UTKEYWORD.append(f"{year} OA procedure")

ITCKEYWORD=["ITC-ISI-JOURNAL-ARTICLE", "ITC-HYBRID", "ITC-GOLD"]


def getPureItems(years):
    logger.info("Retrieving new items from Pure OAI-PMH")

    def fillFromPure(year):

        '''
        Fill up the mongoDB with Pure entries for the given years.
        Gets data from the OAI-PMH endpoint of the UT's Pure instance.

        Parameters:
            year: integer representing the year to retrieve data for - e.g. 2019

        Returns:
            total: the number of entries added
        '''
        result={'ris_pages':[], 'ris_files':[], 'total':0}

        api_responses_pure = db["api_responses_pure"]
        base_url = "https://ris.utwente.nl/ws/oai"
        metadata_prefix = "oai_dc"
        set_name = f"publications:year{year}"
        namespace = {
            "oai": "http://www.openarchives.org/OAI/2.0/",
            "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        }

        def fetch_records(url):
            response = requests.get(url)
            xml_data = response.text
            root = ET.fromstring(xml_data)
            return root, xml_data

        def process_records(records, xml,total):
            articles=[]
            result={'ris_pages':[], 'ris_files':[], 'total':0}

            # First turn every article into from an XML to a dict
            for record in records:
                metadata = record.find("oai:metadata", namespace)
                dc = metadata.find("oai_dc:dc", namespace)
                d={}
                for element in dc:
                    name = element.tag
                    name = name.split("}")[-1]
                    if name not in d:
                        d[name]=[element.text]
                    else:
                        d[name].append(element.text)
                articles.append(d)
            # Then process the data in the article by iterating over the dict keys
            for article in articles:
                for tag in article.keys():
                    # 'subject' field contains SDGs and UT keywords, filter them out
                    if tag == 'subject':
                        sdgs=[]
                        utkeywords=[]
                        subjects=[]
                        itckeywords=[]

                        for subj in article[tag]:
                            if subj in UTKEYWORD:
                                utkeywords.append(subj)
                            elif subj in ITCKEYWORD:
                                itckeywords.append(subj)
                            elif '/dk/atira/pure/sustainabledevelopmentgoals/' in subj\
                            or (len(subj)<10 and str(subj).startswith('SDG')):
                                sdgs.append(subj)
                            else:
                                subjects.append(subj)
                        tmp={}
                        if len(sdgs)>0:
                            tmp['sdgs']=sdgs
                        if len(utkeywords)>0:
                            tmp['ut_keywords']=utkeywords
                        if len(subjects)>0:
                            tmp['subjects']=subjects
                        if len(itckeywords)>0:
                            tmp['itc_keywords']=itckeywords
                        article[tag]=tmp
                    # 'source' field is a multi-line string, split it into a list
                    if tag == 'source':
                        if '\\' in article[tag]:
                            article[tag]=article[tag].split('\\')

                    # 'identifier' field contains multiple types of identifiers, change from list into dict to make it easier to identify & access
                    if tag == 'identifier':
                        tmp={}
                        idmapping=[('research.utwente.nl','ris_page'), ('doi.org','doi'), ('ris.utwente.nl','ris_file'), ('scopus','scopus_link'), ('urn:ISBN','ISBN'), ('arxiv.org','arxiv_link')]
                        for id in article[tag]:
                            external=True
                            for item in idmapping:
                                if item[0] in id:
                                    external=False
                                    if item[1] not in tmp:
                                        tmp[item[1]]=[id]
                                    else:
                                        tmp[item[1]].append(id)
                            if external:
                                if 'external_link' not in tmp:
                                    tmp['external_link']=[id]
                                else:
                                    tmp['external_link'].append(id)
                        for key in tmp.keys():
                            if len(tmp[key])==1:
                                tmp[key]=tmp[key][0]
                        article['identifier']=tmp

                    # initially, each item was added as a list, if it's length is 1, change back to a string
                    if isinstance(article[tag],list) and len(article[tag])==1:
                        article[tag]=article[tag][0]

            # check if article is already in mongodb
            addarticles=[]
            for article in articles:
                if api_responses_pure.find_one({"identifier":{'ris_page':article["identifier"]["ris_page"]}}) or \
                    api_responses_pure.find_one({"identifier":{'ris_file':article["identifier"]["ris_file"]}}):
                        addarticles.append(article)
                        result['ris_files'].append(article["identifier"]["ris_file"])
                        result['ris_pages'].append(article["identifier"]["ris_page"])
                        result['total']+=1
            # add the articles to mongodb
            if len(addarticles)>0:
                api_responses_pure.insert_many(addarticles)
            return result

        initial_url = (
            f"{base_url}?verb=ListRecords&metadataPrefix={metadata_prefix}&set={set_name}"
        )
        root, xml = fetch_records(initial_url)

        list_records = root.find("oai:ListRecords", namespace)
        try:
            resultt=process_records(list_records.findall("oai:record", namespace), xml)
            result['total']+=resultt['total']
            result['ris_files'].extend(resultt['ris_files'])
            result['ris_pages'].extend(resultt['ris_pages'])
        except Exception as e:
            ...
        resumption_token = root.find("oai:ListRecords/oai:resumptionToken", namespace)
        i = 1
        while resumption_token is not None:
            i = i + 1
            token_value = resumption_token.text
            next_url = f"{base_url}?verb=ListRecords&resumptionToken={token_value}"
            try:
                root, xml = fetch_records(next_url)
                list_records = root.find("oai:ListRecords", namespace)
                resultt=process_records(list_records.findall("oai:record", namespace), xml)
                result['total']+=resultt['total']
                result['ris_files'].extend(resultt['ris_files'])
                result['ris_pages'].extend(resultt['ris_pages'])
            except Exception as e:
                ...
            resumption_token = root.find("oai:ListRecords/oai:resumptionToken", namespace)


        return result

    result = {'ris_files':[], 'ris_pages':[], 'total':0}
    for year in years:
        t=fillFromPure(year)
        result['ris_files'].extend(t['ris_files'])
        result['ris_pages'].extend(t['ris_pages'])
        result['total']+=t['total']
    return result if result['total']>0 else None

def getDataCiteItems(years):
    api_responses_datacite = db["api_responses_datacite"]
    result = {'dois':[], 'total':0}
    # the url to retrieve the api response from datacite
    # returns json, with {data:..., meta:..., links:...} as root.
    # data is a list of dicts, one per item.
    #The rest is not important for us; this query returns max 1000 items, and in feb 2024 there were 320 items total for this query.
    url = "https://api.datacite.org/dois?affiliation=true&query=creators.affiliation.affiliationIdentifier:%22https://ror.org/006hf6230%22&page[size]=1000"
    # retrieve json from url
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"DataCite API response code {response.status_code}")
    else:
        response_json = response.json()
        for item in response_json["data"]:
            tmp={}
            attrs=item['attributes']
            for key, value in attrs.items():
                if value is not None:
                    if isinstance(value, list):
                        if value!=[]:
                            tmp[key]=value
                    elif isinstance(value, dict):
                        if value!={}:
                            tmp[key]=value
                    elif isinstance(value, str):
                        if value != "":
                            tmp[key]=value

            tmp['id']=item['id']
            tmp['type']=item['type']
            tmp['relationships']=item['relationships']
            for key, value in tmp.items():
                if isinstance(value, list):
                    if len(value)==1:
                        tmp[key]=value[0]
            if api_responses_datacite.find_one({"id":tmp['id']}):
                continue
            else:
                api_responses_datacite.insert_one(tmp)
                result['dois'].append(tmp['id'])
                result['total']+=1

    return result if result['total']>0 else None
def getCrossrefWorks(years):
    api_responses_crossref = db["api_responses_crossref"]
    pagesize=100
    results=cr.works(filter = {'from-pub-date':f'{years[-1]}-01-01','until-pub-date': f'{years[0]}-12-31'}, query_affiliation='twente', cursor = "*", limit = pagesize, cursor_max=100000)
    result = {'dois':[], 'total':0}
    for page in results:
        articles=[]
        for article in page['message']['items']:
            articles.append(article)
        addarticles=[]
        for article in articles:
            if api_responses_crossref.find_one({"DOI":article['DOI']}):
                continue
            else:
                addarticles.append(article)
                result['dois'].append(article['DOI'])
        if addarticles:
            api_responses_crossref.insert_many(addarticles)
            result['total']+=len(addarticles)

    return result if result['total']>0 else None
def getOpenAlexWorks(years):
    logger.info("Retrieving OpenAlex API results for UT works")
    query = (
            Works()
            .filter(
                institutions={"ror":"https://ror.org/006hf6230"},
                publication_year="|".join([str(x) for x in years]),
            )
    )
    result = retrieveOpenAlexQuery(query)
    query = (
            Works()
            .filter(
                institutions={"id":"I94624287"},
                publication_year="|".join([str(x) for x in years]),
            )
    )
    result2= retrieveOpenAlexQuery(query)
    result['total']+=result2['total']
    result['openalex_url'].extend(result2['openalex_url'])
    result['new']+=result2['new']
    result['updated']+=result2['updated']
    result['skipped']+=result2['skipped']
    result['dois'].extend(result2['dois'])
    if result['total']>0:
        logger.info(f"[New     items] {result['new']}\n[Updated items] {result['updated']}\n-----------------------\n[Total   edits] {result['total']}")
        logger.info(f"\n[Skipped] {result['skipped']}")
        oaupdate = DBUpdate.objects.create(update_source="OpenAlex", update_type="getOpenAlexWorks", details=result)
        oaupdate.save()
    else:
        logger.info("no API updates from OpenAlex.")
def retrieveOpenAlexQuery(query):
    api_responses_openalex = db["api_responses_works_openalex"]
    result={'total':0,'new':0,'updated':0,'skipped':0,'openalex_url':[], 'dois':[]}
    for article in batched(chain(*query.paginate(per_page=100, n_max=None)),100):
        for art in article:
            doc = api_responses_openalex.find_one_and_replace({"id":art['id']}, art, upsert=True)
            if not doc:
                result['total'] += 1
                result['new'] += 1
                result['openalex_url'].append(art['id'])
                result['dois'].append(art['doi'])
            else:
                if art['updated_date'] != doc['updated_date']:
                    result['total'] += 1
                    result['updated'] += 1
                    result['openalex_url'].append(art['id'])
                    result['dois'].append(art['doi'])
                else:
                    result['skipped']+=1

    return result
def addItemsFromOpenAire():
    def get_openaire_token():
        refreshurl=f'https://services.openaire.eu/uoa-user-management/api/users/getAccessToken?refreshToken={OPENAIRETOKEN}'
        tokendata = httpx.get(refreshurl)
        return tokendata.json()

    result = {'openalex_url':[], 'dois':[], 'total':0}
    mongo_openaire_results=db['api_responses_openaire']
    tokendata=get_openaire_token()
    time = datetime.now()
    url = 'https://api.openaire.eu/search/researchProducts'
    headers = {
        'Authorization': f'Bearer {tokendata.get("access_token")}'
    }

    paperlist = Paper.objects.filter(year__gte=2023).values('doi','openalex_url')
    for paper in paperlist:
        if mongo_openaire_results.find_one({'id':paper['openalex_url']}):
            ...
            continue
        params = {'doi':paper['doi'].replace('https://doi.org/','')}
        try:
            r = httpx.get(url, params=params, headers=headers)
        except Exception as e:
            ...
        try:
            metadata = xmltodict.parse(r.text, attr_prefix='',dict_constructor=dict,cdata_key='text', process_namespaces=True).get('response').get('results').get('result').get('metadata').get('http://namespace.openaire.eu/oaf:entity').get('http://namespace.openaire.eu/oaf:result')
        except Exception as e:
            continue

        metadata['id']=paper['openalex_url']
        mongo_openaire_results.insert_one(metadata)
        result['total'] += 1
        result['openalex_url'].append(paper['openalex_url'])
        result['dois'].append(paper['doi'])
        if datetime.now()-time > timedelta(minutes=58):
            try:
                tokendata=get_openaire_token()
                headers = {
                    'Authorization': f'Bearer {tokendata.get("access_token")}'
                }
                time = datetime.now()
            except Exception as e:
                logger.error('exception {e} while retrieving OpenAire item {id}', e=e, id=metadata['id'])
                break



    return result if result['total']>0 else None
def getOpenAlexAuthorData():
    '''
    Go through all the works in the database and get detailed author data for each author.
    Use openalexID to get author data from openalex.
    Check if author has been added to database, if not, add it.
    If author is UT author, remember to also add UT author data -> get_from_scraper -> getUTPeoplePageData
    '''

    def getAuthorListFromDB():
        import time
        authorids=[]
        utauthorids=[]
        alreadyadded=[]
        i=0
        api_responses_openalex = db["api_responses_works_openalex"]
        authors_openalex = db["api_responses_authors_openalex"]
        authors_ut_openalex = db['api_responses_UT_authors_openalex']
        start=time.time()
        for article in api_responses_openalex.find():
            i=i+1
            if i%1000==0:
                print(f'authors for {i} articles processed in {int(time.time()-start)}s')
            for authorship in article['authorships']:
                id=authorship['author']['id']
                if not authors_openalex.find_one({'id':id}):
                    ut=False
                    if id not in utauthorids:
                        for affiliation in authorship['institutions']:
                            if 'twente' in affiliation['display_name'].lower() or '006hf6230' in affiliation['ror']:
                                ut=True
                                print('Found UT author that wasnt in DB:', id, authorship['author']['display_name'])
                                break
                        if ut:
                            utauthorids.append(id)
                        if id not in authorids:
                            authorids.append(id)
                else:
                    alreadyadded.append(id)


        print(f'{len(utauthorids)} UT authors')
        print(f'{len(authorids)} other authors')
        print(f'{len(alreadyadded)} already in DB')
        return authorids, utauthorids

    result={'total':0,'non-ut':0,'ut':0,'non_ut_openalex_urls':[], 'ut_openalex_urls':[]}

    MONGODB = MongoClient(MONGOURL)
    db=MONGODB["mus"]
    authors_openalex = db["api_responses_authors_openalex"]
    authors, utauthors=getAuthorListFromDB()
    result['non-ut']=len(authors)
    result['ut']=len(utauthors)
    result['non_ut_openalex_urls']=authors
    result['ut_openalex_urls']=utauthors
    print(f'adding {len(authors)} non-UT authors')
    print(f'of which {len(utauthors)} UT authors')
    batch=[]
    total=0
    i=0
    for grouping in [authors, utauthors]:
        i=i+1
        grouptype="non-UT"
        if i == 2:
            grouptype='UT'
        for author in grouping:
            batch.append(author)
            if len(batch)==50:
                authorids="|".join(batch)
                query = Authors().filter(openalex=authorids)
                for author in batched(chain(*query.paginate(per_page=100, n_max=None)),100):
                    authors_openalex.insert_many(author)
                total=total+50
                print(f'added {total} {grouptype} authors')
                batch=[]
                authorids=""

        authorids="|".join(batch)
        query = Authors().filter(openalex=authorids)
        for author in batched(chain(*query.paginate(per_page=100, n_max=None)),100):
            authors_openalex.insert_many(author)
        total=total+len(batch)

        result['total']=total
        logger.info(f'added {total} {grouptype} authors to mongoDB')
        if result['total']>0:
            dbupdate = DBUpdate.objects.create(update_source="OpenAlex", update_type="getOpenAlexAuthorData", details=result)
            dbupdate.save()
def getOpenAlexJournalData():
    def getJournalListFromDB():
        journals={}
        i=0
        api_responses_openalex = db["api_responses_openalex"]
        for article in api_responses_openalex.find():
            i=i+1
            if 'locations' in article:
                for location in article['locations']:
                    try:
                        if 'source' in location.keys():
                            if 'type' in location['source'].keys():
                                if location['source']['type']=='journal':
                                    journals[location['source']['id']]={'name':location['source']['display_name'],
                                                                        'issn-l':location['source']['issn_l']
                                                                        }
                    except AttributeError:
                        pass
        return journals

    journals_openalex = db["api_responses_journals_openalex"]
    journals=getJournalListFromDB()
    
    mongojournals=set()
    for journal in journals_openalex.find():
        mongojournals.add(journal['id'])
    
    
    for journal in journals.keys():
        if journal in mongojournals:
            del journals[journal]

    logger.info(f'looking up {len(journals)} journals')
    batch=[]
    total=0
    for journal in journals.keys():
        batch.append(journal)
        if len(batch)==50:
            journalids="|".join(batch)
            query = Journals().filter(openalex=journalids)
            for items in batched(chain(*query.paginate(per_page=100, n_max=None)),100):
                journals_openalex.insert_many(items)
            total=total+50
            batch=[]
            journalids=""

    journalids="|".join(batch)
    query = Journals().filter(openalex=journalids)
    for items in batched(chain(*query.paginate(per_page=100, n_max=None)),100):
        journals_openalex.insert_many(items)
    total=total+len(batch)
    logger.info(f'added {total} journals to DB')

    dbupdate = DBUpdate.objects.create(update_source="OpenAlex", update_type="getOpenAlexJournalData", details={'added':total, 'added_ids':list(journals.keys())})
    dbupdate.save()


