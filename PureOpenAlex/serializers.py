from ninja import NinjaAPI, FilterSchema, Schema, Query, ModelSchema, Field
from ninja.orm import create_schema
from ninja.renderers import BaseRenderer
from ninja.parser import Parser
from PureOpenAlex.models import Paper, PureEntry, viewPaper, Journal, Organization, Author, PilotPureData, Source
from ninja.pagination import paginate
from typing import List, Optional, Optional, Any
from datetime import datetime
from datetime import date as datetime_date
import orjson
from django.db.models import Q
from rich import print
import time
import csv

class OrganizationSchema(Schema):
    name: Optional[str] = None
    country_code: Optional[str] = None
    ror: Optional[str] = None
    type: Optional[str] = None
    data_source: Optional[str] = None
    openalex_url: Optional[str] = None

class DealDataSchema(Schema):
    deal_status: str = None
    publisher: str = None
    jb_url: str = None
    oa_type: str = None

class JournalSchema(Schema):
    name: Optional[str] = None
    e_issn: Optional[str] = None
    issn: Optional[str] = None
    host_org: Optional[str] = None
    is_in_doaj: Optional[bool] = None  
    is_oa: Optional[bool] = None
    type: Optional[str] = None
    keywords: Optional[Any] = None
    publisher: Optional[str] = None
    openalex_url: Optional[str] = None
    dealdata: Optional[DealDataSchema] = None

class UTDataSchema(Schema):
    current_position: Optional[str] = None
    current_group: Optional[str] = None
    current_faculty: Optional[str] = None
    employment_data: Optional[Any] = None
    email: Optional[str] = None

class AuthorSchema(Schema):
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    initials: Optional[str] = None
    affils: Optional[OrganizationSchema] = None
    orcid: Optional[str] = None
    is_ut: Optional[bool] = None
    openalex_url: Optional[str] = None
    known_as: Optional[Any] = None
    scopus_id: Optional[str] = None
    utdata: Optional[UTDataSchema] = None
    
    @staticmethod
    def resolve_utdata(obj):
        try:
            if not obj.utdata:
                return
        except Exception:
            return
        return UTDataSchema().from_orm(obj.utdata).dict()



class SourceSchema(Schema):
    openalex_url: Optional[str] = None
    homepage_url: Optional[str] = None
    display_name: Optional[str] = None
    e_issn: Optional[str] = None
    issn: Optional[str] = None
    host_org: Optional[str] = None
    type: Optional[str] = None
    is_in_doaj: Optional[bool] = None

class LocationSchema(Schema):
    is_accepted: Optional[bool] = None
    is_oa: Optional[bool] = None 
    is_published: Optional[bool] = None
    license: Optional[str] = None
    landing_page_url: Optional[str] = None
    source: Optional[SourceSchema] = None
    is_primary: Optional[bool] = None
    is_best_oa: Optional[bool] = None
    pdf_url: Optional[str] = None

class PureEntrySchema(Schema):
    title: Optional[str] = None
    authors: List[AuthorSchema] = None
    language: Optional[str] = None
    date: Optional[str] = None
    year: Optional[str] = None
    rights: Optional[str] = None
    format: Optional[str] = None
    itemtype: Optional[str] = None
    abstract: Optional[str] = None
    source: Optional[str] = None
    publisher: Optional[str] = None
    ut_keyword: Optional[str] = None
    doi: Optional[str] = None
    isbn: Optional[str] = None
    researchutwente: Optional[str] = None
    risutwente: Optional[str] = None
    scopus: Optional[str] = None
    other_links: Optional[Any] = None
    duplicate_ids: Optional[Any] = None
    journal: Optional[JournalSchema] = None
    keywords: Optional[Any] = None

class PaperSchema(Schema):
    id: int = Field(None, alias='id')
    openalex_url: Optional[str] = Field(None, alias='openalex_url')
    title: Optional[str] = Field(None, alias='title')
    doi: Optional[str] = Field(None, alias='doi')
    year: Optional[str] = Field(None, alias='year')
    citations: Optional[int] = Field(None, alias='citations')
    primary_link: Optional[str] = Field(None, alias='primary_link')
    itemtype: Optional[str] = Field(None, alias='itemtype')
    date: Optional[datetime_date] = Field(None, alias='date')
    openaccess: Optional[str] = Field(None, alias='openaccess')
    language: Optional[str] = Field(None, alias='language')
    abstract: Optional[str] = Field(None, alias='abstract')
    pages: Optional[str] = Field(None, alias='pages')
    pagescount: Optional[int] = Field(None, alias='pagescount')
    volume: Optional[str] = Field(None, alias='volume')
    issue: Optional[str] = Field(None, alias='issue')
    is_oa: Optional[bool] = Field(None, alias='is_oa')
    license: Optional[str] = Field(None, alias='license')
    pdf_link_primary: Optional[str] = Field(None, alias='pdf_link_primary')
    keywords: Optional[Any] = Field(None, alias='keywords')
    journal: Optional[JournalSchema] = Field(None, alias='journal')
    apc_listed_value: Optional[int] = Field(None, alias='apc_listed_value')
    apc_listed_currency: Optional[str] = Field(None, alias='apc_listed_currency')
    apc_listed_value_usd: Optional[int] = Field(None, alias='apc_listed_value_usd')
    apc_listed_value_eur: Optional[int] = Field(None, alias='apc_listed_value_eur')
    apc_paid_value: Optional[int] = Field(None, alias='apc_paid_value')
    apc_paid_currency: Optional[str] = Field(None, alias='apc_paid_currency')
    apc_paid_value_usd: Optional[int] = Field(None, alias='apc_paid_value_usd')
    apc_paid_value_eur: Optional[int] = Field(None, alias='apc_paid_value_eur')
    is_in_pure: Optional[bool] = Field(None, alias='is_in_pure')
    has_pure_oai_match: Optional[bool] = Field(None, alias='has_pure_oai_match')
    has_any_ut_author_year_match: Optional[bool] = Field(None, alias='has_any_ut_author_year_match')
    published_print: Optional[datetime_date] = Field(None, alias='published_print')
    published_online: Optional[datetime_date] = Field(None, alias='published_online')
    published: Optional[datetime_date] = Field(None, alias='published')
    issued: Optional[datetime_date] = Field(None, alias='issued')
    topics: Optional[Any] = Field(None, alias='topics')
    authors: Optional[List[AuthorSchema]] = None
    locations: Optional[List[LocationSchema]] = None
    pure_entries: Optional[List[PureEntrySchema]] = None

    @staticmethod
    def resolve_pure_entries(obj):
        try:
            if not obj.pure_entries:
                return
        except Exception:
            return

        return [PureEntrySchema().from_orm(i).dict() for i in obj.pure_entries.all()]

class ORJSONRenderer(BaseRenderer):
    media_type = "application/json"

    def render(self, request, data, *, response_status):
        return orjson.dumps(data)
    
class ORJSONParser(Parser):
    def parse_body(self, request):
        return orjson.loads(request.body)
    
def serialize_as_list_of_dicts(papers):
    results = [PaperSchema().from_orm(i).dict() for i in papers]
    return results

