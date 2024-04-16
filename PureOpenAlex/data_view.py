from .models import (
    Paper,
    DBUpdate,
    Author,
    Journal,
    Location,
    PureEntry,
    Source,
    UTData
)
from .constants import FACULTYNAMES, TCSGROUPSABBR, EEGROUPSABBR
from loguru import logger
from django.db.models import Q
from rich import print
from pymongo import MongoClient
from django.conf import settings
import json

from collections import defaultdict
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
def generateMainPage(user):
    """
    returns:
    dict total with keys articles = num of papers and oa = % of papers where is_oa==true
    list faculties, each entry is dict with keys name,articles,oa; self explanatory
    """
    facultynamelist = ["EEMCS", "BMS", "ET", "ITC", "TNW", "marked", "Other groups"]
    total = {
        "articles": 1,
        "oa": 0,
        "numoa": 0,
        "inpure": 0,
        "inpure_percent": 0,
        "inpurematch": 0,
    }
    faculties = []
    for faculty in facultynamelist:
        facultyname, stats, _ = getPapers(faculty, "all", user)
        total["articles"] += stats["num"]
        total["numoa"] += stats["numoa"]
        total["inpure"] += stats["articlesinpure"]
        total["inpurematch"] += stats["articlesinpurematch"]
        faculties.append(
            {
                "name": facultyname,
                "articles": stats["num"],
                "oa": stats["oa_percent"],
                "inpure": stats["articlesinpure"],
                "inpure_percent": stats["articlesinpure_percent"],
                "inpurematch": stats["articlesinpurematch"],
                "inpurematch_percent": stats["articlesinpurematch_percent"],
            }
        )
    total["oa"] = round(total["numoa"] / total["articles"] * 100, 2)
    total["inpure_percent"] = round(total["inpure"] / total["articles"] * 100, 2)
    total["inpurematch_percent"] = round(
        total["inpurematch"] / total["articles"] * 100, 2
    )
    total['articles'] += -1
    return total, faculties
def getPapers(name, filter="all", user=None):
    facultyname = ""
    listpapers = []
    if user is None:
        username = "none"
    else:
        username = user.username
    if isinstance(name, int):
        logger.info("getpaper [id] {} [user] {}", name, username)
        paperid = name
        facultyname = "single"
        listpapers = Paper.objects.get_single_paper_data(paperid,user)
        stats = None
        return facultyname, stats, listpapers
    else:
        logger.info("getpapers [name] {} [filter] {} [user] {}", name, filter, username)
        if filter == 'author':
            facultyname = name+" [Author]"
            filterpapers = Paper.objects.get_author_papers(name)
            filter = [['all','']]
        elif name == "marked" or name == "Marked papers":
            facultyname = "Marked papers"
            filterpapers=Paper.objects.get_marked_papers(user)
            if isinstance(filter, str):
                filter = [[str(filter),""]]
        else:
            filterpapers = Paper.objects.all().distinct()
            if name == "all" or name == "All items":
                facultyname = "All MUS papers"
                name = 'all'
                if isinstance(filter, str):
                    filter = [[str(filter),""]]
            else:
                if name not in FACULTYNAMES:
                    facultyname = "Other groups"
                    name = 'other'
                else:
                    facultyname = name
                if isinstance(filter, str):
                    filter = [[str(filter),""],['faculty',name]]
                if isinstance(filter, list):
                    if ['faculty', name] not in filter:
                        filter.append(['faculty',name])

    listpapers = filterpapers.get_table_data(filter,user)
    stats = listpapers.get_stats()
    return facultyname, stats, listpapers
