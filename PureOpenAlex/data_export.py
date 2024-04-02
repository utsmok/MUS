from PureOpenAlex.models import Paper
from PureOpenAlex.constants import CSV_EXPORT_KEYS, EEGROUPSABBR, TCSGROUPSABBR
import csv
from loguru import logger


def write_to_csv(data, filename, keys):
    with open(filename, 'w', newline='',encoding='utf-8') as myFile:
        writer = csv.DictWriter(myFile, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)

def export_paper_data(requests: dict):
    '''
    Exports csv files based on the request.
    Requests is a dict defined as follows:
    requests = {

        'export_filename1.csv': {
            'filters': [[filter1, value1],[filter2, value2],[filter3, value3]]
            'columns': [column1, column2, ...]
        },
        'export_filename2.csv': {
            ...
        },
        ...

    'export_filename_n' is the name of the file to be exported
    'filters' is a list of filters as defined in Paper.objects.filter_by()
    [optional] 'columns' is a list of columns to be exported. Defaults to constants.CSV_EXPORT_KEYS

    Does not return anything, it writes the csv files to disk.
    '''


    for filename, data in requests.items():
        if not str(filename).endswith('.csv'):
            raise FileNotFoundError(f'Filename {filename} does not end with .csv')

        if data.get('columns'):
            keys = data.get('columns')
        else:
            keys = CSV_EXPORT_KEYS

        print(keys)
        logger.info(f'Exporting data to {filename} using filters: {data.get("filters")}')
        papers =  Paper.objects.filter_by(data.get('filters')).get_table_prefetches()

        grouplist=[]
        if data.get('filters'):
            for filter in data.get('filters'):
                if filter[0] == 'EE':
                    grouplist.extend(EEGROUPSABBR)
                if filter[0] == 'TCS':
                    grouplist.extend(TCSGROUPSABBR)
                if filter[0] == 'group':
                    grouplist.append(filter[1])
        grouplist=list(set(grouplist))
        raw_data=papers.create_csv(grouplist)
        write_to_csv(raw_data,str(filename), keys)
        logger.info(f"Exported data to {filename}")


