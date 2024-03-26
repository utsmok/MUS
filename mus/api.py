from ninja import NinjaAPI, FilterSchema, Schema, Query
from ninja.orm import create_schema
from PureOpenAlex.models import Paper, PureEntry, viewPaper, Journal, Organization, Author, PilotPureData, Source
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

PaperSchema = create_schema(Paper,depth=2)
PureEntrySchema = create_schema(PureEntry, depth=3)
ViewPaperSchema = create_schema(viewPaper, depth=3)
JournalSchema = create_schema(Journal, depth=1)
OrganizationSchema = create_schema(Organization, depth=1)
AuthorSchema = create_schema(Author, depth=3)
PilotPureDataSchema = create_schema(PilotPureData, exclude=['apc_paid_amount'], depth=1)
SourceSchema = create_schema(Source, depth=1)

class ORJSONRenderer(BaseRenderer):
    media_type = "application/json"
    def render(self, request, data, *, response_status):
        return orjson.dumps(data)

api = NinjaAPI(renderer=ORJSONRenderer())

@api.get('/papers', response=List[PaperSchema])
@paginate
# def list_papers(request, filters: PaperFilter = Query(...)):
def list_papers(request):
    return Paper.objects.all().select_related('journal').get_table_prefetches()

@api.get('/paper/{int:paper_id}', response={200:PaperSchema,404:NotFoundSchema})
def paper(request, paper_id: int):
    try:
        return 200, Paper.objects.filter(id=paper_id).select_related('journal').get_table_prefetches().first()
    except Paper.DoesNotExist:
        return 404, {'msg': f'Paper with id {paper_id} not found.'}

@api.get('/doi/{path:doi}', response={200:PaperSchema,404:NotFoundSchema})
def paper_by_doi(request, doi: str):
    try:
        return 200, Paper.objects.get(doi__icontains=doi)
    except Paper.DoesNotExist:
        return 404, {'error':404,'exception':'Paper.DoesNotExist','msg': f'No Paper with doi {doi} in database.'}
    except Paper.MultipleObjectsReturned:
        return 404, {'error':404,'exception':'Paper.MultipleObjectsReturned','msg': f"Multiple Papers with doi {doi} found. You've probably used a partial doi as the query."}

@api.get('/pureentries', response=List[PureEntrySchema])
@paginate
def list_pureentries(request):
    return PureEntry.objects.all().select_related('journal','paper', 'pilot_pure_data').prefetch_related('authors')

@api.get('/pureentry/{int:pure_entry_id}', response={200:PureEntrySchema,404:NotFoundSchema})
def pureentry(request, pure_entry_id: int):
    try:
        return 200, PureEntry.objects.filter(id=pure_entry_id).select_related('journal','paper', 'pilot_pure_data').prefetch_related('authors').first()
    except PureEntry.DoesNotExist:
        return 404, {'error':404,'exception':'PureEntry.DoesNotExist','msg': f'No PureEntry with id {pure_entry_id} in database.'}

@api.get('/viewpapers', response=List[ViewPaperSchema])
@paginate
def list_viewpapers(request):
    return viewPaper.objects.all().select_related('displayed_paper', 'user')

@api.get('/journals', response=List[JournalSchema])
@paginate
def list_journals(request):
    return Journal.objects.all().select_related('dealdata')

@api.get('/journal/{int:journal_id}', response={200:JournalSchema,404:NotFoundSchema})
def journal(request, journal_id: int):
    try:
        journal=Journal.objects.get(id=journal_id).__dict__
        for key, value in journal.items():
            if value is None:
                if key in ['is_oa', 'is_in_doaj']:
                    journal[key]=False
                else:
                    journal[key]=''
        return 200, journal
    except Journal.DoesNotExist:
        return 404, {'error':404,'exception':'Journal.DoesNotExist','msg': f'No Journal with id {journal_id} in database.'}
@api.get('/organizations', response=List[OrganizationSchema])
@paginate
def list_organizations(request):
    return Organization.objects.all()

@api.get('/organization/{int:organization_id}', response={200:OrganizationSchema,404:NotFoundSchema})
def organization(request, organization_id: int):
    try:
        return 200, Organization.objects.filter(id=organization_id).first()
    except Organization.DoesNotExist:
        return 404, {'error':404,'exception':'Organization.DoesNotExist','msg': f'No Organization with id {organization_id} in database.'}

@api.get('/authors', response=List[AuthorSchema])
@paginate
def list_authors(request):
    return Author.objects.all().select_related('utdata').prefetch_related('affils')

@api.get('/author/{int:author_id}', response={200:AuthorSchema,404:NotFoundSchema})
def author(request, author_id: int):
    try:
        return 200, Author.objects.filter(id=author_id).select_related('utdata').prefetch_related('affils').first()
    except Author.DoesNotExist:
        return 404, {'error':404,'exception':'Author.DoesNotExist','msg': f'No Author with id {author_id} in database.'}

@api.get('/pilotpure', response=List[PilotPureDataSchema])
@paginate
def list_pilot_data(request):
    return PilotPureData.objects.all()
@api.get('/pilotpure/{int:pilotpure_id}', response={200:PilotPureDataSchema,404:NotFoundSchema})
def pilotpure(request, pilotpure_id: int):
    try:
        return 200, PilotPureData.objects.filter(id=pilotpure_id).first()
    except PilotPureData.DoesNotExist:
        return 404, {'error':404,'exception':'PilotPureData.DoesNotExist','msg': f'No PilotPureData with id {pilotpure_id} in database.'}
@api.get('/sources', response=List[SourceSchema])
@paginate
def list_sources(request):
    return Source.objects.all()

@api.get('/source/{int:source_id}', response={200:SourceSchema,404:NotFoundSchema})
def source(request, source_id: int):
    try:
        return 200, Source.objects.filter(id=source_id).first()
    except Source.DoesNotExist:
        return 404, {'error':404,'exception':'Source.DoesNotExist','msg': f'No Source with id {source_id} in database.'}