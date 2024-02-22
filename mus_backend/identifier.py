'''
The IdentifierFactory is used to create Identifier objects.
When a request to add a new item is received, a new Identifier should be created by calling factory.create([ids]).
The identifiers will be classified + formatted using regex, and if possible validated.

Returns a subclass of Identifier for each id request -- for details see IdentifierFactory.

'''
import re
from abc import ABC
'''
=========================
        Exceptions
=========================
'''
class IdentifierMatchError(Exception):
    id: str
    def __init__(self, id):
        self.id = id
        print(f"Unable to match identifier < {id} > to any known format.")

class IdentifierValidationError(Exception):
    id: str
    id_type: str
    def __init__(self, id, id_type):
        self.id = id
        self.id_type = id_type
        print(f"Identifier < {id} > of type < {id_type} > failed validation on init.")

'''
===================================
        Identifier Base Classes
===================================
'''
class Identifier:
    '''
    Base class for all identifiers.
    Holds the main parameters:
        id: str -- the canonical identifier
        bare: str -- the bare identifier, e.g. a DOI without the URL prefix
        request_id: str -- the initial request string used to build this identifier
    '''
    id: str
    bare: str
    request_id: str 
    def __init__(self, id, bare, request_id):
        self.id = id
        self.request_id = request_id
        self.bare = bare

class AbstractIdentifier(Identifier, ABC):
    '''
    Abstract interface for all actual identifier classes.
    Implements the initialisation process and provides the repr/str functions.
    Implements the validation process but the implementation of is_valid() is left to subclasses.
    During initialisation, the bare and full id's are split and stored.
    '''
    def __init__(self, id, request_id):
        PREPENDS = {
        'DOI':'https://www.doi.org/',
        'OpenAlexId':'https://openalex.org/',
        'ROR':'https://ror.org/',
        'ORCID':'https://orcid.org/',
        'ArxivId':'arXiv:',
        'PureId':'https://research.utwente.nl/en/publications/',
        'SemanticScholarId':'https://api.semanticscholar.org/CorpusID:',
        'ISSN':'',
        }
        prepend = PREPENDS[type(self).__name__]
        if not id.startswith(prepend) and \
            ':' not in id and \
            not id.startswith('https://') and \
            not id.startswith('http://'):
            bare=id
            id=prepend+id
        elif id.startswith(prepend):
            bare=id.strip(prepend)
            id=id
        else:
            splits=id.strip('/').split('/')
            bare="/".join(splits[3:]) if len(splits) > 3 else splits[3:]
            id=prepend+bare

        super().__init__(id, bare, request_id)
        if not self.is_valid():
            raise IdentifierValidationError(self.id, type(self).__name__)

    def __str__(self):
        return self.id

    def __repr__(self):
        return f"{self.bare} // {self.id} [{type(self).__name__}] | built from {self.request_id} "

    def is_valid(self):
        return True
'''
============================================
        Subclasses - Concrete Identifiers
============================================
'''
class DOI(AbstractIdentifier):
    ...
class OpenAlexId(AbstractIdentifier):
    ...
        
class ORCID(AbstractIdentifier):
    def is_valid(self):
        '''
        orcid should be given as 16 digits in str format
        returns True if valid ORCID, else False
        '''
        bare=self.bare.replace('-','')
        if len(bare) != 16:
            return False
        basedigits=bare[0:-1]
        total = 0
        for i in basedigits:
            total = (total + int(i)) * 2
        
        remainder = total % 11
        result = (12 - remainder) % 11
        result = 'X' if result == 10 else str(result)

        if result == bare[-1]:
            return True
        else:
            return False
class ROR(AbstractIdentifier):
    ...
class PureId(AbstractIdentifier):
    ...
class ArxivId(AbstractIdentifier):
    ...
class SemanticScholarId(AbstractIdentifier):
    ...
class ISSN(AbstractIdentifier):
    def is_valid(self):
        '''
        issn should be given as 8 digits in str format
        returns True if valid ISSN, else False
        '''
        id=self.bare.replace('-','')
        if len(id) != 8:
            return False
        basedigits=id[0:-1]
        total = 0
        j=8
        for i in basedigits:
            total=total+int(i)*j
            j=j-1         
        remainder = total % 11
        result = (11 - remainder) % 11
        result = 'X' if result == 10 else str(result)

        if result == id[-1]:
            return True
        else:
            return False