def open_alex_autocomplete(query, types=['works','authors'], amount=5):
    '''
    Uses the OpenAlex autocomplete API to fetch data
    https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/autocomplete-entities
    Parameters:
        query: string to search for
        type: list of strings that denotes the itemtype(s) to search for. Defaults to ['works', 'authors'].
            Choices are: 'works', 'authors', 'sources', 'institutions', 'concepts', 'publishers', 'funders'
        amount: number of results to return, defaults to 5
    Returns:
        response: json response from OpenAlex with 'count' and 'results' fields
            count: number of results total
            results: list of first <amount> found results with the following fields:
            ------------------------------------------------------------------------------------
                'id'                openalex id -- use this to find items in mus database!
                'display_name'      name of item
                'entity_type'       openalex entity type, should match parameter type
                'cited_by_count'    # of citations for Work or sum of all works related to item if not Work
                'works_count'       # of associated works; always 0 for Works
                'hint'              Depends on type - Work: author names, Author: last known institution, Source: host org, Institution: location, Concept: description
                'external_id'       ROR, ORCID, DOI, that sort of thing
                'filter_key'        points to field in openalex work that holds this type of item
            ------------------------------------------------------------------------------------

    '''


    '''
    Call the OpenAlex autocomplete API.
    Returns json with meta, results as root keys.
    meta has fields 'count', 'db_response_time_ms', 'page', 'per_page'.
    results is list of dicts with fields as shown above.
    '''
    import httpx

    tresults={}
    for oa_type in types:
        query = query.replace(' ', '+')
        if oa_type=='works':
            url = f"https://api.openalex.org/autocomplete/{oa_type}?q={query}"
        else:
            url = f"https://api.openalex.org/autocomplete/{oa_type}?q={query}"
        result= {
        'count':0,
        'results':[]
        }

        response = httpx.get(url)
        response.raise_for_status()
        data=response.json()

        result['count']=data['meta']['count']
        if result['count']==0:
            print('no results (?)')
            return None
        result['type']=[oa_type]
        if result['count']>=5:
            result['results']=data['results'][:6]
        else:
            result['results']=data['results']
        tresults[oa_type]=result

    maxlen=0
    most_results_type=''
    for key, value in tresults.items():
        if value['count']>maxlen:
            maxlen=value['count']
            most_results_type=key
    if most_results_type=='':
        return None
    if tresults[most_results_type]['count']>=5:
        result=tresults[most_results_type]
    else:
        result=tresults[most_results_type]
        for oa_type in types:
            if oa_type==most_results_type:
                continue
            elif oa_type in tresults and tresults[oa_type]['count']>0:
                result['results'].extend(tresults[oa_type]['results'][:(5-len(result['results']))])
                result['count']+=tresults[oa_type]['count']
                result['type']=result['type'].append(oa_type)
            if result['count']>=5:
                break
    return result
def getAuthorPapers(display_name, user=None):
    logger.info("authorpapers [author] {} [user] {}", display_name, user.username)
    return getPapers(display_name, 'author', user)
