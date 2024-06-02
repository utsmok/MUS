import marimo

__generated_with = "0.6.11"
app = marimo.App(width="medium")


@app.cell
def __():
    ''' This sets up the Django environment '''
    import os
    import django
    from django.db.models import Count, Q, Prefetch, Exists, OuterRef
    from collections import defaultdict

    PROJECTPATH = ""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mus.settings")
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"  # https://docs.djangoproject.com/en/4.1/topics/async/#async-safety
    django.setup()

    from django.conf import settings
    from loguru import logger
    import asyncio
    from pymongo import MongoClient
    from PureOpenAlex.models import DBUpdate

    MONGOURL = getattr(settings, "MONGOURL")

    MONGODB = MongoClient(MONGOURL)
    db=MONGODB["mus"]
    return (
        Count,
        DBUpdate,
        Exists,
        MONGODB,
        MONGOURL,
        MongoClient,
        OuterRef,
        PROJECTPATH,
        Prefetch,
        Q,
        asyncio,
        db,
        defaultdict,
        django,
        logger,
        os,
        settings,
    )


@app.cell
def __(e, process_cerif, time):
    # Testing retrieval of cerif data from oai_pmh endpoint
    import httpx
    import xmltodict

    def get_results(url:str) -> list[dict]:
        def fetch_response(url):
            try:
                r = httpx.get(url)
                parsed = xmltodict.parse(r.text)
                return parsed['OAI-PMH']['ListRecords']
            except Exception as e:
                print(f'error fetching {url}: {e}')
                return None
        results = []
        resume_url = url.split('&metadataPrefix')[0]
        while True:
                response = fetch_response(url)
                if not response:
                    time.sleep(5)
                    continue
                items = response.get('record')
                if not isinstance(items, list):
                    items = [items]
                for result in items:
                    results.append(result)
                if response.get('resumptionToken'):
                    resumetoken = response.get('resumptionToken').get('value')
                    url = f"{resume_url}&resumptionToken={resumetoken}"
                    print('would resume normally, now stopping')
                    return results
                else:
                    print(f'no more results for {url}')
                    return results

    base_url = 'https://ris.utwente.nl/ws/oai?verb=' # Use env variable

    # move to constants
    verbs = {
        'sets':'ListSets',
        'schemas':'ListMetadataFormats',
        'records':'ListRecords',
        'identify':'Identify',
    }

    # get repo info using identify
    info = {

    }
    # get available schemas
    schemes = {
    }
    # get available sets


    # let user pick which sets to retrieve
    sets = {'persons':'openaire_cris_persons', 'orgs':'openaire_cris_orgunits','works':'openaire_cris_publications','products':'openaire_cris_products', 'patents':'openaire_cris_patents', 'datasets':'datasets:all', 'projects':'openaire_cris_projects', 'funding':'openaire_cris_funding'}

    # let user pick the preferred scheme -- store globally?
    scheme = 'oai_cerif_openaire'
    finalresults = {}
    for type, set in sets.items():
        singleresult = {}
        url = f'https://ris.utwente.nl/ws/oai?verb=ListRecords&metadataPrefix={scheme}&set={set}'
        print(f'Grabbing records from {url}')
        singleresult['raw'] = get_results(url)
        singleresult['processed'] = process_cerif(type, singleresult['raw'])
        finalresults[type]=singleresult


    return (
        base_url,
        finalresults,
        get_results,
        httpx,
        info,
        scheme,
        schemes,
        set,
        sets,
        singleresult,
        type,
        url,
        verbs,
        xmltodict,
    )


@app.cell
def __():
    cerif_item_mapping = {
        'persons':'cerif:Person',
        'orgs': 'cerif:OrgUnit',
        'works': 'cerif:Publication',
        'products': 'cerif:Product',
        'patents': 'cerif:Patent',
        'datasets': 'cerif:Product',
        'projects': 'cerif:Project',
        'funding':'cerif:Funding',
    }
    cerif_mapping = {
        'persons':{
            'internal_repository_id':'@id',
            'name':'cerif:PersonName',
            'orcid':'cerif:ORCID',
            'scopus_id':'cerif:ScopusAuthorID',
            'scopus_affil_id':'cerif:ScopusAffiliationID',
            'affiliation': 'cerif:Affiliation',
            'researcher_id': 'cerif:ResearcherID',
            'isni': 'cerif:ISNI',
            'cris-id': 'cerif:CRIS-ID',
            'uuid':'cerif:UUID',
            'uri':'cerif:URI',
            'url':'cerif:URL',
        },
        'orgs': {},
        'works': {},
        'products': {},
        'patents': {},
        'datasets': {},
        'projects': {},
        'funding': {},
        'ec_funded_resources': {},
    }
    def check_keys(item, keylist, type):
        for k in item.keys():
            if k.startswith('cerif:') and k not in keylist:
                print(f'key found for {type} that is not currently stored: {k}')

    def process_cerif(type:str, data:list[dict]) -> list[dict]:
        # TODO: handle nested fieldnames
        results=[]
        mapping = cerif_mapping[type]
        keylist = mapping.values()
        for i in data:
            item = i['metadata'].get(cerif_item_mapping[type])
            result = {}
            for key, value in mapping.items():
                result[key]=item.get(value)
            check_keys(item, keylist, type)
            results.append(results)
        return results
    return cerif_item_mapping, cerif_mapping, check_keys, process_cerif


@app.cell
def __():
    import marimo as mo
    return mo,


if __name__ == "__main__":
    app.run()