class IdentifierFactory:
    '''
    Helper class for creating identifiers from input string(s).
    Uses regular expressions to match the input string to a known format.

    Returns an Identifier subclass object for each item in the list 
    -- or throws an IdentifierMatchError if no match is found.

    Ex. usage:
    id_maker=IdentifierFactory()
    id_maker.create('https://orcid.org/0000-0002-1825-0097')
    id_maker.create(['https://orcid.org/0000-0002-1825-0097', 'https://doi.org/10.1109/ICCV.2019.00089'])
    '''


    def clean_id(self, id):
        id=str(id).strip('/')
        try:
            if id.startswith('http'):
                splits = id.split('/')
                return "/".join(splits[3:]) if len(splits) > 3 else splits[3:]
        except Exception as e:
            print(e," while cleaning id: ", id)
        return id
        
    def create(self, id):
        if isinstance(id, Identifier):
            return id
        if isinstance(id, list):
            return [self.id_matcher(i) for i in id]
        else:
            return [self.id_matcher(id)]
        
    def id_matcher(self, id):
        REGEX = {
        'DOI':          re.compile("(?i)10.\d{4,9}/[-._;()/:A-Z0-9]+"),
        'ROR':          re.compile('^0[a-z|0-9]{6}[0-9]{2}$'),
        'OpenAlex':     re.compile('[WAISCF][1-9]\d{3,9}'),
        'Pure':         re.compile('^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
        'ORCID':        re.compile('^(\d){4}-(\d){4}-(\d){4}-(\d){3}[0-9X]$'),
        'S2PID':        re.compile('[0-9a-fA-F]{40}'),
        'ISSN':         re.compile('^[0-9]{4}-[0-9]{3}[0-9X]$'),
        'arXiv':        re.compile("(\d{4}.\d{4,5}|[a-z\-]+(\.[A-Z]{2})?\/\d{7})(v\d+)?"),
  #     'ISBN-10':      re.compile("([0-57]-(\d-\d{7}|\d\d-\d{6}|\d{3}-\d{5}|\d{4}-\d{4}|\d{5}-\d{3}|\d{6}-\d\d|\d{7}-\d)|(65|8\d|9[0-4])-(\d-\d{6}|\d\d-\d{5}|\d{3}-\d{4}|\d{4}-\d{3}|\d{5}-\d\d|\d{6}-\d)|(6[0-4]|9[5-8])\d-(\d-\d{5}|\d\d-\d{4}|\d{3}-\d{3}|\d{4}-\d\d|\d{5}-\d)|99[0-8]\d-(\d-\d{4}|\d\d-\d{3}|\d{3}-\d\d|\d{4}-\d)|999\d\d-(\d-\d{3}|\d\d-\d\d|\d{3}-\d))-[\dX]"),
  #     'ISBN-13':      re.compile("97(8-([0-57]-(\d-\d{7}|\d\d-\d{6}|\d{3}-\d{5}|\d{4}-\d{4}|\d{5}-\d{3}|\d{6}-\d\d|\d{7}-\d)|(65|8\d|9[0-4])-(\d-\d{6}|\d\d-\d{5}|\d{3}-\d{4}|\d{4}-\d{3}|\d{5}-\d\d|\d{6}-\d)|(6[0-4]|9[5-8])\d-(\d-\d{5}|\d\d-\d{4}|\d{3}-\d{3}|\d{4}-\d\d|\d{5}-\d)|99[0-8]\d-(\d-\d{4}|\d\d-\d{3}|\d{3}-\d\d|\d{4}-\d)|999\d\d-(\d-\d{3}|\d\d-\d\d|\d{3}-\d))|9-(8-(\d-\d{7}|\d\d-\d{6}|\d{3}-\d{5}|\d{4}-\d{4}|\d{5}-\d{3}|\d{6}-\d\d|\d{7}-\d)|(1[0-2]|6\d)-(\d-\d{6}|\d\d-\d{5}|\d{3}-\d{4}|\d{4}-\d{3}|\d{5}-\d\d|\d{6}-\d)))-\d|"),
  #     'PMID':         re.compile('([1-3]\d{7}|[1-9]\d{0,6})'),
        }

        IDENTIFIERS = {
        'ORCID':        ORCID,
        'S2PID':        SemanticScholarId,
        'arXiv':        ArxivId,
        'Pure':         PureId,
        'ROR':          ROR,
        'OpenAlex':     OpenAlexId,
        'DOI':          DOI,
        'ISSN':         ISSN,  
        }
        PREPENDS = {
        'DOI':['https://www.doi.org/','https://doi.org/','http://doi.org/', 'https://dx.doi.org/'],
        'OpenAlexId':['https://openalex.org/', 'https://api.openalex.org/'],
        'ROR':'https://ror.org/',
        'ORCID':'https://orcid.org/',
        'ArxivId':'arXiv:',
        'PureId':'https://research.utwente.nl/en/publications/',
        'SemanticScholarId':'https://api.semanticscholar.org/CorpusID:',
        }

        request_id=id
        id_type=None
        for name, prepend in PREPENDS.items():
            if isinstance(prepend, list):
                for p in prepend:
                    if id.startswith(p):
                        id_type=name
                        break
            elif id.startswith(prepend):
                id_type=name
                break
        if not id_type:
            id = self.clean_id(id)
            for id_name,regex in REGEX.items():
                if re.search(regex, id):
                    id_type=id_name
                    break

        if id_type in IDENTIFIERS:
            return IDENTIFIERS[id_type](id, request_id)
        raise IdentifierMatchError(request_id)
