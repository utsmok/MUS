
''' This sets up the Django environment '''
import os
import django
from django.db.models import Count, Q, Prefetch, Exists, OuterRef
from collections import defaultdict

PROJECTPATH = ""
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mus.settings")
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"  # https://docs.djangoproject.com/en/4.1/topics/async/#async-safety
django.setup()
from mus_wizard import models, constants
from mus_wizard.harvester import openalex, oai_pmh
from mus_wizard.database import matching, mongo_client
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
import asyncio
from rich import print
from rich.console import Console
from rich.table import Table

co = Console()
authorid = 'https://openalex.org/A5045181048'
mongoclient = mongo_client.MusMongoClient()

openalex_authors: AsyncIOMotorCollection = mongoclient.authors_openalex
pure_authors: AsyncIOMotorCollection = mongoclient.openaire_cris_persons
openalex_works: AsyncIOMotorCollection = mongoclient.works_openalex
pure_works: AsyncIOMotorCollection = mongoclient.openaire_cris_publications

async def get_data():
    oa_author_details = await openalex_authors.find_one({'id': authorid})
    oa_work_details = await openalex_works.find({'authorships.author.id': authorid}).to_list(length=10000)
    pure_author_details = await pure_authors.find({'id': authorid}).to_list(length=10000)
    pure_work_details = []
    if len(pure_author_details) > 0:
        for author in pure_author_details:
            tmp = await pure_works.find({'authors.internal_repository_id': author['internal_repository_id']}).to_list(length=10000)
            pure_work_details.extend(tmp)

    co.print(f'Overview for {authorid}', justify='center')
    co.print(f'OA Author details? {oa_author_details is not None}')
    co.print(f'Pure Author details? {len(pure_author_details) > 0}')
    co.print(f'# of oa works: {len(oa_work_details)}')
    co.print(f'# of pure works: {len(pure_work_details)}')
    co.input('Press enter to continue')
    co.print(f'[bold red]Details for {authorid}[/bold red]', justify='center')
    co.rule('OpenAlex')
    oatable = Table(title='Author details')
    oatable.add_column('key', style='bold cyan', justify='left')
    oatable.add_column('value')
    for k,v in oa_author_details.items():
        oatable.add_row(k, str(v))
    co.print(oatable)
    co.input('Press enter to continue')

    oatable = Table(title='OpenAlex works')
    oatable.add_column('oa id', style='bold cyan', justify='left')
    oatable.add_column('title')
    oatable.add_column('doi')
    oatable.add_column('type')
    oa_work_details = sorted(oa_work_details, key=lambda x: x['publication_date'])
    for work in oa_work_details:
        if len(work['title']) > 50:
            title = work['title'][:50] + '...'
        else:
            title = work['title']
        oatable.add_row(work['id'], title, work['doi'], work['type_crossref'])
    co.print(oatable)
    co.input('Press enter to continue')

    co.rule('Pure')
    pure_table = Table(title='Pure author details')
    pure_table.add_column('key', style='bold cyan', justify='left')
    pure_table.add_column('value')
    for k,v in pure_author_details[0].items():
        pure_table.add_row(k, str(v))
    co.print(pure_table)
    co.input('Press enter to continue')
    pure_table = Table(title='Pure works')
    pure_table.add_column('pure id', style='bold cyan', justify='left')
    pure_table.add_column('openalex id?')
    pure_table.add_column('title')
    pure_table.add_column('doi')
    for work in pure_work_details:
        if len(work['title']) > 50:
            title = work['title'][:50] + '...'
        else:
            title = work['title']
        pure_table.add_row(work['internal_repository_id'],str(work.get('id') is not None), title, work.get('doi'))
    co.print(pure_table)
def main():
    asyncio.run(get_data())

if __name__ == '__main__':
    main()