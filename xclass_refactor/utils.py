
from collections import defaultdict
from xclass_refactor.mus_mongo_client import MusMongoClient
from datetime import datetime, date
import motor.motor_asyncio
from rich.console import Console

cons = Console()
async def get_mongo_collection_mapping():
    '''
    iterate over all mongodb collections to map the key/values in there
    '''
    def get_one(value):
        if value in ['', list, dict, str, None, datetime, date]:
            return str(type(value)).replace('<class \'', '').replace('\'>', '')
        elif value == []:
            return 'list'
        elif value == {}:
            return 'dict'
        elif isinstance(value, dict):
            if len(value.keys()) > 50:
                return 'dict'
            result = {}
            for k, v in value.items():
                if k == '_id' or k == 'abstract_inverted_index':
                    continue
                result[k] = get_one(v)
            return result
        elif isinstance(value, list):
            result = []
            tmp = []
            tmp2 = []
            for v in value:
                if isinstance(v, dict):
                    dct = {}
                    for k, v in v.items():
                        if k not in tmp:
                            tmp.append(k)
                            dct[k] = get_one(v)
                    if dct:
                        result.append(dct)
                else:
                    if v not in tmp2:
                        res = get_one(v)
                        tmp2.append(v)
                        result.append(res)
            return result
        else:
            return str(type(value)).replace('<class \'', '').replace('\'>', '')
        

    def compare(new, old, level=0):
        change = False
        

        if isinstance(new, list) and not isinstance(old, list):
            old = new
            return old, True
        elif isinstance(new, dict) and not isinstance(old, dict):
            old = new
            return old, True
        elif isinstance(new, list) and isinstance(old, list):
            if len(new) < len(old):
                return old, False
            try:
                old = sorted(old)
                new = sorted(new)
            except Exception as e:
                pass
            for v_old, v_new in zip(old, new):
                if not isinstance(v_old, dict) and not isinstance(v_new, dict):
                    if v_old != v_new and v_new not in ['', [], {}, {}, None] and v_new not in old:
                        try:
                            old.append(v_new)
                            change = True
                            cons.print(f'value "{v_new}" added to list level {level}')
                        except Exception as e:
                            cons.print(f'error appending item to list: {e}')
                            cons.print(f'old: {old}')
                            cons.print(f'new: {new}')
                else:
                    old, change = compare(v_new, v_old, level+1)
                
        elif isinstance(new, dict) and isinstance(old, dict):
                for k, v in new.items():    
                    if k not in old.keys():
                        old[k] = v
                        cons.print(f'key "{k}" added to dict level {level}')
                        change = True
                    elif v:
                        if isinstance(v, dict) or isinstance(v, list):
                            old[k], change = compare(v, old[k], level+1)
                        elif old[k] in ['', [], {}, None] and v not in ['', [], {}, {}, None]:
                            cons.print(f'changed value for key "{k}" from {old[k]} to {v} level {level}')
                            old[k] = v
                            change = True

        return old, change


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
        i=0
        cons.print(f'getting mapping for {collection}')
        changed = False
        async for item in musmongoclient.mongoclient[collection].find({}):
            res = get_one(item) 
            
            if collection in mapping.keys():
                try:
                    newres, change = compare(res, mapping[collection])
                except Exception as e:
                    cons.print(f'error {e} in {collection} {i}')
                    cons.print(newres)
                    cons.print(mapping[collection])
                    raise Exception(e)
                if change:
                    changed = True
                    mapping[collection] = newres

            else:
                mapping[collection] = res

            
            i=i+1
            
            '''
            if i%200 == 0:
                if changed:
                    changed=False
                    continue
                else:
                cons.print(f'{collection} {i} items checked -- no changes to the result in last 200 items')
                next = cons.input('Press y to move to next item, any other key to check another batch. ')
                if next == 'y':
                    break
                else:
                    continue
            '''




    return mapping

