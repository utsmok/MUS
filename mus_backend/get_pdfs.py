'''
Try to download the pdf for papers in the db.

First try the pdf_urls for the locations of the paper directly, in this order:
1. best_oa_location
2. ris.utwente.nl or research.utwente.nl in url
3. rest of is_oa locations
4. rest of non is_oa locations

if still not found, see if the paper has a pure entry, and if so, try to get the pdf from:
1. research/ris utwente fields
2. scopus? other links?
3. retry doi field?


if paper is found:
- store in static/papers/pdf/   as <paper.id>_<year>_<doi>.pdf
- create new models.MUSPDF() entry:
    paper = foreign key: paper
    location = foreign key: location where pdf was found if it's a location linked to the paper
    doi = paper.doi
    openalex_url = paper.openalex_url
    url = location.pdf_url
    is_oa = location.is_oa or deduce depending on how pdf was found
    from_pure = if from research/ris.utwente.nl -> true, otherwise false
    year = paper.year
    filename = <paper.id>_<year>_<doi>.pdf

'''

from PureOpenAlex.models import Paper, MUSPDF
import asyncio
from rich import print
from asgiref.sync import sync_to_async
import aiohttp
import os.path
import fitz
from .multi_column import column_boxes

'''def get_headers_list():
    with httpx.Client() as client:
        response = client.get(f'https://headers.scrapeops.io/v1/browser-headers?api_key={SCRAPEOPSKEY}&num_results=10', follow_redirects=True)
        json_response = response.json()
        return json_response.get('result', [])
SCRAPEOPSKEY = getattr(settings, "SCRAPEOPSKEY")
HEADERLIST = get_headers_list()'''

