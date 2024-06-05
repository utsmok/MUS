from datetime import datetime

FACULTYNAMES = [
    "EEMCS",
    "BMS",
    "ET",
    "ITC",
    "TNW",
]
FACULTYNAMES.extend([item.lower() for item in FACULTYNAMES])

FACULTYABBRMAPPING = {
    'EEMCS': 'Faculty of Electrical Engineering, Mathematics and Computer Science',
    'BMS': 'Faculty of Faculty of Behavioural, Management and Social Sciences',
    'ET': 'Faculty of Engineering Technology',
    'ITC': 'Faculty of Geo-Information Science and Earth Observation',
    'TNW': 'Faculty of Science and Technology',
}
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

UTRESEARCHGROUPS_HIERARCHY = {
    'ITC': {},
    'TNW': {
        'Applied Nanophotonics (AN)': [
            'Biomedical Photonic Imaging (BPI)',
            'Complex Photonic Systems (COPS)',
            'Laser Physics and Non-linear Optics (LPNO)',
            'Optical Sciences (OS)',
            'Integrated Optical Systems (IOS)',
            'Nanobiophysics (NBP)',
            'Adaptive Quantum Optics (AQO)',
        ],
        'Bioengineering Technologies (BT)': [
            'Advanced Organ Bioengineering and Therapeutics (AOT)',
            'Applied Stem Cell Technologies (AST)',
            'Bioelectronics (BE)',
            'Biomolecular Nanotechnology (BNT)',
            'Developmental Bioengineering (DBE)',
            'Molecular Nanofabrication (MNF)',
        ],
        'Energy, Materials and Systems (EMS)': [

        ],
        'Imaging and Diagnostics (ID)': [
            'Biomedical Photonic Imaging (BMPI)',
            'Magnetic Detection & Imaging (MDI)',
            'Medical Cell Biophysics (MCBP)',
            'Multi-Modality Medical Imaging (M3I)',
            'Physics of Fluids (POF)',
        ],
        'Membrane Science and Technology (MST)': [
            'Membrane Surface Science (MSUS)',
            'Soft matter, Fluidics and Interfaces (SFI)',
            'Films in Fluids (FIF)',
            {'Membrane Process Technology (MPT)': [
                'Membranes for Harsh Conditions (MHC)',
                'Membrane Processes for Food (MPF)',
                'Membrane Technology and Engineering for Water Treatment (MTEWT)',
            ]},
        ],
        'Nano Electronic Materials (NEM)': [
            'Inorganic Materials Science (IMS)',
            'Interfaces and Correlated Electron Systems (ICE)',
            'Quantum Transport in Matter (QTM)',
            'Physics of Interfaces and Nanomaterials (PIN)',
            'Computational Chemical Physics (CCP)',
            'XUV Optics (XUV)',
        ],
        'Department of molecules and Materials (DMM)': [
            'Biomolecular Nanotechnology (BNT)',
            'Molecular Nanofabrication (MNF)',
            'Sustainable Polymer Chemistry (SPC)',
            'Hybrid Materials for Opto-Electronic (HMOE)',
        ],
        'Physics Of Fluids (POF)': [
            'Physics Of Fluids (POF)',
        ],
        'Process and Catalysis Engineering (PCE)': [
            'Catalytic Processes and Materials (CPM)',
            'Sustainable Process Technology (SPT)',
            'Mesoscale Chemical Systems (MCS)',
            'Photocatalytic Syntheses (PCS)',
        ],
        'Soft Matter (SM)': [
            'Bioelectronics (BE)',
            'Physics of Complex Fluids (PCF)',
            'Nanobiophysics (NBP)',
        ],
        'Translational Physiology (TP)': [
            'Clinical Neurophysiology (CNPH)',
            'Cardio-Respiratory Physiology (CRPH)',
        ]
    },
    'EEMCS': {
        'Computer Science (CS)': [
            'Computer Architecture for Embedded Systems (CAES)',
            'Design and Analysis of Communication Systems (DACS)',
            'Data Management & Biometrics (DMB)',
            'Formal Methods and Tools (FMT)',
            'Human Media Interaction (HMI)',
            'Pervasive Systems (PS)',
            'Semantics, Cybersecurity and Services (SCS)',
        ],
        'Electrical engineering (EE)': [
            'Applied Microfluidics for BioEngineering Research  (AMBER)',
            'Biomedical Signals and Systems (BSS)',
            'The BIOS lab-on-a-chip group (BIOS)',
            'Integrated Circuit Design (ICD)',
            'Nano Electronics (NE)',
            'Robotics and Mechatronics (RAM)',
            'Integrated Devices and Systems (IDS)',
            'Power Electronic & Electromagnetic Compatibility (PE)',
            'Radio Systems (RS)',
            'Computer Architecture for Embedded Systems (CAES)',
            'Design and Analysis of Communication Systems (DACS)',
        ],
        'Applied mathematics (DAMUT)': [{
            'Mathematics of Operations Research (MOR)': [
                'Discrete Mathematics and Mathematical Programming (DMMP)',
                'Stochastic Operations Research (SOR)',
                'Statistics (STAT)',
            ],
            'Systems, Analysis and Computational Science (SACS)': [
                'Mathematics of Computational Science (MACS)',
                'Mathematics of Imaging & AI (MIA)',
                'Mathematics of Systems Theory (MAST)',
                'Mathematics of Multiscale Modeling and Simulation (3MS)',
            ],
            'Mathematics of Data Science (MDS)': [
                'Mathematics of Imaging & AI (MIA)',
                'Statistics (STAT)',
            ]
        }]
    },
    'BMS': {
        'Department of technology, policy and society (TPS)': [
            'Health Technology & Services Research (HTSR)',
            'Governance and Technology for Sustainability (CSTM)',
            'Philosophy of Science & Technology (PHIL)',
            'Knowledge, Transformation & Society (KITES)',
        ],
        'Department of Technology, Human and Instititional behaviour (HIB)': [
            'Psychology, Health & Technology (PHT)',
            'Psychology of Conflict, Risk and Safety (PCRS)',
            'Public Administration (PA)',
            'Communication Science (CS)',
        ],
        'Department of Learning, Data analytics and Technology (LDT)': [
            'ELAN Teacher Development',
            'Instructional Technology (IST)',
            'Professional Learning & Technology (PLT)',
            'Cognition, Data and Education (CODE)',
        ],
        'Department of High-tech Business and Entrepreneurship (HBE)': [
            'Industrial Engineering and Business Information Systems (IEBIS)',
            'Entrepeneurship, Technology and Management (ETM)',
            'Financial Engineering (FE)',
        ],
    },
    'ET': {
        'Biomechanical Engineering (BE)': [
            'Biomechatronics and Rehabilitation Technology (BRT)',
            'Biomedical Device Design and Production (BDDP)',
            'Engineering Organ Support Technologies (EOST)',
            'Neuromechanical Engineering (NE)',
            'Surgical Robotics (SR)',
        ],
        'Civil Engineering and Management (CEM)': [
            'Integrated Project Delivery (IPD)',
            'Multidisciplinary Water Management (MWM)',
            'Water Engineering and Management, in particular Watersystems (WS)',
            'Coastal Systems and Nature Based Engineering (CSNBE)',
            'Market Dynamics (MD)',
            'Soil Micro Mechanics (SMM)',
            'Transport Engineering and Management (TEM)',
            'Transport Planning (TP)',
        ],
        'Design, Production and Management (DPM)': [
            'Asset Management & Maintenance Engineering (AMME)',
            'Advanced Manufacturing, Sustainable products & Energy systems (AMSPES)',
            'Human Centred Design (HCD)',
            'Interaction Design (ID)',
            'Information driven Product Development & Engineering (IdPDE)',
            'Manufacturing Systems (MS)',
            'Product-Market Relations (PMR)',
            'Systems Engineering & Multidisciplinary Design (SEMD)',
        ],
        'Mechanics of Solids, Surfaces and Systems (MS3)': [
            'Applied Mechanics and Data Analysis (AMDA)',
            'Computational Design of Structural Materials (CDSM)',
            'Dynamics Based Maintenance (DBM)',
            'Elastomer Technology and Engineering (ETE)',
            'Functional Surface Engineering & Design (FSED)',
            'Laser Processing (LP)',
            'Nonlinear Solid Mechanics (NSM)',
            'Production Technology (PT)',
            'Precision Engineering (PE)',
            'Surface technology and Tribology (STT)',
            'Tribology Based Maintenance (TBM)',
        ],
        'Thermal and Fluid Engineering (TFE)': [
            'Engineering Fluid Dynamics (EFD)',
            'Multi-Scale Mechanics (MSM)',
            'Thermal Engineering (TE)',
        ],
    }
}
UTRESEARCHGROUPS_FLAT: dict[str, str] = {
    'Advanced Membranes for Aqueous Applications (AMAA)': 'TNW',
    'Adaptive Quantum Optics (AQO)': 'TNW',
    'Analog signal processing devices and systems (ASPDS)': 'TNW',
    'Applied Stem Cell Technologies (AST)': 'TNW',
    'Bioelectric signaling and engineering (BIOEE)': 'TNW',
    'Bioelectronics (BE)': 'TNW',
    'Advanced Organ bioengineering and Therapeutics (AOT) ': 'TNW',
    'Biomedical Photonic Imaging (BMPI)': 'TNW',
    'Biomolecular Nanotechnology (BNT)': 'TNW',
    'Cardiovascular and Respiratory Physiology (CRPH)': 'TNW',
    'Catalytic Processes and Materials (CPM)': 'TNW',
    'Clinical Neurophysiology (CNPH)': 'TNW',
    'Computational Chemical Physics (CCP)': 'TNW',
    'Complex Photonic Systems (COPS)': 'TNW',
    'Developmental BioEngineering (DBE)': 'TNW',
    'Energy, Materials and Systems (EMS)': 'TNW',
    'Films in Fluids (FIF)': 'TNW',
    'Hybrid Materials for Opto-Electronic (HMOE)': 'TNW',
    'Industrial Focus Group XUV Optics (XUV)': 'TNW',
    'Inorganic Membranes (IM)': 'TNW',
    'Inorganic Materials Science (IMS)': 'TNW',
    'Interfaces and Correlated Electron Systems (ICE)': 'TNW',
    'Integrated Optical Systems (IOS)': 'TNW',
    'Laser Physics and Non-linear Optics (LPNO)': 'TNW',
    'Magnetic Detection & Imaging (MD&I)': 'TNW',
    'Materials Science and Technology of Polymers (MTP)': 'TNW',
    'Medical Cell BioPhysics (MCBP)': 'TNW',
    'Membrane Process Technology (MPT)': 'TNW',
    'Membrane Surface Science (MSUS)': 'TNW',
    'Mesoscale Chemical Systems (MCS)': 'TNW',
    'Molecular Nanofabrication (MNF)': 'TNW',
    'Multi-Modality Medical Imaging (M3I)': 'TNW',
    'Nanobiophysics (NBP)': 'TNW',
    'Nonlinear Nanophotonics Group (NLNP)': 'TNW',
    'Optical Sciences (OS)': 'TNW',
    'Photo-catalytic Synthesis (PCS)': 'TNW',
    'Physics of Complex Fluids (PCF)': 'TNW',
    'Physics of Fluids (POF)': 'TNW',
    'Physics of Interfaces and Nanomaterials (PIN)': 'TNW',
    'Polymer Chemistry and Biomaterials (PBM)': 'TNW',
    'Quantum Transport in Matter (QTM)': 'TNW',
    'Soft matter, Fluidics and Interfaces (SFI)': 'TNW',
    'Sustainable Polymer Chemistry (SPC)': 'TNW',
    'Sustainable Process Technology (SPT)': 'TNW',
}


