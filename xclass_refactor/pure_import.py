
import csv
from datetime import datetime
from xclass_refactor.mus_mongo_client import MusMongoClient
from xclass_refactor.generic_api import GenericAPI
from rich import progress, console, print
import functools
import aiometer
import xmltodict
import rich
import time

class PureAPI(GenericAPI):
    NAMESPACES = {
        "http://www.openarchives.org/OAI/2.0/":None,
        "http://www.openarchives.org/OAI/2.0/oai_dc/":None,
        'http://purl.org/dc/elements/1.1/':None,
        'http://www.w3.org/2001/XMLSchema-instance':None,
        'http://www.w3.org/XML/1998/namespace':None,
        'http://purl.org/dc/terms/':None,
    }
    def __init__(self, years: list[int]):
        super().__init__('items_pure_oaipmh', 'doi')
        self.years : list[int] = years
        self.years.sort(reverse=True)
        self.set_api_settings(max_at_once=5,
                            max_per_second=5,)

    def run(self):
        self.motorclient.get_io_loop().run_until_complete(self.get_item_results())

    async def get_item_results(self) -> None:
        '''
        uses call_api() to get the result for each item in itemlist and puts them in the mongodb collection
        '''
        print(f"calling api to get data for {self.item_id_type}s")
        async with aiometer.amap(functools.partial(self.call_api), self.years, max_at_once=self.api_settings['max_at_once'], max_per_second=self.api_settings['max_per_second']) as responses:
                ...

    async def call_api(self, year) -> list[dict]:
        async def fetch_response(url):
            try:
                r = await self.httpxclient.get(url)
                parsed = xmltodict.parse(r.text, process_namespaces=True, namespaces=self.NAMESPACES, attr_prefix="", cdata_key='value')
                return parsed['OAI-PMH']['ListRecords']
            except Exception as e:
                print(f'error fetching {url}: {e}')
                return None
        base_url = "https://ris.utwente.nl/ws/oai"
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

            for result in response.get('record'):
                del result['metadata']['dc']['xmlns']
                del result['metadata']['dc']['schemaLocation']
                temp = result['metadata']['dc']
                temp['pure_identifier'] = result['header']['identifier']
                temp['pure_datestamp'] = result['header']['datestamp']
                results.append(temp)
            if results:
                await self.collection.insert_many(results)
            if response.get('resumptionToken'):
                resumetoken = response.get('resumptionToken').get('value')
                url = f"{base_url}?verb=ListRecords&resumptionToken={resumetoken}"
                continue
            else:
                return True



class PureAuthorCSV():
    '''
    read in a csv file exported from Pure containing author details
    and store the data in MongoDB
    '''

    def __init__(self, filepath: str, mongoclient: MusMongoClient):
        self.filepath = filepath
        self.mongoclient = mongoclient
        self.collection = mongoclient.authors_pure

    def run(self):
        with open(self.filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
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
                self.collection.insert_one(row)
