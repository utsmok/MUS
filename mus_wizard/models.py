from django.db import models
from django.db.models import Q
from django_extensions.db.models import TimeStampedModel
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.utils.translation import gettext_lazy as _
from django.core.serializers.json import DjangoJSONEncoder
'''

The detailed data from the APIs as stored in MongoDB can be
stored in the SQL DB as a single JSON in the form of a MongoData entry,
which has a many-to-one relationship with each other model
(each mongodata entry only has a single link, but each model instance can have multiple data sources)
'''

class MongoData(TimeStampedModel, models.Model):
    class MongoCollections(models.TextChoices):
        WORKS_OPENALEX = 'works_openalex'
        AUTHORS_OPENALEX = 'authors_openalex'
        TOPICS_OPENALEX = 'topics_openalex'
        SOURCES_OPENALEX = 'sources_openalex'
        FUNDERS_OPENALEX = 'funders_openalex'
        PUBLISHERS_OPENALEX = 'publishers_openalex'
        INSTITUTIONS_OPENALEX = 'institutions_openalex'
        AUTHORS_PURE = 'authors_pure'
        EMPLOYEES_PEOPLEPAGE = 'employees_peoplepage'
        DEALS_JOURNALBROWSER = 'deals_journalbrowser'
        ITEMS_CROSSREF = 'items_crossref'
        ITEMS_DATACITE = 'items_datacite'
        ITEMS_OPENAIRE = 'items_openaire'
        ITEMS_ORCID = 'items_orcid'

    data = models.JSONField(encoder=DjangoJSONEncoder)
    source_collection = models.CharField(choices=MongoCollections) # the mongodb collection this data is from
    source_id = models.CharField() # the _id of the doc in the mongodb collection
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        indexes = [
            models.Index(fields=["content_type", "object_id", "source_collection"]),
        ]

'''
Each model also has a built-in many-to-many relationship with the 'Tag' model, which is a simple
tagging system for the data, with some simple tag types to start with.
A 'notes' field is included in the tag model --
a JSON field that can be used to store arbitrary data.

'''

class Tag(TimeStampedModel, models.Model):
    class TagTypes(models.TextChoices):
        PEER_REVIEWED = 'PR' # peer-reviewed works (item type grouping)
        ONLY_REPO = 'OR' # work only found in repository -- no matches in other apis
        FOUND_IN_REPOSITORY = 'FR' # work found in repository of primary institute
        REPO_FOUND_IN_OPENALEX = 'RF' # repository of primary institute found in OpenAlex Locations for this work
        INSTITUTE_AUTHOR_MATCH = 'IA' # at least one of the authors of work has affiliation w/ primary instutution in the publication year of the work
        HAS_ERROR = 'HE' # item is tagged as having an error, needs repairs -- details in 'notes' field
        GENERIC = 'GN' # generic tag, not specific to any type -- used as default
        ORG_TYPE = 'OT' # organization type -- actual type in 'notes' field

    tag_type = models.CharField(choices=TagTypes, default=TagTypes.GENERIC, max_length=2)
    notes = models.CharField(default='', blank=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    def __str__(self):
        return f'{self.tag_type} - {self.notes}'
    class Meta:
        indexes = [
            models.Index(fields=["content_type", "object_id",  "tag_type"]),
        ]

'''
base class for the rest of the models: tags and raw_data as explained above + timestamps from TimeStampedModel
'''
class MusModel(TimeStampedModel, models.Model):
    raw_data = GenericRelation(MongoData)
    tags = GenericRelation(Tag)
    class Meta:
        abstract = True

'''
Below: all actual models, inheriting from MusModel
The base design is mostly from OpenAlex, but with some modifications to fit the rest
'''
class Group(models.Model):
    '''
    simple class to hold data for author's group (+ faculty)
    will be used in Affiliation model if the Organization == the primary institution
    '''
    name = models.CharField()
    faculty = models.CharField(null=True)
    internal_repository_id = models.CharField(null=True)
    org_type = models.CharField(null=True)
    scopus_affiliation_ids = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    acronym = models.CharField(null=True)
    part_of = models.ManyToManyField('self', related_name="subgroups", symmetrical=False)
    def __str__(self):
        return f'{self.name} ({self.faculty})'
    class Meta:
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["faculty"]),
            models.Index(fields=["internal_repository_id"]),
            models.Index(fields=["org_type"]),
            models.Index(fields=["acronym"]),
            
        ]

