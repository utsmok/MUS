
from datetime import datetime
from xclass_refactor.mus_mongo_client import MusMongoClient
from xclass_refactor.generics import GenericAPI
from xclass_refactor.constants import OAI_PMH_URL
from rich.console import Console
import functools
import aiometer
import xmltodict
import time
import aiocsv
import aiofiles
cons = Console(markup=True)

class PureAPI(GenericAPI):
    #! Note: check documentation for the correct namespaces and keys to use -- maybe switch to openaire cerif style??
    def __init__(self, years: list[int] = None):
        super().__init__('items_pure_oaipmh', 'doi', itemlist=None)
        if years:
            self.years : list[int] = years
        else:
            self.years : list[int] = [2019, 2020, 2021, 2022, 2023, 2024]
        self.years.sort(reverse=True)
        self.set_api_settings(max_at_once=5,
                            max_per_second=5)
        self.NAMESPACES = {
        "http://www.openarchives.org/OAI/2.0/":None,
        "http://www.openarchives.org/OAI/2.0/oai_dc/":None,
        'http://purl.org/dc/elements/1.1/':None,
        'http://www.w3.org/2001/XMLSchema-instance':None,
        'http://www.w3.org/XML/1998/namespace':None,
        'http://purl.org/dc/terms/':None,
        }
        self.KEYS_TO_FIX = {
        'title':'value',
        'subject': ['value'],
        'description': 'value',
        }
    async def run(self):
        await self.get_item_results()
        return self.results

    async def get_item_results(self) -> None:
        '''
        uses call_api() to get the result for each item in itemlist and puts them in the mongodb collection
        '''
        cons.print(f"calling api to get data for {self.item_id_type}s")
        async with aiometer.amap(functools.partial(self.call_api), self.years, max_at_once=self.api_settings['max_at_once'], max_per_second=self.api_settings['max_per_second']) as responses:
                # do something with the returned items?
                ...
        cons.print(f"finished gathering Pure Data for {self.years}")
    async def call_api(self, year) -> list[dict]:
        cons.print(f"gathering Pure Data for year {year}")
        async def fetch_response(url):
            async def remove_lang_fields(json):
                for key, value in json.items():
                    if key in self.KEYS_TO_FIX:
                        mapping = self.KEYS_TO_FIX[key]
                        if isinstance(mapping, str):
                            tmp = value['value']
                        elif isinstance(mapping, list):
                            tmp = []
                            for i in value:
                                tmp.append(i['value'])
                        json[key] = tmp
                return json
            try:
                r = await self.httpxclient.get(url)
                parsed = xmltodict.parse(r.text, process_namespaces=True, namespaces=self.NAMESPACES, attr_prefix="", cdata_key='value')
                parsed = await remove_lang_fields(parsed)
                return parsed['OAI-PMH']['ListRecords']
            except Exception as e:
                cons.print(f'error fetching {url}: {e}')
                return None
        base_url = OAI_PMH_URL
        metadata_prefix = "oai_dc"
        set_name = f"publications:year{year}"
        url = (
            f"{base_url}?verb=ListRecords&metadataPrefix={metadata_prefix}&set={set_name}"
        )
        while True:
            response = await fetch_response(url)
            if not response:
                time.sleep(5)
                continue
            results = []
            items = response.get('record')
            if not isinstance(items, list):
                items = [items]
            for result in items:
                del result['metadata']['dc']['xmlns']
                del result['metadata']['dc']['schemaLocation']
                temp = result['metadata']['dc']
                temp['pure_identifier'] = result['header']['identifier']
                temp['pure_datestamp'] = result['header']['datestamp']
                results.append(temp)

            if results:
                for result in results:
                    await self.collection.find_one_and_update({"pure_identifier":result['pure_identifier']}, {'$set':result}, upsert=True)
                    self.results['ids'].append(result['pure_identifier'])
                    self.results['total'] += 1
            if response.get('resumptionToken'):
                resumetoken = response.get('resumptionToken').get('value')
                url = f"{base_url}?verb=ListRecords&resumptionToken={resumetoken}"
                continue
            else:
                cons.print(f'no more pure results for year {year}')
                return True



class PureAuthorCSV():
    '''
    read in a csv file exported from Pure containing author details
    and store the data in MongoDB
    '''

    def __init__(self, filepath: str = 'eemcs_author_details.csv'):
        self.filepath = filepath
        self.mongoclient = MusMongoClient()
        self.collection = self.mongoclient.authors_pure
        self.results = {'total':0}
    async def run(self):
        pureids = []
        async for item in self.collection.find(projection={'author_pureid':1}):
            if item['author_pureid'] not in pureids:
                pureids.append(item['author_pureid'])
            else:
                await self.collection.delete_one({'author_pureid':item['author_pureid']})
        async with aiofiles.open(self.filepath, 'r', encoding='utf-8') as f:
            cons.print(f"reading in {self.filepath}")
            async for row in aiocsv.AsyncDictReader(f):
                for key, value in row.items():
                    if 'affl_periods' in key:
                        # data looks like this: '1/01/81 → 1/01/18 | 2/08/01 → 2/08/01'
                        list_affl_periods = [i.strip() for i in value.split('|')]
                        new_value = []
                        for item in list_affl_periods:
                            formatted_dates = [i.strip() for i in item.split('→')]
                            for i,date in enumerate(formatted_dates):
                                if date != '…':
                                    splitted_date = date.split('/')
                                    if len(splitted_date[0]) == 1:
                                        splitted_date[0] = '0'+splitted_date[0]
                                    formatted_dates[i] = datetime.strptime('/'.join(splitted_date), '%d/%m/%y')
                                else:
                                    formatted_dates[i] = None
                            dictform={'start_date':formatted_dates[0], 'end_date':formatted_dates[1]}
                            new_value.append(dictform)
                        row[key] = new_value
                    elif 'date' in key or 'modified' in key:
                        if row[key]:
                            row[key] = [datetime.strptime(i.strip().split(' ')[0], '%Y-%m-%d') for i in value.split('|')]
                    elif '|' in value:
                        row[key] = [i.strip() for i in value.split('|')]

                if row['author_pureid'] not in pureids:
                    await self.collection.insert_one(row)
                    self.results['total'] = self.results['total'] + 1
        cons.print(f"finished reading in {self.filepath}")
        return self.results
