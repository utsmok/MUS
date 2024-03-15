from datetime import datetime, date
import os.path as op
import urllib.request
from currency_converter import ECB_URL, CurrencyConverter
from io import BytesIO
import requests
import threading
import os
from .models import UTData, DealData
from django.db import transaction
from loguru import logger
import re

TAGLIST = ["UT-Hybrid-D", "UT-Gold-D", "NLA", "N/A OA procedure"]
LICENSESOA = [
    "cc-by-sa",
    "cc-by-nc-sa",
    "publisher-specific-oa",
    "cc-by-nc-nd",
    "cc-by-nc",
    "cc0",
    "cc-by",
    "public-domain",
    "cc-by-nd",
    "pd",
]
OTHERLICENSES = [
    "publisher-specific,authormanuscript",
    "unspecified-oa",
    "implied-oa",
    "elsevier-specific",
]
TCSGROUPS = [
    "Design and Analysis of Communication Systems",
    "Formal Methods and Tools",
    "Computer Architecture Design and Test for Embedded Systems",
    "Pervasive Systems",
    "Datamanagement & Biometrics",
    "Semantics",
    "Human Media Interaction",
]

TCSGROUPSABBR = [
    "DACS",
    "FMT",
    "CAES",
    "PS",
    "DMB",
    "SCS",
    "HMI",
]

start_year = 2000
end_year = 2030

for year in range(start_year, end_year + 1):
    TAGLIST.append(f"{year} OA procedure")

# Now TAGLIST has all the OA procedures up till 2030
TWENTENAMESDELETE = [
    "university of twente",
    "University of Twente / Apollo Tyres Global R&D",
    "University of Twente Faculty of Engineering Technology",
    "University of Twente, Faculty of Geo-Information Science and Earth Observation",
    "University of Twente Faculty of Geo-Information Science and Earth Observation ITC",
    "University of Twente, Faculty of Geo-Information Science and Earth Observation (ITC)",
    "University of Twente - Faculty of ITC",
    "University of Twente, faculty of Science and Technology",
    "University of Twente,ITC",
    "University of Twenty, Netherlands",
]
TWENTENAMES = [
    "university of twente",
    "University of Twente",
    "University of Twente ",
    "University of Twente / Apollo Tyres Global R&D",
    "University of Twente Faculty of Engineering Technology",
    "University of Twente, Faculty of Geo-Information Science and Earth Observation",
    "University of Twente Faculty of Geo-Information Science and Earth Observation ITC",
    "University of Twente, Faculty of Geo-Information Science and Earth Observation (ITC)",
    "University of Twente - Faculty of ITC",
    "University of Twente, faculty of Science and Technology",
    "University of Twente,ITC",
    "University of Twenty, Netherlands",
]
ORCID_RECORD_API = "https://pub.orcid.org/v3.0/"
APILOCK = threading.Lock()


def invertAbstract(inverted_abstract):
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
        for k, v in inverted_abstract.items():
            for index in v:
                word_index.append([k, index])
        word_index = sorted(word_index, key=lambda x: x[1])
        text = " ".join(word[0] for word in word_index)
    except Exception:
        text = ""
    return text


def convertToEuro(amount, currency, publishdate):

    """
    Converts the given `amount` of `currency` to Euro based on the specified `publishdate`.

    Parameters:
        amount (int): The amount of currency to be converted.
        currency (str): The currency code of the amount to be converted.
        publishdate (str): The publish date for the currency conversion rates.

    Returns:
        int: The converted amount in Euro.
    """
    raise Exception("currently not implemented properly")
    folder = 'ecb_data'
    zipname = f"ecb_{date.today():%Y%m%d}.zip"
    filename = os.path.join(os.getcwd(),folder, zipname)
    exists = op.isfile(os.path.join(folder, filename))
    if not exists:
        urllib.request.urlretrieve(ECB_URL, filename)

    c = CurrencyConverter(filename)

    return int(c.convert(amount, currency, "EUR", publishdate))