class Topic(MusModel):
    class DomainTypes(models.TextChoices):
        PHYSICAL_SCIENCES = 'Physical Sciences'
        SOCIAL_SCIENCES = 'Social Sciences'
        HEALTH_SCIENCES = 'Health Sciences'
        LIFE_SCIENCES = 'Life Sciences'
    class FieldTypes(models.TextChoices):
        MEDICINE = 'Medicine'
        SOCIAL_SCIENCES = 'Social Sciences'
        ENGINEERING = 'Engineering'
        ARTS_AND_HUMANITIES = 'Arts and Humanities'
        COMPUTER_SCIENCE = 'Computer Science'
        BIOCHEMISTRY_GENETICS_AND_MOLECULAR_BIOLOGY = 'Biochemistry, Genetics and Molecular Biology'
        AGRICULTURAL_AND_BIOLOGICAL_SCIENCES = 'Agricultural and Biological Sciences'
        ENVIRONMENTAL_SCIENCE = 'Environmental Science'
        PHYSICS_AND_ASTRONOMY = 'Physics and Astronomy'
        BUSINESS_MANAGEMENT_AND_ACCOUNTING = 'Business, Management and Accounting'
        MATERIALS_SCIENCE = 'Materials Science'
        ECONOMICS_ECONOMETRICS_AND_FINANCE = 'Economics, Econometrics and Finance'
        HEALTH_PROFESSIONS = 'Health Professions'
        PSYCHOLOGY = 'Psychology'
        CHEMISTRY = 'Chemistry'
        EARTH_AND_PLANETARY_SCIENCES = 'Earth and Planetary Sciences'
        NEUROSCIENCE = 'Neuroscience'
        MATHEMATICS = 'Mathematics'
        IMMUNOLOGY_AND_MICROBIOLOGY = 'Immunology and Microbiology'
        DECISION_SCIENCES = 'Decision Sciences'
        ENERGY = 'Energy'
        NURSING = 'Nursing'
        PHARMACOLOGY_TOXICOLOGY_AND_PHARMACEUTICALS = 'Pharmacology, Toxicology and Pharmaceutics'
        DENTISTRY = 'Dentistry'
        CHEMICAL_ENGINEERING = 'Chemical Engineering'
        VETERINARY = 'Veterinary'

    siblings = models.ManyToManyField('self', related_name="set_siblings", symmetrical=False)

    description = models.CharField()
    name = models.CharField()
    domain = models.CharField(choices=DomainTypes.choices)
    field = models.CharField(choices=FieldTypes.choices)
    openalex_id = models.URLField(max_length=20000,unique=True)
    works_count = models.IntegerField()
    keywords = models.JSONField(encoder=DjangoJSONEncoder)
    wikipedia = models.URLField(max_length=20000)
    subfield = models.CharField()
    subfield_id = models.IntegerField()

    def __str__(self):
        return f'{self.name} [{self.field}]'

    class Meta:
        indexes = [
            models.Index(fields=["openalex_id"]),
            models.Index(fields=["wikipedia"]),
        ]

class SourceTopic(MusModel):
    source = models.ForeignKey('Source', on_delete=models.CASCADE, related_name="source_topics", db_index=True)
    topic = models.ForeignKey('Topic', on_delete=models.CASCADE, related_name="source_topics", db_index=True)
    count = models.IntegerField()

    def __str__(self):
        return f'{self.topic} | {self.count}'

    class Meta:
        indexes = [
            models.Index(fields=["source", "topic"]),
        ]
class OrganizationTopic(MusModel):
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name="organization_topics", db_index=True)
    topic = models.ForeignKey('Topic', on_delete=models.CASCADE, related_name="organization_topics", db_index=True)
    count = models.IntegerField()

    def __str__(self):
        return f'{self.topic} | {self.count}'

    class Meta:
        indexes = [
            models.Index(fields=["organization", "topic"]),
        ]
