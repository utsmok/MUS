from PureOpenAlex.models import Paper
from PureOpenAlex.constants import (
    CSV_EXPORT_KEYS,
    EEGROUPSABBR, TCSGROUPSABBR,
    CERIF_CLOSER, RECORD_HEADER, RECORD_CLOSER,
    get_cerif_header
    )
import csv
from loguru import logger
import xmltodict

def write_to_csv(data, filename, keys):
    with open(filename, 'w', newline='',encoding='utf-8') as myFile:
        writer = csv.DictWriter(myFile, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)

def export_paper_data(requests: dict) -> list[str]:
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

    Returns the paths to the files for further processing.
    '''
    filenames=[]

    for filename, data in requests.items():
        if not str(filename).endswith('.csv'):
            raise FileNotFoundError(f'Filename {filename} does not end with .csv')

        if data.get('columns'):
            keys = data.get('columns')
        else:
            keys = CSV_EXPORT_KEYS

        print(keys)
        logger.info(f'Exporting data to {filename} using filters: {data.get("filters")}')
        papers =  Paper.objects.filter_by(data.get('filters'))

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
        filenames.append(filename)
    return filenames
def export_paper_data_to_cerif_xml(requests: dict) -> list[str]:
    '''
    Exports CERIF XML files based on the request.
    see https://rawgit.com/EuroCRIS/CERIF-DataModel/8743066b/documentation/MInfo.html

        Requests is a dict defined as follows:
        requests = {

            'export_filename1.xml': {
                'papers': [ paper.id1, paper.id2, ...],
                'filters': [[filter1, value1],[filter2, value2],[filter3, value3]]
            },
            'export_filename2.xml': {
                ...
            },
            ...

    export_filename_n is the name of the file to be exported
    'papers' is a list of paper ids to be exported. Defaults to all papers remaining after filtering.
    'filters' is a list of filters as defined in Paper.objects.filter_by() -- used on the list of papers.

    saves the xml files to disk and returns the path to the file for further processing.
    '''
    filenames=[]
    for filename, data in requests.items():
        if not str(filename).endswith('.xml'):
            raise FileNotFoundError(f'Filename {filename} does not end with .xml')

        logger.info(f'Exporting data to {filename} using filters: {data.get("filters")}')
        if data.get('papers'):
            papers =  Paper.objects.filter_by(data.get('filters')).filter(id__in=data.get('papers'))
        else:
            papers =  Paper.objects.filter_by(data.get('filters'))

        data = papers.exportxmldata()

        result = get_cerif_header()
        for record in data:
                result += RECORD_HEADER
                result += xmltodict.unparse(record, pretty=True)
                result += RECORD_CLOSER

    result += CERIF_CLOSER


    return filenames