def determineIsInPure(paper):
    for location in paper.locations.all():
        if 'ris.utwente.nl' in location.landing_page_url.lower() or 'research.utwente.nl' in location.landing_page_url.lower():
            return True
        if "twente" in location.pdf_url.lower():
            return True
    return False

def processDOI(doi: str) -> str|None:
    doi_pattern = re.compile(r'10.\d{4,9}/[-._;()/:A-Z0-9]+', re.IGNORECASE)
    doi = str(doi).replace(' ', '').replace(r'%20','').replace(r'%2F','/').replace(',','.')
    if doi.endswith('/'):
        doi = doi[:-1]
    match = doi_pattern.search(doi)
    if match:
        extracted_doi = match.group()
        if extracted_doi.endswith('/'):
            extracted_doi = doi[:-1]
        if extracted_doi.lower().endswith('openaccess'):
            extracted_doi = extracted_doi[:-10]
        if extracted_doi.lower().endswith('thefunderforthischapterisuniversityoftwente'):
            extracted_doi = extracted_doi.replace('ThefunderforthischapterisUniversityofTwente','')
        return "https://doi.org/" + extracted_doi
    else:
        logger.error(f"Invalid DOI: {doi}")
        return None

def calculateUTkeyword(work, paper, authorships):
    keyword = ""
    dealstatus = ""
    license = ""
    oatypejournal = ""
    ut_corresponding = False
    ut_author = False
    corresponders = []
    # determine keyword to add based on flowchart
    # work --> openalex api response
    # paper --> Paper object
    # authorships --> dict with authorship data
    license = paper.license
    paper.openaccess
    is_oa = paper.is_oa
    paper.is_in_pure
    paper.has_pure_oai_match
    taverne_date = paper.taverne_date
    for author in authorships:
        if author["author"].is_ut:
            ut_author = True
            if author["corresponding"]:
                ut_corresponding = True
                corresponders.append(author["author"].name)
    if not ut_author:
        keyword += " (no UT author found) "
    if not ut_corresponding:
        keyword += " (no corresponding UT author found) "
    if paper.journal is not None:
        dealdata = DealData.objects.filter(journal=paper.journal)
        if dealdata.exists():
            dealstatus = dealdata.first().deal_status
            oatypejournal = dealdata.first().oa_type
    if "100% APC discount for UT authors" in dealstatus:
        if is_oa:
            if (
                oatypejournal
                == "Hybrid Open Access. Journal supports Open Access publishing on request"
            ):
                keyword += " UT-Hybrid-D "
            if (
                oatypejournal
                == "Full Open Access. All articles in this journal are Open Access"
            ):
                keyword += " UT-Gold-D "
        else:
            keyword += " Missed deal. Email authors to notify. "
    elif license in LICENSESOA:
        keyword += " Has open acces license - no keyword needed - OA status Open "
    elif taverne_date is not None:
        if datetime.today().date() >= taverne_date:
            keyword += f" Taverne with keyword {datetime.today().year} OA Procedure "

    return keyword

def addAvatars():
    """
    Reads URL for avatar of UT author from UTData.avatar, grabs the jpg and stores that instead
    """
    from django.core.files.images import ImageFile

    allUTData = UTData.objects.all().prefetch_related("employee")

    for utdata in allUTData:
        if utdata.avatar is not None and type(utdata.avatar) != ImageFile:
            try:
                avatarurl=str(utdata.avatar)
                if avatarurl[0:4] != "http":
                    raise Exception('no url found in avatar field')
            except Exception as e:
                    print('error',e,' while updating avatar:', utdata.avatar)

            fn = f"{avatarurl.strip('https://people.utwente.nl/').split('/')[0]}.jpg"
            response = requests.get(avatarurl)
            image = ImageFile(BytesIO(response.content))
            with transaction.atomic():
                utdata.avatar.save(fn,image,save=True)

