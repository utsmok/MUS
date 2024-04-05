from PureOpenAlex.models import Paper
from PureOpenAlex.constants import (
    CSV_EXPORT_KEYS, CSV_EEMCS_KEYS,
    EEGROUPSABBR, TCSGROUPSABBR,
    CERIF_CLOSER, RECORD_CLOSER,
    get_cerif_header, get_cerif_record_header
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
        },
        'export_filename2.csv': {
            ...
        },
        ...

    'export_filename_n' is the name of the file to be exported
    'filters' is a list of filters as defined in Paper.objects.filter_by()

    Returns the paths to the files for further processing.
    '''
    filenames=[]

    for filename, data in requests.items():
        if not str(filename).endswith('.csv'):
            raise FileNotFoundError(f'Filename {filename} does not end with .csv')

        raw_data, keys=Paper.objects.get_csv(data)
        write_to_csv(raw_data,str(filename), keys)
        logger.info(f"Exported data to {filename}")

    return filenames
def export_paper_data_to_cerif_xml(requests: dict) -> list[str]:
    '''
    Exports CERIF XML files based on the request.
    see https://rawgit.com/EuroCRIS/CERIF-DataModel/8743066b/documentation/MInfo.html
    and https://openaire-guidelines-for-cris-managers.readthedocs.io/en/latest/cerif_xml_publication_entity.html
    and https://github.com/EuroCRIS/CERIF-Vocabularies/blob/master/IdentifierTypes.xml
    and https://vocabularies.coar-repositories.org/resource_types/
    and https://adk.elsevierpure.com/ws/api/documentation/index.html
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
                result += get_cerif_record_header() #also get id to add to record header
                result += xmltodict.unparse(record, pretty=True)
                result += RECORD_CLOSER

    result += CERIF_CLOSER


    return filenames
