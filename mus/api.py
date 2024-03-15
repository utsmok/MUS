from ninja import NinjaAPI, FilterSchema, Schema, Query
from ninja.orm import create_schema
from PureOpenAlex.models import Paper, PureEntry, viewPaper, Journal, Organization, Author, PilotPureData, Source
from PureOpenAlex.data_view import getTablePrefetches
from ninja.pagination import paginate
from typing import List, Optional
from ninja.renderers import BaseRenderer
import orjson
from django.db.models import Q
from datetime import date
from rich import print
FACULTYNAMES = ["EEMCS", "BMS", "ET", "ITC", "TNW", 'eemcs', 'bms', 'et', 'itc','tnw']
OATYPES = ['green', 'bronze', 'closed', 'hybrid', 'gold']
ITEMTYPES = ['journal-article', 'proceedings', 'proceedings-article','book', 'book-chapter']
class PaperFilter(FilterSchema):

    faculties: Optional[List[str]] = None
    def filter_faculties(self, value: List[str]) -> Q:
        queries = Q()
        if value:
            for faculty in value:
                faculty = faculty.upper()
                if faculty in FACULTYNAMES:
                    queries = queries | Q(authorships__author__utdata__current_faculty=faculty)
        return queries
    
    openaccess_type: Optional[List[str]] = None
    def filter_openaccess_type(self, value: List[str]) -> Q:
        queries = Q()
        if value:
            for oatype in value:
                oatype = oatype.lower()
                if oatype in OATYPES:
                    queries = queries | Q(openaccess=oatype)
        return queries
    
    item_type: Optional[List[str]] = None
    def filter_item_type(self, value: List[str]) -> Q:
        queries = Q()
        if value:
            for itemtype in value:
                itemtype = itemtype.lower()
                if itemtype in ITEMTYPES:
                    queries = queries | Q(itemtype=itemtype)
                elif itemtype == 'other':
                    queries = queries | ~Q(itemtype__in=ITEMTYPES)
        return queries
    
    groups: Optional[List[str]] = None
    def filter_groups(self, value: List[str]) -> Q:
        queries = Q()
        if value:
            for group in value:
                group = group.upper()
                queries = queries | Q(authorships__author__utdata__current_group=group)
        return queries
    
    date_start: Optional[date] = None
    def filter_date_start(self, value: date) -> Q:
        if value:
            value=value.strftime('%Y-%m-%d')
            return Q(date__gte=value)
        return Q()
    
    date_end: Optional[date] = None
    def filter_date_end(self, value: date) -> Q:
        if value:
            value=value.strftime('%Y-%m-%d')
            return Q(date__lte=value)
        return Q()
    
    is_in_pure: Optional[bool] = None
    has_pure_oai_match: Optional[bool] = None
    is_oa: Optional[bool] = None
    after_taverne: Optional[bool] = None
    def filter_after_taverne(self, value: bool) -> Q:
        if value is None:
            return Q()
        if value:
            return Q(taverne_date__gte=date.today())
        return ~Q(taverne_date__gte=date.today())


class NotFoundSchema(Schema):
    error: int
    exception: str
    msg: str 

PaperSchema = create_schema(Paper,depth=0)
PureEntrySchema = create_schema(PureEntry, depth=0)
ViewPaperSchema = create_schema(viewPaper, depth=1)
JournalSchema = create_schema(Journal, depth=1)
OrganizationSchema = create_schema(Organization, depth=1)
AuthorSchema = create_schema(Author, depth=1)
PilotPureDataSchema = create_schema(PilotPureData, exclude=['apc_paid_amount'], depth=1)
SourceSchema = create_schema(Source, depth=1)

class ORJSONRenderer(BaseRenderer):
    media_type = "application/json"

    def render(self, request, data, *, response_status):
        return orjson.dumps(data)

api = NinjaAPI(renderer=ORJSONRenderer())

@api.get('/papers', response=List[PaperSchema])
@paginate
def list_papers(request, filters: PaperFilter = Query(...)):
    papers =  Paper.objects.all()
    papers = filters.filter(papers)
    papers = papers.select_related('journal').prefetch_related(*getTablePrefetches(papers))
    return papers

@api.get('/paper/{int:paper_id}', response={200:PaperSchema,404:NotFoundSchema})
def paper(request, paper_id: int):
    try:
        paper = Paper.objects.get(id=paper_id)
        return 200, paper
    except Paper.DoesNotExist:
        return 404, {'msg': f'Paper with id {paper_id} not found.'}
    
@api.get('/doi/{path:doi}', response={200:PaperSchema,404:NotFoundSchema})
def paper_by_doi(request, doi: str):
    try:
        paper = Paper.objects.get(doi__icontains=doi)
        return 200, paper
    except Paper.DoesNotExist:
        return 404, {'error':404,'exception':'Paper.DoesNotExist','msg': f'No Paper with doi {doi} in database.'}
    except Paper.MultipleObjectsReturned:
        return 404, {'error':404,'exception':'Paper.MultipleObjectsReturned','msg': f"Multiple Papers with doi {doi} found. You've probably used a partial doi as the query."}


@api.get('/pureentries', response=List[PureEntrySchema])
@paginate
def list_pureentries(request):
    return PureEntry.objects.all().select_related('journal','paper', 'pilot_pure_data').prefetch_related('authors')

@api.get('/viewpapers', response=List[ViewPaperSchema])
@paginate
def list_viewpapers(request):
    return viewPaper.objects.all().select_related('displayed_paper', 'user')

@api.get('/journals', response=List[JournalSchema])
@paginate
def list_journals(request):
    return Journal.objects.all().select_related('dealdata')

@api.get('/organizations', response=List[OrganizationSchema])
@paginate
def list_organizations(request):
    return Organization.objects.all()

@api.get('/authors', response=List[AuthorSchema])
@paginate
def list_authors(request):
    return Author.objects.all().select_related('utdata').prefetch_related('affils')

@api.get('/pilotpure', response=List[PilotPureDataSchema])
@paginate
def list_pilot_data(request):
    return PilotPureData.objects.all()

@api.get('/sources', response=List[SourceSchema])
@paginate
def list_sources(request):
    return Source.objects.all()