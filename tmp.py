from motor import motor_asyncio
import orjson
import asyncio
from rich import print
import os
from pymongo import IndexModel

db = motor_asyncio.AsyncIOMotorClient(
MONGOURL).library_overview

async def get_data(path):
    with open(path, 'r', encoding='utf-8') as f: 
        while True:
            data = f.readline()  # Read a line
            if not data:
                break  # Break if there's no more data
            yield orjson.loads(data)  # Decode the line with orjson


async def run():
    print('starting run()')
    batch_size = 1000
    files = ['data_export_rich.json', 'data_export_refs.json']
    items = []
    count = 0
    for file in files:
        print(f'\n Now processing file {file}')
        colname = file.split('.')[0]
        # read and parse the json file as a stream
        # when batch_size items are parsed, insert them into the database
        async for item in get_data(file):
            del(item['_id'])
            items.append(item)
            if len(items) == batch_size:
                res = await db[colname].insert_many(items)
                print(res)
                print(len(items))
                count = count + batch_size
                print(f'inserted {count} (+{batch_size})', end='->')
                items = []

        # final insert call because the last batch might be smaller
        if items:
            await db.data_export_rich.insert_many(items)
            count = count + len(items)
            print(f'inserted {count} (+{len(items)}). Done with {file}!')
            items = []

async def create_indexes():
    print('creating indexes')
    for colname in ['data_export_rich', 'data_export_refs']:
        await db[colname].create_indexes([
                IndexModel('open_access_type'),
                IndexModel('is_oa'),
                IndexModel('year'),
                IndexModel('type'),
                IndexModel('doi'),
                IndexModel('title'),
                IndexModel('journal'),
                IndexModel('publisher'),
                IndexModel('EEMCS'),
                IndexModel('BMS'),
                IndexModel('TNW'),
                IndexModel('ET'),
                IndexModel('ITC'),
                IndexModel('pure_id'),
                IndexModel('openalex_id'),
                IndexModel('num_authors'),
                IndexModel('primary_topic'),
                IndexModel('subfield'),
                IndexModel('field'),
                IndexModel('domain'),
            ])
if __name__ == '__main__':
    print('starting script')
    asyncio.run(create_indexes())
    #asyncio.run(run())