from dotenv import load_dotenv
import os
dotenv_path = 'secrets.env'
load_dotenv(dotenv_path)

ORCID_CLIENT_ID = str(os.getenv('ORCID_CLIENT_ID'))
ORCID_CLIENT_SECRET = str(os.getenv('ORCID_CLIENT_SECRET'))
ORCID_ACCESS_TOKEN = str(os.getenv('ORCID_ACCESS_TOKEN'))
MONGOURL = str(os.getenv('MONGOURL'))
APIEMAIL = str(os.getenv('APIEMAIL'))
OPENAIRETOKEN = str(os.getenv('OPENAIRETOKEN'))