def update_flat_groups():
    flatgroups = {}
    global UTRESEARCHGROUPS_FLAT
    for fac, grouplist in UTRESEARCHGROUPS_HIERARCHY.items():
        if fac in ['ITC']:
            continue
        else:
            for dept, groups in grouplist.items():
                if isinstance(groups, list):
                    for group in groups:
                        if isinstance(group, str):
                            if group not in flatgroups.keys():
                                flatgroups[group] = fac
                            elif flatgroups[group] != fac:
                                print(f'group with 2 faculties? curfac: {fac}. fac in list: {flatgroups[group]}')
                        elif isinstance(group, dict):
                            for subdept, subgroups in group.items():
                                if subdept not in flatgroups.keys():
                                    flatgroups[subdept] = fac
                                for subgroup in subgroups:
                                    if subgroup not in flatgroups.keys():
                                        flatgroups[subgroup] = fac
    UTRESEARCHGROUPS_FLAT = UTRESEARCHGROUPS_FLAT | flatgroups
    tempgroup = UTRESEARCHGROUPS_FLAT.copy()
    for k, v in tempgroup.items():
        UTRESEARCHGROUPS_FLAT[k.split('(')[0].strip().lower()] = v


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
CSV_EEMCS_KEYS = [
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
    return f''' <?xml version="1.0" encoding="UTF-8"?> <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/" 
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/ 
    http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd https://www.openaire.eu/cerif-profile/1.2/ 
    https://www.openaire.eu/schema/cris/current/openaire-cerif-profile.xsd"> <responseDate>{time}</responseDate>
        <request metadataPrefix="oai_cerif_openaire" verb="ListRecords" set="openaire_cris_publications"></request>
        <ListRecords>
    '''


def get_cerif_record_header(id=None):
    return f'''
        <record>
            <header>
                <identifier>{id}</identifier>
                <datestamp></datestamp>
                <setSpec></setSpec>
            </header>
            <metadata>
    '''


CERIF_CLOSER = '''
    </ListRecords>
</OAI-PMH>
'''

RECORD_CLOSER = '''
            </metadata>
        </record>
'''

update_flat_groups()