DOWNLOADLOC = r'c:\pshell\MUS\static\papers\pdf'
HEADER={
'Accept':
'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'
,'Accept-Encoding':
'gzip, deflate, br, zstd'
,'Accept-Language':
'en-US,en;q=0.9,nl-NL;q=0.8,nl;q=0.7'
,'Cache-Control':
'max-age=0'
,'Dnt':
'1'
,'Sec-Ch-Ua':
'"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"'
,'Sec-Ch-Ua-Platform':
'"Windows"'
,'Sec-Fetch-Dest':
'document'
,'Sec-Fetch-Mode':
'navigate'
,'Sec-Fetch-Site':
'none'
,'Upgrade-Insecure-Requests':
'1'
,'User-Agent':
'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}


async def get_paper_pdfs(years):


    @sync_to_async
    def getpapers(year):
        return list(Paper.objects.filter(year=year).prefetch_related('locations'))

    async def downloadpdf(url, paper, session, fileloc):
        try:
            async with session.get(url=url, headers=HEADER, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                        if resp.status == 200:
                            with open(fileloc, 'wb') as fd:
                                    fd.write(await resp.content.read())
                            msg = f'[✅{resp.status}✅] {paper.doi} - {url}'
                            return True, msg
                        elif str(resp.status).startswith('3'):
                            return downloadpdf(resp.headers['Location'], paper, session)
                        else:
                            msg = f'[😾{resp.status}😾] {paper.doi} - {url}'
                            return False, msg
        except Exception as e:
            print(e)
            msg = f'[❗Exception❗] {paper.doi} - {url}'
            return False, msg
    async def processpdf(loc):
        try:
            doc = fitz.open(loc)
            txtloc = loc.replace('.pdf','.txt')
            out=open(txtloc,'wb')
            for page in doc:
                #see https://artifex.com/blog/extract-text-from-a-multi-column-document-using-pymupdf-inpython
                bboxes = column_boxes(page, footer_margin=50, no_image_text=True)
                for rect in bboxes:
                    out.write(page.get_text(clip=rect, sort=True).encode("utf8"))
                out.write(bytes((12,)))
            out.close()
            return True
        except Exception as e:
            return False

    async def downloadpaper(paper, session):
        pdf_urls = {'best_oa':'', 'twente':[],'is_oa':[], 'non_oa':[]}
        found = False
        downloaded = False
        from_pure = False
        i=0
        msglist=[]
        fileloc = DOWNLOADLOC +'\\'+ str(paper.id) + '_' + str(paper.year) + '_' + str(paper.doi).replace('https://doi.org/','').replace('/','_') + '.pdf'
        downloadargs = [paper, session, fileloc]
        if os.path.isfile(fileloc):
            print('pdf already exists')
            if os.path.isfile(fileloc.replace('.pdf','.txt')):
                print('txt already exists')
            else:
                _ = await processpdf(fileloc)
            return None
        for location in paper.locations.all():
            i=i+1
            msglist.append(f"[LOCATION {i}] {paper.doi} - {location.pdf_url}")
            if location.pdf_url != '':
                if location.is_best_oa:
                    pdf_urls['best_oa'] = location
                    found = True
                if 'ris.utwente.nl' in location.landing_page_url.lower() or 'research.utwente.nl' in location.landing_page_url.lower()\
                or 'ris.utwente.nl' in location.pdf_url.lower() or 'research.utwente.nl' in location.pdf_url.lower():
                    pdf_urls['twente'].append(location)
                    found = True
                elif location.is_oa and location.pdf_url:
                    pdf_urls['is_oa'].append(location)
                    found = True
                else:
                    pdf_urls['non_oa'].append(location)
                    found = True
        if found:
            #at least 1 pdf url found
            if pdf_urls['best_oa']!='':
                downloaded, msg =await downloadpdf(pdf_urls['best_oa'].pdf_url, *downloadargs)
                msglist.append(msg)
                location = pdf_urls['best_oa']
            if not downloaded:
                if len(pdf_urls['twente'])>0:
                    for url in pdf_urls['twente']:
                        downloaded, msg =await downloadpdf(url.pdf_url, *downloadargs)
                        msglist.append(msg)
                        if downloaded:
                            from_pure = True
                            location = url
                            break
            if not downloaded:
                if len(pdf_urls['is_oa'])>0:
                    for url in pdf_urls['is_oa']:
                        downloaded, msg =await downloadpdf(url.pdf_url, *downloadargs)
                        msglist.append(msg)
                        if downloaded:
                            location = url
                            break
            if not downloaded:
                if len(pdf_urls['non_oa'])>0:
                    for url in pdf_urls['non_oa']:
                        downloaded, msg =await downloadpdf(url.pdf_url, *downloadargs)
                        msglist.append(msg)
                        if downloaded:
                            location = url
                            break
        else:
            downloaded, msg =await downloadpdf(paper.doi, *downloadargs)
            msglist.append(msg)
            if downloaded:
                location = None

        if downloaded:
            msglist.append(f'downloaded a pdf for paper {paper.id} {paper.doi}')
            pdftext = await processpdf(fileloc)
            muspdfdict= {
                    'paper' : paper.id,
                    'location' : location.id if location else None,
                    'doi' : paper.doi,
                    'year' : paper.year,
                    'openalex_url' : paper.openalex_url,
                    'url' : location.pdf_url if location else None,
                    'is_oa' : location.is_oa if location else None,
                    'from_pure' : from_pure,
                    'filename' : str(paper.id) + '_' + str(paper.year) + '_' + str(paper.doi).replace('https://doi.org/','').replace('/','_') + '.pdf',
            }
            for msg in msglist:
                print(msg)
            return muspdfdict
        else:
            msglist.append(f'no pdf downloaded for paper {paper.id} {paper.doi}')
            for msg in msglist:
                print(msg)
            return None
    
    results=[]
    for year in years:
        papers=await getpapers(year)
        print(f'getting pdfs for {len(papers)} papers from {year}')
        chunks = [papers[i:i + 100] for i in range(0, len(papers), 100)]
        for papers in chunks:
            tasks=[]
            async with aiohttp.ClientSession() as session:
                for paper in papers:
                    task = asyncio.create_task(downloadpaper(paper, session))
                    tasks.append(task)
                result = await asyncio.gather(*tasks)
                results.append(result)
            print('done with chunk of papers')
        print(f'finished getting pdfs for {year}')
    print('finished getting all pdfs')
    return results

    

def main():
    results = asyncio.run(get_paper_pdfs([2024]))
    print(f'{len(results)=}')
    results = [result for result in results if result]
    print(f'{len(results)=}')
    muspdfs = MUSPDF.objects.bulk_create([MUSPDF(**result) for result in results])
    print(f'added {len(muspdfs)} muspdf objects to db')
    