class Funder(MusModel):
    as_other_funders = models.ManyToManyField('Funder', related_name="other_funders_entries")

    openalex_id = models.URLField(max_length=20000)
    name = models.CharField()
    alternate_names = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    country_code = models.CharField(null=True)
    counts_by_year = models.JSONField(encoder=DjangoJSONEncoder)
    openalex_created_date = models.DateField()
    openalex_updated_date = models.DateTimeField()
    grants_count = models.IntegerField()
    description = models.CharField(null=True)
    homepage_url = models.URLField(max_length=20000,null=True)
    ror = models.URLField(max_length=20000,null=True)
    wikidata = models.URLField(max_length=20000,null=True)
    crossref = models.CharField(null=True)
    doi = models.URLField(max_length=20000,null=True)
    image_thumbnail_url = models.URLField(max_length=20000,null=True)
    image_url = models.URLField(max_length=20000,null=True)

    impact_factor = models.FloatField()
    h_index = models.IntegerField()
    i10_index = models.IntegerField()
    works_count = models.IntegerField()
    cited_by_count = models.IntegerField()

    internal_repository_id = models.CharField(null=True)
    def __str__(self):
        return f'{self.name}'

    class Meta:
        indexes = [
            models.Index(fields=["openalex_id"]),
            models.Index(fields=["doi"]),
            models.Index(fields=["ror"]),
            models.Index(fields=["crossref"]),
            models.Index(fields=["country_code"]),
            models.Index(fields=["image_url"]),
            models.Index(fields=["image_thumbnail_url"]),
            models.Index(fields=["wikidata"]),
            models.Index(fields=["internal_repository_id"]),
        ]


# TODO: Organization types
# idea: use tags of tagtype 'ORG_TYPE' ('OT') to store the type of this institution instance + all related institutions (see 'roles' field in api data)
# note: double check for accidental duplicates when going through the list of related items!!
# the actual type should be in the 'notes' field of the tag
# these are the types that can be used:
# education, funder, healthcare, company, archive, nonprofit, government, facility, other

class Organization(MusModel):
    '''
    Organizations are currently all OpenAlex Institutions -- but data from other sources will be added in the future.
    lineage points to parent orgs, repos point to repositories that this org manages.
    Other organization types like Funders and Publishers will link to this model to indicate their relationship,
    keeping this model as the base.
    '''
    topics = models.ManyToManyField('Topic', through='OrganizationTopic', related_name="organizations")
    repositories = models.ManyToManyField('Source', related_name="repositories")
    lineage = models.ManyToManyField('Organization', related_name="org_children")

    name = models.CharField()
    name_acronyms = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    name_alternatives = models.JSONField(encoder=DjangoJSONEncoder, null=True)

    ror = models.CharField(null=True)
    openalex_id = models.URLField(max_length=20000)
    wikipedia = models.URLField(max_length=20000,null=True)
    wikidata = models.URLField(max_length=20000,null=True)
    openalex_created_date = models.DateField()
    openalex_updated_date = models.DateTimeField()
    country_code = models.CharField(null=True)

    works_count = models.IntegerField(null=True)
    cited_by_count = models.IntegerField(null=True)
    impact_factor = models.FloatField(null=True)
    h_index = models.IntegerField(null=True)
    i10_index = models.IntegerField(null=True)

    image_thumbnail_url = models.URLField(max_length=20000,null=True)
    image_url = models.URLField(max_length=20000,null=True)
    internal_repository_id = models.CharField(null=True)
    def __str__(self):
        return f'{self.name}'

    class Meta:
        indexes = [
            models.Index(fields=["openalex_id"]),
            models.Index(fields=["ror"]),
            models.Index(fields=["wikipedia"]),
            models.Index(fields=["wikidata"]),
            models.Index(fields=["country_code"]),
            models.Index(fields=["image_url"]),
            models.Index(fields=["image_thumbnail_url"]),
            models.Index(fields=["internal_repository_id"]),
        ]