'''def addEEMCSAuthorsFromCSV():
    import csv
    import regex
    import ast

    authordata = []

    def extractIDs(data):
        # This regex captures both the names of the IDs and their corresponding numbers
        pattern = r"(Employee ID|Scopus Author ID|ISNI|Digital author ID):\s*(\d+)"
        matches = regex.findall(pattern, data)
        finalmatches = {}
        for match in matches:
            if match[0] == "Employee ID":
                name = "employee_id"
                finalmatches[name] = match[1]

            elif match[0] == "Scopus Author ID":
                name = "scopus_id"
                finalmatches[name] = match[1]

            elif match[0] == "ISNI":
                name = "isni"
                finalmatches[name] = match[1]

            elif match[0] == "Digital author ID":
                name = "digital_author_id"
                finalmatches[name] = match[1]
        return finalmatches

    def extractSEPKUOZyears(data, name):
            if len(data) > 1:
                result = (
                    "["
                    + data.replace("\xa0", " ")
                    .replace(",", " ")
                    .replace("Some Titlestaff:", ('"},{"name":"'+name+'","job_title":"'))
                    .replace("year: ", '", "year":"')
                    .replace("fte:", '", "fte":"')
                    .strip('"},')
                    + '"}]'
                )
                return ast.literal_eval("".join(result.split()))
            return None

    results=[]
    authordata=[]
    orglist=[]

    with open(
            r"C:\pshell\powershell\DjangoOpenAlex\mus\PureOpenAlex\static\eemcs_authors.csv",
            encoding="utf-8-sig",
        ) as csv_file:
            csv_reader = csv.DictReader(csv_file, delimiter=",")
            for row in csv_reader:
                data = extractIDs(row["ID"])
                try:
                    result= extractSEPKUOZyears(row["SEPKUOZ"], data["employee_id"])
                except Exception:
                    continue
                if result is not None:
                    [results.append(x) for x in result]
                data["orcid"] = row["ORCID"]
                data["name"] = row["Name"]
                data["first_name"] = row["FirstName"]
                data["last_name"] = row["LastName"]
                data["pub_name"] = row["DefaultPubName"]
                data["known_as"] = row["KnownAsName"]
                data["former_name"] = row["FormerName"]
                orglist.append(row['Organisations'])
                unit = row["OrgUnit"].split(",")
                institutes = list(
                    set(
                        [
                            org.strip()
                            for org in unit
                            if "TechMed Centre" in org or "Institute" in org
                        ]
                    )
                )
                #data["institutes"] = institutes
                data["is_dsi"] = [
                    True if "Digital Society Institute" in institutes else False
                ][0]
                data["is_mesa"] = [True if "MESA+ Institute" in institutes else False][0]
                data["is_techmed"] = [True if "TechMed Centre" in institutes else False][0]
                data["current_org_unit"] = list(
                    set(
                        [
                            org.strip()
                            for org in unit
                            if (
                                "Former organisational unit" not in org
                                and "Institute" not in org
                            )
                        ]
                    )
                )

                if data["current_org_unit"] != []:
                    data["current_org_unit"] = data["current_org_unit"][0].strip()
                    data["is_tcs"] = data["current_org_unit"] in TCSGROUPS
                    if data["current_org_unit"] == "Semantics":
                        data["current_org_unit"] = "Semantics, Cybersecurity and Services"
                else:
                    data["is_tcs"] = False
                authordata.append(data)

    #use list of dicts to make dict of dicts with employee_id as a key
    authordatadict = {item['employee_id']:item for item in authordata}

    #add job + year info to the datadict
    results=pd.json_normalize(results)
    grouped=results[['name', 'job_title', 'year']].groupby('name')
    for name, group in grouped:
        group2=group.groupby('job_title')
        authordatadict[name]['jobs']=[]
        for job_title, group2 in group2:
            jobdetails={"job_title":job_title, "years":group2['year'].sort_values().tolist()}
            authordatadict[name]['jobs'].append(jobdetails)
        authordatadict[name]['jobs']=pd.json_normalize(authordatadict[name]['jobs']).to_json(orient="records")

    tcsauthorsdict={k:v for (k,v) in authordatadict.items() if v['is_tcs']}
    tcsauthorslist=[authordatadict[name] for name in tcsauthorsdict.keys()]

    with transaction.atomic():
        AFASData.objects.bulk_create([AFASData(**data) for data in tcsauthorslist])
'''