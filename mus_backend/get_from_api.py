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
from pyalex import Works, Authors, Journals, config
import pyalex
from pymongo import MongoClient
from django.conf import settings
MONGOURL = getattr(settings, "MONGOURL")
APIEMAIL = getattr(settings, "APIEMAIL", "no@email.com")

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
def getItems(identifiers):
    '''
    If 1 or more items are not present in the main SQL database, use this function to add them.
    It will choose the data source(s) to use based on the identifier.

    Input:
    identifiers: a list of identifiers to retrieve data for, preferably in canonical format (see helpers.formatIdentifier)

    returns ??
    '''
    from .identifier import IdentifierFactory, Identifier
    id_factory = IdentifierFactory()

    results=[]
    ids=id_factory.create(identifiers)
    # Decide which data to pull from where
    return results

def getPureItems(years):
    def fillFromPure(year):

        '''
        Fill up the mongoDB with Pure entries for the given years.
        Gets data from the OAI-PMH endpoint of the UT's Pure instance.

        Parameters:
            year: integer representing the year to retrieve data for - e.g. 2019

        Returns:
            total: the number of entries added
        '''

        api_responses_pure = db["api_responses_pure"]
        total=0
        base_url = "https://ris.utwente.nl/ws/oai"
        metadata_prefix = "oai_dc"
        set_name = f"publications:year{year}"
        namespace = {
            "oai": "http://www.openarchives.org/OAI/2.0/",
            "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
        }
        total=0
        def fetch_records(url):
            response = requests.get(url)
            xml_data = response.text
            root = ET.fromstring(xml_data)
            return root, xml_data

        def process_records(records, xml,total):
            articles=[]
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

            # add the articles to mongodb
            api_responses_pure.insert_many(articles)
            total=total+len(articles)
            print(f"[{year}] {total} articles (+{len(articles)})")
            return total

        initial_url = (
            f"{base_url}?verb=ListRecords&metadataPrefix={metadata_prefix}&set={set_name}"
        )
        root, xml = fetch_records(initial_url)

        list_records = root.find("oai:ListRecords", namespace)
        try:
            total=process_records(list_records.findall("oai:record", namespace), xml,total)
        except Exception as e:
            print(f"[{year}] {e} while processing initial batch")
            pass
        resumption_token = root.find("oai:ListRecords/oai:resumptionToken", namespace)
        i = 1
        while resumption_token is not None:
            i = i + 1
            token_value = resumption_token.text
            next_url = f"{base_url}?verb=ListRecords&resumptionToken={token_value}"
            try:
                root, xml = fetch_records(next_url)
                list_records = root.find("oai:ListRecords", namespace)
                total=process_records(list_records.findall("oai:record", namespace), xml, total)
            except Exception as e:
                print(f"[{year}] {e} while processing batch {i}")
            resumption_token = root.find("oai:ListRecords/oai:resumptionToken", namespace)


        return total

    results=[]

    for year in years:
        t=fillFromPure(year)
        results.append({"year":year, "articles":t})
    return results

def getDataCiteItems(years):
    api_responses_datacite = db["api_responses_datacite"]
    total=0
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
            api_responses_datacite.insert_one(tmp)
            total=total+1
            if total%25==0:
                print(f"{total} DataCite items added")

    return total

def getCrossrefWorks(years):
    api_responses_crossref = db["api_responses_crossref"]
    pagesize=100
    results=cr.works(filter = {'from-pub-date':f'{years[-1]}-01-01','until-pub-date': f'{years[0]}-12-31'}, query_affiliation='twente', cursor = "*", limit = pagesize, cursor_max=100000)
    total=0
    for page in results:
        articles=[]
        for article in page['message']['items']:
            articles.append(article)
        total=total+len(articles)
        api_responses_crossref.insert_many(articles)
        print(f'{total} Crossref articles [+{len(articles)}]')

def getOpenAlexWorksInstituteID(years):
    api_responses_openalex = db["api_responses_utasinstitute_openalex"]
    query = (
            Works()
            .filter(
                institutions={"id":"I94624287"},
                publication_year="|".join([str(x) for x in years]),
            )
    )
    total=0
    for article in batched(chain(*query.paginate(per_page=100, n_max=None)),100):
        api_responses_openalex.insert_many(article)
        total=total+len(article)
        print(f'{total} OpenAlex articles')
    print(f'{total} OpenAlex articles added filtering on institution id I94624287 (UTwente)')

def getOpenAlexWorksROR(years):
    api_responses_openalex = db["api_responses_utasinstitute_openalex"]
    query = (
            Works()
            .filter(
                institutions={"ror":"https://ror.org/006hf6230"},
                publication_year="|".join([str(x) for x in years]),
            )
    )
    total=0
    for article in batched(chain(*query.paginate(per_page=100, n_max=None)),100):
        api_responses_openalex.insert_many(article)
        total=total+len(article)
        print(f'{total} OpenAlex articles')
    print(f'{total} OpenAlex articles added filtering on https://ror.org/006hf6230 (UTwente)')

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
        authors_openalex = db["api_responses_UT_authors_openalex"]

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

    MONGODB = MongoClient('mongodb://smops:bazending@192.168.2.153:27017/')
    db=MONGODB["mus"]
    authors_openalex = db["api_responses_authors_openalex"]
    authors, utauthors=getAuthorListFromDB()
    print(f'adding {len(authors)} non-UT authors')
    print(f'of which {len(utauthors)} UT authors')
    batch=[]
    total=0
    for author in authors:
        batch.append(author)
        if len(batch)==50:
            authorids="|".join(batch)
            query = Authors().filter(openalex=authorids)
            for author in batched(chain(*query.paginate(per_page=100, n_max=None)),100):
                authors_openalex.insert_many(author)
            total=total+50
            print(f'added {total} non-UT authors')
            batch=[]
            authorids=""

    authorids="|".join(batch)
    query = Authors().filter(openalex=authorids)
    for author in batched(chain(*query.paginate(per_page=100, n_max=None)),100):
        authors_openalex.insert_many(author)
    total=total+len(batch)
    print(f'added {total} non-UT authors to DB')

def getOpenAlexJournalData():
    def getJournalListFromDB():
        import time
        journals={}
        i=0
        api_responses_openalex = db["api_responses_openalex"]
        start=time.time()
        for article in api_responses_openalex.find():
            i=i+1
            if i%1000==0:
                print(f'journals for {i} articles processed in {int(time.time()-start)}s')
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
    print(f'adding {len(journals)} journals')
    batch=[]
    total=0
    for journal in journals.keys():
        batch.append(journal)
        if len(batch)==50:
            journalids="|".join(batch)
            query = Journals().filter(openalex=journalids)
            for author in batched(chain(*query.paginate(per_page=100, n_max=None)),100):
                journals_openalex.insert_many(author)
            total=total+50
            print(f'added {total} journals')
            batch=[]
            journalids=""

    journalids="|".join(batch)
    query = Journals().filter(openalex=journalids)
    for author in batched(chain(*query.paginate(per_page=100, n_max=None)),100):
        journals_openalex.insert_many(author)
    total=total+len(batch)
    print(f'added {total} journals to DB')

'''def getAll():
    years=[2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016, 2015, 2014, 2013, 2012, 2011, 2010]
    getOpenAlexWorksROR(years) #or use getOpenAlexWorksInstituteID(years)
    getPureItems(years)
    getDataCiteItems(years)
    getCrossrefWorks(years)
    ...

'''