class Publisher(MusModel):
    lineage = models.ManyToManyField('Publisher', related_name="publ_children")
    as_funder = models.ManyToManyField('Funder', related_name="as_publisher")
    as_institution = models.ManyToManyField('Organization', related_name="as_publisher")

    openalex_id = models.URLField(max_length=20000,null=True)
    openalex_created_date = models.DateField(null=True)
    openalex_updated_date = models.DateTimeField(null=True)
    name = models.CharField()
    alternate_names = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    country_code = models.CharField(null=True)
    counts_by_year = models.JSONField(encoder=DjangoJSONEncoder)
    hierarchy_level = models.IntegerField()
    ror = models.CharField(null=True)
    wikidata = models.URLField(max_length=20000,null=True)
    image_url = models.URLField(max_length=20000,null=True)
    image_thumbnail_url = models.URLField(max_length=20000,null=True)
    sources_api_url = models.URLField(max_length=20000,null=True)
    impact_factor = models.FloatField(null=True)
    h_index = models.IntegerField(null=True)
    i10_index = models.IntegerField(null=True)
    works_count = models.IntegerField()
    internal_repository_id = models.CharField(null=True)
    def __str__(self):
        return f'{self.name}'

    class Meta:
        indexes = [
            models.Index(fields=["openalex_id"]),
            models.Index(fields=["ror"]),
            models.Index(fields=["wikidata"]),
            models.Index(fields=["image_url"]),
            models.Index(fields=["image_thumbnail_url"]),
            models.Index(fields=["internal_repository_id"]),
        ]
class Source(MusModel):
    class SourceType(models.TextChoices):
        JOURNAL = 'J'
        BOOK_SERIES = 'BS'
        REPOSITORY = 'R'
        EBOOK_PLATFORM = 'EP'
        CONFERENCE = 'C'
        METADATA = 'M'
        UNKNOWN = 'U'
    lineage = models.ManyToManyField('Publisher', related_name="children")
    topics = models.ManyToManyField('Topic', through='SourceTopic', related_name="sources")

    openalex_id = models.URLField(max_length=20000)
    openalex_created_date = models.DateField()
    openalex_updated_date = models.DateTimeField()

    is_in_doaj = models.BooleanField(default=False)
    is_oa = models.BooleanField(default=False)
    country_code = models.CharField(null=True)

    source_type = models.CharField(choices=SourceType, default=SourceType.UNKNOWN)
    title = models.CharField()
    alternate_titles = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    abbreviated_title = models.CharField(null=True)

    homepage_url = models.URLField(max_length=20000,null=True)
    host_org_name = models.CharField(null=True)

    issn_l = models.CharField(null=True)
    issn = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    wikidata = models.URLField(max_length=20000,null=True)
    fatcat = models.URLField(max_length=20000,null=True)
    mag = models.CharField(null=True)

    cited_by_count = models.IntegerField()
    counts_by_year = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    works_api_url = models.URLField(max_length=20000)
    works_count = models.IntegerField()
    impact_factor = models.FloatField()
    h_index = models.IntegerField()
    i10_index = models.IntegerField()

    apc_prices = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    apc_usd = models.IntegerField(null=True)
    internal_repository_id = models.CharField(null=True)
    def __str__(self):
        return f'{self.name}'

    class Meta:
        indexes = [
            models.Index(fields=["openalex_id"]),
            models.Index(fields=["issn_l"]),
            models.Index(fields=["issn"]),
            models.Index(fields=["wikidata"]),
            models.Index(fields=["source_type"]),
            models.Index(fields=["homepage_url"]),
            models.Index(fields=["is_in_doaj"]),
            models.Index(fields=["is_oa"]),
            models.Index(fields=["country_code"]),
            models.Index(fields=["internal_repository_id"]),
        ]
