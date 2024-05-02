from dotenv import load_dotenv
import os
dotenv_path = 'secrets.env'
load_dotenv(dotenv_path)

# API keys / ID's / e-mails / tokens
ORCID_CLIENT_ID = str(os.getenv('ORCID_CLIENT_ID'))
ORCID_CLIENT_SECRET = str(os.getenv('ORCID_CLIENT_SECRET'))
ORCID_ACCESS_TOKEN = str(os.getenv('ORCID_ACCESS_TOKEN'))
APIEMAIL = str(os.getenv('APIEMAIL'))
OPENAIRETOKEN = str(os.getenv('OPENAIRETOKEN'))

# IDs, names, and URLS for current university

INSTITUTE_NAME = str(os.getenv('INSTITUTE_NAME'))
INSTITUTE_ALT_NAME = str(os.getenv('INSTITUTE_ALT_NAME'))

ROR = str(os.getenv('ROR'))
OPENALEX_INSTITUTE_ID = str(os.getenv('OPENALEX_INSTITUTE_ID'))

JOURNAL_BROWSER_URL = str(os.getenv('JOURNAL_BROWSER_URL'))
OAI_PMH_URL = str(os.getenv('OAI_PMH_URL'))

# System settings
MONGOURL = str(os.getenv('MONGOURL')) #url to mongoDB incl user/pass
