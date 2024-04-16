
import csv
from datetime import datetime
from xclass_refactor.mus_mongo_client import MusMongoClient


class PureAPI():
    def __init__(self, years, mongoclient):
        self.years = years
        self.mongoclient = mongoclient
        self.results = {}

class PureReports():
    def __init__(self, mongoclient):
        self.mongoclient = mongoclient
        self.results = {}

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
