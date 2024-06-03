
from mus_wizard.database.mongo_client import MusMongoClient
from datetime import datetime, date
from rich.console import Console
import re
cons = Console()

async def normalize_doi(doi) -> str|None:
    '''
    retrieves a doi and normalizes it to a standard format:
    https://doi.org/<doi>, in lowercase
    '''
    if not doi:
        return None
    if isinstance(doi, str):
        doi = doi.lower()
    if doi.startswith('10'):
        stripped_doi = doi
    elif doi.startswith('https://doi.org/'):
        stripped_doi = doi.replace('https://doi.org/', '')
    elif doi.startswith('http://dx.doi.org/'):
        stripped_doi = doi.replace('http://dx.doi.org/', '')
    elif doi.startswith('https://dx.doi.org/'):
        stripped_doi = doi.replace('https://dx.doi.org/', '')
    elif doi.startswith('/'):
        stripped_doi = doi.replace('/', '')
    elif doi.startswith('0.'):
        stripped_doi = doi.replace('0.', '10.')
    elif doi.startswith('doi:'):
        stripped_doi = doi.replace('doi:', '').strip()
    elif doi.startswith('doi.org/'):
        stripped_doi = doi.replace('doi.org/', '').strip()
    
    else:
        try:
            stripped_doi = '10.'+doi.split('10.')[-1].strip()
        except Exception as e:
            print(f'DOI not recognized -- {doi}')
            return None
        if not stripped_doi:
            print(f'DOI does not start with 10 or https://doi.org/ -- {doi}')
            return None
        
    if not stripped_doi.startswith('https://doi.org/') and stripped_doi.startswith('10'):
        # check if doi matched the regex
        return f'https://doi.org/{stripped_doi}'
    else:
        raise ValueError(f'DOI does not match the expected format: {doi} ({stripped_doi} does not start with 10 or it does starts with https://doi.org/)')


async def get_mongo_collection_mapping():
    '''
    Iterates over all mongodb collections and recursively maps all dicts.
    Output is a dict with the key names as keys, and a string representation of the type(s) of the value(s) as the value. 
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

async def parse_reversed_abstract(abstract_raw:dict) -> str:
    """
    Inverts the given abstract by converting it from a string representation to a dictionary.
    Then, it creates a list of word-index pairs by iterating over the inverted abstract dictionary.
    Finally, it sorts the list based on the index and returns the concatenation of all word-index pairs.

    Parameters:
    - inverted_abstract (str): The string representation of the inverted abstract.

    Returns:
    - str: The concatenated word-index pairs.
    """
    try:
        word_index = []
        for k, v in abstract_raw.items():
            for index in v:
                word_index.append([k, index])
        word_index = sorted(word_index, key=lambda x: x[1])
        text = " ".join(word[0] for word in word_index)
    except Exception:
        text = ""
    return text