def get_raw_data(article_id, user=None):
    article=Paper.objects.get_single_paper_data(article_id, user)
    if not article:
        return None, None, None
    article = article.first()
    openalexid=article.openalex_url
    doi = article.doi
    title = article.title

    if not any([openalexid, doi, title]):
        return None, None, None

    author_openalexids = []
    for author in article.authors.all():
        author_openalexids.append(author.openalex_url)
    source_openalexids = []
    for location in article.locations.all():
        try:
            source_openalexids.append(location.source.openalex_url)
        except Exception:
            pass

    raw_data={}
    fulljson = {}
    client=MongoClient(getattr(settings, 'MONGOURL', None))
    db=client['mus']
    cutdoi = doi.replace('https://doi.org/','')
    pure_works=db['api_responses_pure']

    if openalexid:
        openalex_works=db['api_responses_works_openalex']
        mongo_openaire_results = db['api_responses_openaire']

        raw_data['openalex_work']=openalex_works.find_one({'id':openalexid})
        raw_data['openaire']=mongo_openaire_results.find_one({'id':openalexid})
    if doi:
        crossref_info=db['api_responses_crossref']
        datacite_info=db['api_responses_datacite']
        raw_data['crossref']=crossref_info.find_one({'DOI':cutdoi})
        raw_data['datacite']=datacite_info.find_one({'doi':cutdoi})
        if raw_data.get('datacite'):
            del raw_data['datacite']['_id']
        if article.has_pure_oai_match:
            raw_data['pure']=pure_works.find_one({'identifier':{'doi':cutdoi}})
            if not raw_data.get('pure'):
                raw_data['pure']=pure_works.find_one({'identifier':{'doi':doi}})
    if article.has_pure_oai_match and not raw_data.get('pure'):
        raw_data['pure']=pure_works.find_one({'title':article.pure_entries.first().title})
    if author_openalexids != []:
        raw_data['authors']={}
        openalex_ut_authors = db['api_responses_UT_authors_openalex']
        openalex_authors = db['api_responses_authors_openalex']
        peoplepage_results = db['api_responses_UT_authors_peoplepage']
        for author_openalexid in author_openalexids:
            raw_data['authors'][author_openalexid]={}
            raw_data['authors'][author_openalexid]['openalex_author']=openalex_ut_authors.find_one({'id':author_openalexid})
            if not raw_data['authors'][author_openalexid]['openalex_author']:
                raw_data['authors'][author_openalexid]['openalex_author']=openalex_authors.find_one({'id':author_openalexid})
            raw_data['authors'][author_openalexid]['peoplepage']=peoplepage_results.find_one({'id':author_openalexid})
    if source_openalexids != []:
        openalex_journals = db['api_responses_journals_openalex']
        dealdata = db['api_responses_journals_dealdata_scraped']
        raw_data['locations']={}
        for source_openalexid in source_openalexids:
            raw_data['locations'][source_openalexid]={}
            raw_data['locations'][source_openalexid]['openalex_journal']=openalex_journals.find_one({'id':source_openalexid})
            raw_data['locations'][source_openalexid]['dealdata']=dealdata.find_one({'id':source_openalexid})



    fulljson=json.dumps(raw_data, default=str)

    return article, fulljson, raw_data

def get_chart_data():
    '''
    Preloads data from the db into separate pandas dataframes for use in making charts
    Stores the pandas dataframes on disk to load in when 'generate_chart' is called
    '''
    '''fields['author']=Author._meta.get_fields()
    fields['journal']=Journal._meta.get_fields()
    fields['location']=Location._meta.get_fields()
    fields['ut_data']=UTData._meta.get_fields()
    fields['pure_entry']=PureEntry._meta.get_fields()
    fields['authorship']=Authorship._meta.get_fields()
    fields['organization']=Organization._meta.get_fields()
    fields['affiliation']=Affiliation._meta.get_fields()
    fields['dealdata']=Dealdata._meta.get_fields()
    fields['source']=Source._meta.get_fields()'''

    allpapers = Paper.objects.filter(year__gte=2015).prefetch_related('authors', 'locations', 'pure_entries', 'authorships').select_related('journal').order_by('-year')


    data = [{'pure_entries':" | ".join([str(e.id) for e in p.pure_entries.all()]),
        'id':p.id,
        'created':p.created,
        'modified':p.modified,
        'openalex_url':p.openalex_url,
        'title':p.title,
        'doi':p.doi,
        'year':p.year,
        'citations':p.citations,
        'primary_link':p.primary_link,
        'itemtype':p.itemtype,
        'date':p.date,
        'openaccess':p.openaccess,
        'language':p.language,
        'abstract':p.abstract,
        'pages':p.pages,
        'pagescount':p.pagescount,
        'volume':p.volume,
        'issue':p.issue,
        'is_oa':p.is_oa,
        'license':p.license,
        'pdf_link_primary':p.pdf_link_primary,
        'keywords':p.keywords,
        'journal':p.journal.id if p.journal else None,
        'apc_listed_value':p.apc_listed_value,
        'apc_listed_currency':p.apc_listed_currency,
        'apc_listed_value_usd':p.apc_listed_value_usd,
        'apc_listed_value_eur':p.apc_listed_value_eur,
        'apc_paid_value':p.apc_paid_value,
        'apc_paid_currency':p.apc_paid_currency,
        'apc_paid_value_usd':p.apc_paid_value_usd,
        'apc_paid_value_eur':p.apc_paid_value_eur,
        'is_in_pure':p.is_in_pure,
        'has_pure_oai_match':p.has_pure_oai_match,
        'has_any_ut_author_year_match':p.has_any_ut_author_year_match,
        'published_print':p.published_print,
        'published_online':p.published_online,
        'published':p.published,
        'issued':p.issued,
        'topics':p.topics,
        'taverne_date':p.taverne_date,
        'authors':" | ".join([str(a.id) for a in p.authors.all()]),
        'locations':" | ".join([str(l.id) for l in p.locations.all()]),
        }
        for p in allpapers]
    paperframe = pd.DataFrame(data)
    paperframe.to_csv('paperdataframe.csv')