class Author(MusModel):
    affiliations = models.ManyToManyField(Organization,through='Affiliation', related_name="authors")
    topics = models.ManyToManyField(Topic, related_name="authors")

    name = models.CharField() # use primary openalex name as default
    alternative_names = models.JSONField(encoder=DjangoJSONEncoder, null=True) # e.g. display_name_alternatives from openalex or default_publishing_name from pure

    standardized_name = models.CharField(null=True) # TODO: determine how to standardize names
    first_names = models.CharField(null=True)
    last_name = models.CharField(null=True)
    middle_names = models.CharField(null=True)
    initials = models.CharField(null=True)
    prefixes = models.CharField(null=True)
    suffixes = models.CharField(null=True)

    orcid = models.URLField(max_length=20000,null=True)
    scopus = models.CharField(null=True)
    isni = models.CharField(null=True)

    # from openalex
    openalex_id = models.URLField(max_length=20000,null=True)
    openalex_created_date = models.DateField(null=True)
    openalex_updated_date = models.DateTimeField(null=True)
    works_api_url = models.URLField(max_length=20000,null=True)
    works_count = models.IntegerField(null=True)
    cited_by_count = models.IntegerField(null=True)
    counts_by_year = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    impact_factor = models.FloatField(null=True)
    h_index = models.IntegerField(null=True)
    i10_index = models.IntegerField(null=True)

    # from repo/ris/pure of institute
    pure_uuid = models.UUIDField(default=None, null=True, unique=True)
    pure_id = models.IntegerField(null=True)
    pure_last_modified = models.DateTimeField(null=True)
    author_links = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    avatar_url = models.URLField(max_length=20000,null=True)
    profile_url = models.URLField(max_length=20000,null=True)
    research_url = models.URLField(max_length=20000,null=True)
    email = models.CharField(null=True)
    internal_repository_id = models.CharField(null=True)

    # name-match info openalex <-> pure/institute data
    searched_name = models.CharField(null=True)
    found_name = models.CharField(null=True)
    match_similarity = models.FloatField(null=True)

    def __str__(self):
        groups = ''
        for a in self.affiliation_details.all():
            for g in a.groups.all():
                groups = groups + f'| {g}'
        if groups != '':
            return f'{self.name} {groups}'
        return f'{self.name}'

    class Meta:
        indexes = [
            models.Index(fields=["openalex_id"]),
            models.Index(fields=["pure_uuid"]),
            models.Index(fields=["pure_id"]),
            models.Index(fields=["orcid"]),
            models.Index(fields=["scopus"]),
            models.Index(fields=["isni"]),
            models.Index(fields=["email"]),
            models.Index(fields=["internal_repository_id"]),
        ]

class Affiliation(MusModel):
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="affiliation_details", db_index=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="affiliation_details", db_index=True)

    # for openalex affils:
    years = models.JSONField(encoder=DjangoJSONEncoder, null=True)

    # for pure/institute affils:
    position = models.CharField(blank=True, default='')
    groups = models.ManyToManyField(Group, related_name="affiliations")
    start_date = models.DateField(null=True)
    end_date = models.DateField(null=True)

    def __str__(self):
        return f'{self.organization} | {min(self.years)} - {max(self.years)} | {self.groups}'

    class Meta:
        indexes = [
            models.Index(fields=["author", "organization"]),
            models.Index(fields=["organization", "author"]),
            models.Index(fields=["years"]),
        ]

class DealData(MusModel):

    class DealType(models.TextChoices):
        FULL = 'FL', _("100% APC discount for UT authors")
        TWENTY = '20', _("20% APC discount for UT authors")
        FIFTEEN = '15', _("15% APC discount for UT authors")
        TEN = '10', _("10% APC discount for UT authors")
        PROBABLY_NONE = 'PR', _("Probably no APC costs")
        NONE = 'NO', _("No APC discount") # Also includes 'Full APC costs for UT authors (no discount)'
        UNKNOWN = 'UN', _("APC costs unknown")

    related_sources = models.ManyToManyField('Source', related_name="deals", db_index=True)

    dealtype = models.CharField(choices=DealType, default=DealType.UNKNOWN)
    issns = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    jb_url = models.URLField(max_length=20000)
    keywords = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    journal_title = models.CharField()
    publisher_name = models.CharField(default='', blank=True)
    # details for the openalex source item that was used to find this dealdata
    openalex_id = models.URLField(max_length=20000,unique=True)
    openalex_display_name = models.CharField(blank=True, default='')
    openalex_issn = models.JSONField(encoder=DjangoJSONEncoder, null=True, unique=True)
    openalex_issn_l = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    openalex_type = models.CharField(blank=True, default='')

    def __str__(self):
        return f'{self.dealtype}'

    class Meta:
        indexes = [
            models.Index(fields=["openalex_id"]),
            models.Index(fields=["openalex_display_name"]),
            models.Index(fields=["openalex_issn"]),
            models.Index(fields=["openalex_issn_l"]),
            models.Index(fields=["openalex_type"]),
            models.Index(fields=["journal_title"]),
            models.Index(fields=["publisher_name"]),
            models.Index(fields=["jb_url"]),
            models.Index(fields=["issns"]),
            models.Index(fields=["dealtype"]),
        ]

