'''
move DOIs of papers to zotero
let zotero pull metadata and pdfs in the background

later:
load in the metadata to mongodb
transfer the pdfs to mus to use later
'''

from pyzotero import zotero
from .models import Paper
from django.conf import settings
from pymongo import MongoClient
from rich import print
from collections import deque 

MONGOURL = getattr(settings, "MONGOURL")
db = MongoClient(MONGOURL)
zot : zotero.Zotero = getattr(settings, "ZOTERO")

def split_list(input_list, chunk_size): 
    deque_obj = deque(input_list) 
    while deque_obj: 
        chunk = [] 
        for _ in range(chunk_size): 
            if deque_obj: 
                chunk.append(deque_obj.popleft()) 
        yield chunk

zotitemtypes = {
    'journal-article':'journalArticle',
    'proceedings-article':'conferencePaper',
    'proceedings':'conferencePaper',
    'book':'book',
    'book-chapter':'bookSection',
    'dataset':'dataset',
    'report':'report',
    'dissertation':'thesis',
    }

def add_papers_to_zotero():
    papers = Paper.objects.all()
    addlist = []
    for paper in papers:
        try:
            addlist.append({'title':paper.title,'DOI':paper.doi, 'itemType':zotitemtypes.get(paper.itemtype,'journalArticle')})
        except Exception as e:
            print(f'error {e} when making zotero addlist for paper {paper.doi}')
            continue
    print(f'adding {len(addlist)} items to zotero')
    responses=[]
    for chunk in split_list(addlist, 50):
        resp = zot.create_items(chunk)
        responses.append(resp)
    print(responses[0],responses[-1])
        

def get_pdfs_from_zotero():
    pass

def get_metadata_from_zotero():
    pass