'''
    allauthors = Author.objects.filter(paper__in=allpapers)
    data =[{} for a in allauthors]
    authorframe = pd.DataFrame(data)
    authorframe.to_csv('authordataframe.csv')

    alllocs = Author.objects.filter(papers__in=allpapers)
    data =[{} for loc in alllocs]
    locframe = pd.DataFrame(data)
    locframe.to_csv('locationsdataframe.csv')

    allpureentries = PureEntry.objects.filter(papers__in=allpapers)
    data =[{} for p in allpureentries]
    peframe = pd.DataFrame(data)
    peframe.to_csv('pureentriesdataframe.csv')

'''
def get_oa_chart_data():
    '''
    chart 1: stacked bar with peer-reviewed items

    x-axis: year
    y-axis: %
        each bar shows % of each oa-type from this list:
            - gold doaj
            - gold non-doaj or hybrid
            - green only
            - not oa / closed
    also show total % open access (all except not oa/closed) per year
    also mark preferred route OA (immediate OA: gold, hybrid, 'bronze')
    peer-reviewed items contain these itemtypes:
    1) article
    2) letter
    3) comment / letter to the editor,
    4) article in a special issue
    5) review article

    table 1: details for items for past year (2023)
    # and % of:
    - total
    - OA publications
    - closed
    - gold DOAJ
    - Bronze (gold non-doaj) or hybrid
    - green only
        - number with 'OA procedure XXXX' ut keyword

    chart 2: same as chart 1 but for 2022 and now faculty on x-axis
    '''
    def get_fac(paper):
        faclist = []
        #grouplist = []
        for author in paper.authors.all():
            if UTData.objects.filter(employee=author).exists():
                faclist.append(author.utdata.current_faculty)
                #grouplist.append(author.utdata.current_group)
                if author.utdata.employment_data:
                    for entry in author.utdata.employment_data:
                        faclist.append(entry.get('faculty'))
                        #grouplist.append(entry.get('group'))
        faclist = list(set(faclist))
        if len(faclist) == 0:
            return None
        if len(faclist) == 1:
            return faclist[0]
        else:
            return ' | '.join(faclist)
    itemtypes = ['journal-article', 'peer-review']
    years = [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]
    papers = Paper.objects.filter(Q(year__in=years) & Q(itemtype__in=itemtypes)).get_table_prefetches()
    data = [{
        'id':p.id,
        'oa_type':p.openaccess,
        'is_oa':p.is_oa,
        'has_pure_entry':p.pure_entries.exists(),
        'year':p.year,
        'itemtype':p.itemtype,
        'faculty':get_fac(p)
            } for p in papers
    ]
    oadf = pd.DataFrame(data)
    oadf.to_csv('oachartdata.csv')