class Location(MusModel):
    # based on the subitem from OpenAlex Works
    source = models.ForeignKey('Source', on_delete=models.CASCADE, related_name="locations", db_index=True, null=True)
    source_type = models.CharField(choices=Source.SourceType, default=None, null=True)
    is_oa = models.BooleanField(default=False)
    landing_page_url = models.URLField(max_length=20000,null=True)
    pdf_url = models.URLField(max_length=20000,null=True)
    license = models.CharField(null=True)
    license_id = models.CharField(null=True)
    version = models.CharField(null=True)
    is_accepted = models.BooleanField(default=False)
    is_published = models.BooleanField(default=False)
    is_primary = models.BooleanField(default=False)
    is_best_oa = models.BooleanField(default=False)

    def __str__(self):
        if not self.landing_page_url:
            return f'{self.pdf_url}'
        return f'{self.landing_page_url}'

    class Meta:
        indexes = [
            models.Index(fields=["source", "source_type"]),
            models.Index(fields=["landing_page_url"]),
            models.Index(fields=["pdf_url"]),
            models.Index(fields=["license"]),
            models.Index(fields=["license_id"]),
            models.Index(fields=["is_best_oa"]),
            models.Index(fields=["is_accepted"]),
            models.Index(fields=["is_published"]),
            models.Index(fields=["is_primary"]),
        ]

class Abstract(MusModel):
    text = models.TextField()

    def __str__(self):
        return f'{self.text}'

class Work(MusModel):
    class OAStatus(models.TextChoices):
        GOLD = 'gold'
        BRONZE = 'bronze'
        GREEN = 'green'
        HYBRID = 'hybrid'
        CLOSED = 'closed'
        NOT_SET = 'not_set'
    class MUSTypes(models.TextChoices):
        BOOK = 'book'
        CONFERENCE_PROCEEDING = 'conference_proceeding'
        JOURNAL_ARTICLE = 'journal_article'
        DISSERTATION = 'dissertation'
        REPORT = 'report'
        OTHER = 'other'
        NOT_SET = 'not_set'
        # TODO:
        # add more types and map to pure, openalex, crossref ... types
        # store this mapping somewhere to be viewed by users in the UI as well

    authors = models.ManyToManyField(Author, through='Authorship', related_name="works")
    topics = models.ManyToManyField(Topic, related_name="works")
    abstract = models.OneToOneField(Abstract, on_delete=models.CASCADE, null=True, default=None)
    locations = models.ManyToManyField(Location, related_name="works")
    primary_topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="primary_works", db_index=True, null=True)

    # for journal: go through locations, get sources, if sourcetype == journal, add here
    journal = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="journals", db_index=True, null=True)

    openalex_id = models.URLField(max_length=20000,null=True)
    openalex_created_date = models.DateField(null=True)
    openalex_updated_date = models.DateTimeField(null=True)
    ngrams_url = models.URLField(max_length=20000,null=True)
    cited_by_api_url = models.URLField(max_length=20000,null=True)
    cited_by_count = models.IntegerField(null=True)
    cited_by_percentile_year = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    referenced_works_count = models.IntegerField(null=True)

    doi = models.CharField(null=True)
    title = models.CharField()
    publication_year = models.IntegerField()
    publication_date = models.DateField()
    pmid = models.CharField(null=True)
    pmcid = models.CharField(null=True)
    isbn = models.CharField(null=True)
    mag = models.CharField(null=True)
    language = models.CharField(null=True)
    mesh_terms = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    type_crossref = models.CharField(null=True)

    volume = models.CharField(null=True)
    issue = models.CharField(null=True)
    first_page = models.CharField(null=True)
    last_page = models.CharField(null=True)
    pages = models.CharField(null=True)
    article_number = models.CharField(null=True)

    locations_count = models.IntegerField(null=True)
    is_oa = models.BooleanField(default=False)
    oa_status = models.CharField(choices=OAStatus, default=OAStatus.NOT_SET)
    oa_url = models.URLField(max_length=20000,null=True)
    is_also_green = models.BooleanField(default=False) #'any repository has fulltext' field
    itemtype = models.CharField(choices=MUSTypes, default=MUSTypes.NOT_SET)
    apc_listed = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    apc_paid = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    has_fulltext = models.BooleanField(default=False)
    is_paratext = models.BooleanField(default=False)
    is_retracted = models.BooleanField(default=False)
    indexed_in = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    keywords = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    sdgs = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    versions = models.JSONField(encoder=DjangoJSONEncoder, null=True)

    # is item found in .... ? Then add the data right here
    # decide later which fields from these jsons to properly store
    found_in_institute_repo = models.BooleanField(default=False)
    repo_data = models.OneToOneField('RepositoryData', on_delete=models.CASCADE, null=True)
    repo_keywords = models.JSONField(encoder=DjangoJSONEncoder, null=True)
    internal_repository_id = models.CharField(null=True)
    pure_id = models.IntegerField(null=True)

    found_in_openaire = models.BooleanField(default=False)
    openaire_data = models.OneToOneField('OpenAireData', on_delete=models.CASCADE, null=True)

    found_in_datacite = models.BooleanField(default=False)
    datacite_data = models.OneToOneField('DataCiteData', on_delete=models.CASCADE, null=True)

    found_in_crossref = models.BooleanField(default=False)
    crossref_data = models.OneToOneField('CrossrefData', on_delete=models.CASCADE, null=True)

    def __str__(self):
        return f'{self.title} - {self.doi}'

    class Meta:
        indexes = [
            models.Index(fields=["openalex_id"]),
            models.Index(fields=["doi"]),
            models.Index(fields=["publication_date"]),
            models.Index(fields=["publication_year"]),
            models.Index(fields=["oa_status"]),
            models.Index(fields=["pmid"]),
            models.Index(fields=["pmcid"]),
            models.Index(fields=["isbn"]),
            models.Index(fields=["mag"]),
            models.Index(fields=["is_also_green"]),
            models.Index(fields=["is_oa"]),
            models.Index(fields=["itemtype"]),
            models.Index(fields=["type_crossref"]),
            models.Index(fields=["internal_repository_id"]),
        ]


