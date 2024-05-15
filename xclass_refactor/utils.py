
from collections import defaultdict
from xclass_refactor.mus_mongo_client import MusMongoClient
from datetime import datetime, date
import motor.motor_asyncio
from rich import print
async def get_mongo_collection_mapping():
    '''
    iterate over all mongodb collections to map the key/values in there
    '''
    def get_one(value):
        if value in ['', list, dict, str, None, datetime, date]:
            return str(type(value))
        elif value == []:
            return list
        elif value == {}:
            return dict
        elif isinstance(value, dict):
            if len(value.keys()) > 50:
                return dict
            result = {}
            for k, v in value.items():
                result[k] = get_one(v)
            return result
        elif isinstance(value, list):
            result = []
            tmp = []
            for v in value:
                retrieved = get_one(v)
                if isinstance(retrieved, dict):
                    keys = list(retrieved.keys())
                    for t in tmp:
                        for k in keys:
                            if k not in t:
                                t[k] = retrieved[k]
                elif retrieved not in tmp:
                    tmp.append(retrieved)
            for v in tmp:
                result.append(v)
            return result
        else:
            return str(type(value))

    musmongoclient = MusMongoClient()
    mapping = {}
    collist = [
        'authors_openalex',
        'authors_pure',
        'deals_journalbrowser',
        'employees_peoplepage',
        'funders_openalex',
        'institutions_openalex',
        'items_crossref',
        'items_datacite',
        'items_openaire',
        'items_orcid',
        'items_pure_oaipmh',
        'sources_openalex',
        'topics_openalex',
        'works_openalex'
    ]
    for collection in collist:
        # for now: only do the first item
        # todo: somehow loop over all items and get all unique keymappings
        async for item in musmongoclient.mongoclient[collection].find({}):
            mapping[collection] = get_one(item)
            print(f'{collection}: {mapping[collection]}')
            break


    return mapping