def generate_oa_chart():
    import plotly.express as px
    try:
        oachartdata = pd.read_csv('oachartdata.csv')
    except FileNotFoundError:
        get_oa_chart_data()
        oachartdata = pd.read_csv('oachartdata.csv')
    years = [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]
    oatypes = ['green', 'closed', 'bronze', 'gold','hybrid']
    resultsy = []
    resultsf = []
    for year in years:
        yearpapers=oachartdata[oachartdata['year']==year]
        result = {}
        total = yearpapers.shape[0]

        resultsy.append(result)
        for oatype in oatypes:
            result = {'year':year}
            count = yearpapers[yearpapers['oa_type'] == oatype].shape[0]
            percent = round(count*100/total,0)
            result['type'] = oatype
            result['count'] = int(count)
            result['percent'] = int(percent)
            resultsy.append(result)
    papers2023=oachartdata[oachartdata['year']==2023]
    faculties = ['EEMCS', 'BMS', 'EE', 'ITC', 'TNW']
    for fac in faculties:
        result = {'faculty':fac}
        papers2023['faculty_clean'] = papers2023['faculty'].fillna('').astype(str)

        msk = papers2023['faculty_clean'].str.contains(fac)
        total = papers2023[msk].shape[0]

        for oatype in oatypes:
            result = {'faculty':fac}
            count = papers2023[(papers2023['oa_type'] == oatype) & msk].shape[0]
            percent = round(count*100/total,0)
            result['type'] = oatype
            result['count'] = int(count)
            result['percent'] = int(percent)
            resultsf.append(result)



    dfoay = pd.DataFrame(resultsy)
    dfoay=dfoay.sort_values(by=['year'])
    print(dfoay.info(verbose=True))
    print(dfoay)
    dfoaf = pd.DataFrame(resultsf)
    print(dfoay.info(verbose=True))
    print(dfoaf)
    fig = px.bar(dfoay, x="year", y="count", color="type")
    fig2 = px.bar(dfoaf, x="faculty", y="count", color="type")
    return [fig.to_html(), fig2.to_html()]