class RepositoryData(MusModel):
    data = models.JSONField(encoder=DjangoJSONEncoder)
    internal_repository_id = models.CharField(null=True)

class OpenAireData(MusModel):
    data = models.JSONField(encoder=DjangoJSONEncoder)

class CrossrefData(MusModel):
    data = models.JSONField(encoder=DjangoJSONEncoder)

class DataCiteData(MusModel):
    data = models.JSONField(encoder=DjangoJSONEncoder)

class Authorship(MusModel):
    class PositionTypes(models.TextChoices):
        FIRST = 'first'
        MIDDLE = 'middle'
        LAST = 'last'
        UNKNOWN = '-'
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="authorships")
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="authorships")
    position = models.CharField(choices=PositionTypes, default=PositionTypes.UNKNOWN)
    is_corresponding = models.BooleanField(default=False)
    affiliations = models.ManyToManyField(Organization, related_name="authorships")

    def __str__(self):
        if self.is_corresponding:
            return f'{self.author} - {self.position} (corresponding)'
        else:
            return f'{self.author} - {self.position}'

    class Meta:
        indexes = [
            models.Index(fields=["author", "work"]),
            models.Index(fields=["work", "author"]),
            models.Index(name='cor_index', fields=["is_corresponding"], condition=Q(is_corresponding=True)),
        ]

class Grant(MusModel):
    funder = models.ForeignKey('Funder', on_delete=models.CASCADE, related_name="grants", null=True)
    award_id = models.CharField(null=True)
    funder_name = models.CharField(null=True)
    work = models.ForeignKey('Work', related_name="grants", on_delete=models.CASCADE)
    internal_repository_id = models.CharField(null=True)

    def __str__(self):
        return f'{self.funder_name} - {self.award_id}'

    class Meta:
        indexes = [
            models.Index(fields=["award_id"]),
            models.Index(fields=["funder_name"]),
            models.Index(fields=["work"]),
            models.Index(fields=["funder"]),
            models.Index(fields=["internal_repository_id"]),
        ]