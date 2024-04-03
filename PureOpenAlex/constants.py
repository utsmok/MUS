from datetime import datetime
FACULTYNAMES = [
    "EEMCS",
    "BMS",
    "ET",
    "ITC",
    "TNW",
    ]
FACULTYNAMES.extend([item.lower() for item in FACULTYNAMES])

TCSGROUPS = [
    "Design and Analysis of Communication Systems",
    "Formal Methods and Tools",
    "Computer Architecture Design and Test for Embedded Systems",
    "Pervasive Systems",
    "Datamanagement & Biometrics",
    "Semantics",
    "Human Media Interaction",
]
TCSGROUPSABBR = [
    "DACS",
    "FMT",
    "CAES",
    "PS",
    "DMB",
    "SCS",
    "HMI",
]

EEGROUPS = [
    'AMBER',
    'Biomedical Signals and Systems',
    'The BIOS lab-on-a-chip group',
    'Integrated Circuit Design',
    'Nano Electronics',
    'Robotics and Mechatronics',
    'Integrated Devices and Systems ',
    'Power Electronic & Electromagnetic Compatibility',
    'Radio Systems',
    'Computer Architecture for Embedded Systems',
    'Design and Analysis of Communication Systems',
    'Datamanagement & Biometrics',
]
EEGROUPSABBR = [
    'AMBER',
    'BSS',
    'BIOS',
    'ICD',
    'NE',
    'RAM',
    'PE',
    'RS',
    'CAES',
    'DACS',
    'DMB',
]

LICENSESOA = [
    "cc-by-sa",
    "cc-by-nc-sa",
    "publisher-specific-oa",
    "cc-by-nc-nd",
    "cc-by-nc",
    "cc0",
    "cc-by",
    "public-domain",
    "cc-by-nd",
    "pd",
]
OTHERLICENSES = [
    "publisher-specific,authormanuscript",
    "unspecified-oa",
    "implied-oa",
    "elsevier-specific",
]

TAGLIST = ["UT-Hybrid-D", "UT-Gold-D", "NLA", "N/A OA procedure"]
for year in range(2000, 2031):
    TAGLIST.append(f"{year} OA procedure")

TWENTENAMES = [
    "university of twente",
    "University of Twente",
    "University of Twente ",
    "University of Twente / Apollo Tyres Global R&D",
    "University of Twente Faculty of Engineering Technology",
    "University of Twente, Faculty of Geo-Information Science and Earth Observation",
    "University of Twente Faculty of Geo-Information Science and Earth Observation ITC",
    "University of Twente, Faculty of Geo-Information Science and Earth Observation (ITC)",
    "University of Twente - Faculty of ITC",
    "University of Twente, faculty of Science and Technology",
    "University of Twente,ITC",
    "University of Twenty, Netherlands",
]

CSV_EXPORT_KEYS = [
    'title',
    'doi',
    'year',
    'itemtype',
    'isbn',
    'topics',
    'Authorinfo ->',
    'ut_authors',
    'ut_groups',
    'is_eemcs?',
    'is_ee?',
    'is_tcs?',
    'ut_corresponding_author',
    'all_authors',
    'Openaccessinfo ->',
    'is_openaccess',
    'openaccess_type',
    'found_as_green',
    'present_in_pure',
    'license',
    'URLs ->',
    'primary_link',
    'pdf_link_primary',
    'best_oa_link',
    'pdf_link_best_oa',
    'other_oa_links',
    'openalex_url',
    'pure_page_link',
    'pure_file_link',
    'scopus_link',
    'Journalinfo ->',
    'journal',
    'journal_issn',
    'journal_e_issn',
    'journal_publisher',
    'volume',
    'issue',
    'pages',
    'pagescount',
    'MUS links ->',
    'mus_paper_details',
    'mus_api_url_paper',
    'mus_api_url_pure_entry',
    'mus_api_url_pure_report_details'
]

def get_cerif_header():
    time = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
    return f'''
    <?xml version="1.0" encoding="UTF-8"?>
        <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/ http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd https://www.openaire.eu/cerif-profile/1.2/ https://www.openaire.eu/schema/cris/current/openaire-cerif-profile.xsd">
        <responseDate>{time}</responseDate>
        <request metadataPrefix="oai_cerif_openaire" verb="ListRecords" set="openaire_cris_publications"></request>
        <ListRecords>
    '''

CERIF_CLOSER = '''
    </ListRecords>
</OAI-PMH>
'''
RECORD_HEADER = '''
        <record>
            <header>
                <identifier></identifier>
                <datestamp></datestamp>
                <setSpec></setSpec>
            </header>
            <metadata>
'''
RECORD_CLOSER = '''
            </metadata>
        </record>
'''