def generate_chart(parameters, user):
    '''
    returns a html chart with given params for user

    '''
    dataoa = []
    oatypes = ['green', 'bronze', 'closed', 'hybrid', 'gold']
    years = ['2016','2017','2018', '2019', '2020', '2021', '2022', '2023']
    groups = []
    groups.extend(EEGROUPSABBR)
    groups.extend(TCSGROUPSABBR)
    groups=list(set(groups))
    types = ['proceedings-article', 'journal-article']
    baseline_tcs= defaultdict()
    baseline_ee= defaultdict()
    for year in years:
        baseline_tcs[year]=defaultdict(int)
        baseline_ee[year]=defaultdict(int)

    for group in groups:
        print('=========================')
        filters= [['start_date','2016-01-01'],['end_date', '2023-12-31'],['group',group], ['itemtype', types]]
        facultyname, stats, listpapers = getPapers('all', filters, user)
        print(group)
        print(stats)
        for year in years:
            immediate=0
            delayed=0
            total=0

            yearpapers=listpapers.filter(year=year)
            for oatype in oatypes:
                count = yearpapers.filter(openaccess=oatype).count()
                if oatype in ['gold', 'hybrid', 'bronze']:
                    immediate += count
                else:
                    delayed += count
                #dataoa.append({'faculty':faculty, 'year':year,'counttype':oatype,'count':count})
            #for type in types:
            #    count = yearpapers.filter(itemtype=type).count()
            #    datatypes.append({'faculty':faculty, 'year':year,'counttype':type,'count':count})
            value = round(immediate*100/(immediate+delayed),0)
            total = immediate+delayed
            #value = delayed*100/(immediate+delayed)
            dept=''
            if group in EEGROUPSABBR and group in TCSGROUPSABBR:
                dept = 'Mixed'
            elif group in TCSGROUPSABBR:
                dept = 'TCS'
            elif group in EEGROUPSABBR:
                dept = 'EE'
            if group in TCSGROUPSABBR :
                baseline_tcs[year]['count'] += value
                baseline_tcs[year]['amount'] += immediate
                baseline_tcs[year]['total'] += total
            elif group in EEGROUPSABBR :
                baseline_ee[year]['count'] += value
                baseline_ee[year]['amount'] += immediate
                baseline_ee[year]['total'] += total

            dataoa.append({'group':group, 'dept':dept,'year':year,'counttype':'gold/hybrid/bronze','count':value, 'amount':immediate, 'total':total})

    for year in years:
        baseline_tcs[year]['count']/=len(TCSGROUPSABBR)
        baseline_ee[year]['count']/=len(EEGROUPSABBR)
        baseline_tcs[year]['count']=round(baseline_tcs[year]['count'],0)
        baseline_ee[year]['count']=round(baseline_ee[year]['count'],0)
    dfoa = pd.DataFrame(dataoa)
    dfoa=dfoa.sort_values(by=['year', 'dept', 'count'], ascending=[True, True, False])
    #dftypes= pd.DataFrame(datatypes)
    print(dfoa.info(verbose=True))

    fig = go.Figure()
    for group in groups:
        if group in EEGROUPSABBR and group in TCSGROUPSABBR:
            color='#474967'
        elif group in TCSGROUPSABBR:
            color='#337357'
        elif group in EEGROUPSABBR:
            color='#5E1675'
        else:
            color='#FFD23F'

        curdata=dfoa[dfoa['group']==group]
        dept=dfoa[dfoa['group']==group]['dept'].values[0]
        fig.add_trace(go.Bar(x=curdata['year'],
                y=curdata['amount'],
                name=group,
                text=group,
                textposition='auto',
                hoverinfo='text',
                hovertext=' ['+dept+']['+group+'] '+curdata['count'].astype(str)+'% '+curdata['counttype'].astype(str)+' - '+curdata['amount'].astype(str)+'/'+curdata['total'].astype(str)+' total',
                marker_color=color,
                ))
    if False:
        fig.add_trace(go.Scatter(
            x=[*baseline_ee.keys()],
            y=[year['amount'] for year in [*baseline_ee.values()]],
            mode='lines+markers',
            name='EE total gold/hybrid/bronze',
            marker_color='#5E1675',
            marker_size=[year['count'] for year in [*baseline_ee.values()]],

            ))

        fig.add_trace(go.Scatter(
            x=[*baseline_tcs.keys()],
            y=[year['amount'] for year in [*baseline_tcs.values()]],
            mode='lines+markers',
            name='TCS total gold/hybrid/bronze',
            marker_color='#337357',
            marker_size=[year['count'] for year in [*baseline_tcs.values()]],
            ))
    fig.update_layout(barmode='group', uniformtext_minsize=8, uniformtext_mode='hide', )
    fig.update_xaxes(type='category')


    return fig.to_html()

def read_log(filename='log_mus.log', maxlines=10000):
    if filename=='db_updates.log':
        lines = []
        updates = DBUpdate.objects.filter(created__gte=datetime.now() - timedelta(days=4)).order_by('-created')
        for i, update in enumerate(updates.all()):
            lines.append(str(f'DB UPDATE {i+1}/{updates.count()}'))
            lines.append('Date run: '+ str(update.created))
            lines.append('Data source: '+ str(update.update_source))
            lines.append('Update type: '+ str(update.update_type))
            lines.append('Details: ')
            for key, value in update.details.items():
                if len(str(value)) < 500:
                    lines.append('  '+str(key)+': '+str(value))
                else:
                    lines.append('  '+str(key)+': '+str(value)[0:1000]+'...')
            lines.append('')
        lines.reverse()
        with open(filename, 'w') as f:
            for line in lines:
                f.write(line+'\n')

    lineset=[]
    with open(filename, 'r') as f:
        lineset = f.readlines()
    lineset.reverse()
    if len(lineset) > maxlines:
        lineset = lineset[0:maxlines]
    return lineset
