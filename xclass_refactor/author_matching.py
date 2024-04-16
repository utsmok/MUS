

from polyfuzz.models import TFIDF
from polyfuzz import PolyFuzz
from xclass_refactor.mus_mongo_client import MusMongoClient

import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mus.settings")
import django
django.setup()


mongoclient = MusMongoClient()
from_list = [a['author_name'] for a in mongoclient.authors_pure.find()][:5]
to_list = [a['display_name'] for a in mongoclient.authors_openalex.find()]

tfidf = TFIDF(n_gram_range=(3, 3))
model = PolyFuzz(tfidf)
matchlist = model.match(from_list, to_list)
print(matchlist)