import os

from dotenv import load_dotenv

# -------------------------------------------------------
#
#   load in settings / urls / data from secrets.env
#
# -------------------------------------------------------

# change to dynamic path to be set in the wizard
dotenv_path = 'secrets.env'
load_dotenv(dotenv_path)

# API keys / ID's / e-mails / tokens
ORCID_CLIENT_ID = str(os.getenv('ORCID_CLIENT_ID'))
ORCID_CLIENT_SECRET = str(os.getenv('ORCID_CLIENT_SECRET'))
ORCID_ACCESS_TOKEN = os.getenv('ORCID_ACCESS_TOKEN')
APIEMAIL = str(os.getenv('APIEMAIL'))
OPENAIRETOKEN = str(os.getenv('OPENAIRETOKEN'))

# IDs, names, groups, URLS for current main institute/uni/...

INSTITUTE_NAME = str(os.getenv('INSTITUTE_NAME'))
INSTITUTE_ALT_NAME = str(os.getenv('INSTITUTE_ALT_NAME'))

if ';' in INSTITUTE_ALT_NAME:  # if there are multiple names separated by semicolons, split them up
    INSTITUTE_ALT_NAME = INSTITUTE_ALT_NAME.split(';')
    INSTITUTE_ALT_NAME = [item.strip() for item in INSTITUTE_ALT_NAME]

'''groups = str(os.getenv('INSTITUTE_GROUPS'))
if groups:
    INSTITUTE_GROUPS = groups.split(',')
else:
    INSTITUTE_GROUPS = []
'''

ROR = str(os.getenv('ROR'))
OPENALEX_INSTITUTE_ID = str(os.getenv('OPENALEX_INSTITUTE_ID'))

JOURNAL_BROWSER_URL = str(os.getenv('JOURNAL_BROWSER_URL'))
OAI_PMH_URL = str(os.getenv('OAI_PMH_URL'))

# System settings
MONGOURL = str(os.getenv(
    'MONGOURL'))  # mongodb connection string; separated from main django settings so this whole module can
# eventually be used as a separate service

# -------------------------------------------------------
#
#   Actual constants
#
# -------------------------------------------------------

# license types in OpenAlex Works that denote open access or not:
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

# -------------------------------------------------------
#
#    UT specific data -- temporary for now.
#    todo: somehow build these lists dynamically for the chosen institute
#    plus let the user add their own institute data in the wizard
#
# -------------------------------------------------------

# tags used by UT metadata team to classify open access procedures
# these will be found in the OAI-PMH response
TAGLIST = ["UT-Hybrid-D", "UT-Gold-D", "NLA", "N/A OA procedure"]
for year in range(2000, 2031):
    TAGLIST.append(f"{year} OA procedure")

FACULTYNAMES = [
    "EEMCS",
    "BMS",
    "ET",
    "ITC",
    "TNW",
]
FACULTYNAMES.extend(['Faculty of Science and Technology',
                     'Faculty of Engineering Technology',
                     'Faculty of Behavioural, Management and Social Sciences',
                     'Faculty of Geo-Information Science and Earth Observation',
                     'Faculty of Electrical Engineering, Mathematics and Computer Science'])
FACULTYNAMES.extend([item.lower() for item in FACULTYNAMES])

UTRESEARCHGROUPS_HIERARCHY = {
    'ITC'  : {},
    'TNW'  : {
        'Applied Nanophotonics (AN)'                 : [
            'Biomedical Photonic Imaging (BPI)',
            'Complex Photonic Systems (COPS)',
            'Laser Physics and Non-linear Optics (LPNO)',
            'Optical Sciences (OS)',
            'Integrated Optical Systems (IOS)',
            'Nanobiophysics (NBP)',
            'Adaptive Quantum Optics (AQO)',
        ],
        'Bioengineering Technologies (BT)'           : [
            'Advanced Organ Bioengineering and Therapeutics (AOT)',
            'Applied Stem Cell Technologies (AST)',
            'Bioelectronics (BE)',
            'Biomolecular Nanotechnology (BNT)',
            'Developmental Bioengineering (DBE)',
            'Molecular Nanofabrication (MNF)',
        ],
        'Energy, Materials and Systems (EMS)'        : [

        ],
        'Imaging and Diagnostics (ID)'               : [
            'Biomedical Photonic Imaging (BMPI)',
            'Magnetic Detection & Imaging (MDI)',
            'Medical Cell Biophysics (MCBP)',
            'Multi-Modality Medical Imaging (M3I)',
            'Physics of Fluids (POF)',
        ],
        'Membrane Science and Technology (MST)'      : [
            'Membrane Surface Science (MSUS)',
            'Soft matter, Fluidics and Interfaces (SFI)',
            'Films in Fluids (FIF)',
            {'Membrane Process Technology (MPT)': [
                'Membranes for Harsh Conditions (MHC)',
                'Membrane Processes for Food (MPF)',
                'Membrane Technology and Engineering for Water Treatment (MTEWT)',
            ]},
        ],
        'Nano Electronic Materials (NEM)'            : [
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
        'Physics Of Fluids (POF)'                    : [
            'Physics Of Fluids (POF)',
        ],
        'Process and Catalysis Engineering (PCE)'    : [
            'Catalytic Processes and Materials (CPM)',
            'Sustainable Process Technology (SPT)',
            'Mesoscale Chemical Systems (MCS)',
            'Photocatalytic Syntheses (PCS)',
        ],
        'Soft Matter (SM)'                           : [
            'Bioelectronics (BE)',
            'Physics of Complex Fluids (PCF)',
            'Nanobiophysics (NBP)',
        ],
        'Translational Physiology (TP)'              : [
            'Clinical Neurophysiology (CNPH)',
            'Cardio-Respiratory Physiology (CRPH)',
        ]
    },
    'EEMCS': {
        'Computer Science (CS)'      : [
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
            'Mathematics of Operations Research (MOR)'          : [
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
            'Mathematics of Data Science (MDS)'                 : [
                'Mathematics of Imaging & AI (MIA)',
                'Statistics (STAT)',
            ]
        }]
    },
    'BMS'  : {
        'Department of technology, policy and society (TPS)'               : [
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
        'Department of Learning, Data analytics and Technology (LDT)'      : [
            'ELAN Teacher Development',
            'Instructional Technology (IST)',
            'Professional Learning & Technology (PLT)',
            'Cognition, Data and Education (CODE)',
        ],
        'Department of High-tech Business and Entrepreneurship (HBE)'      : [
            'Industrial Engineering and Business Information Systems (IEBIS)',
            'Entrepeneurship, Technology and Management (ETM)',
            'Financial Engineering (FE)',
        ],
    },
    'ET'   : {
        'Biomechanical Engineering (BE)'                 : [
            'Biomechatronics and Rehabilitation Technology (BRT)',
            'Biomedical Device Design and Production (BDDP)',
            'Engineering Organ Support Technologies (EOST)',
            'Neuromechanical Engineering (NE)',
            'Surgical Robotics (SR)',
        ],
        'Civil Engineering and Management (CEM)'         : [
            'Integrated Project Delivery (IPD)',
            'Multidisciplinary Water Management (MWM)',
            'Water Engineering and Management, in particular Watersystems (WS)',
            'Coastal Systems and Nature Based Engineering (CSNBE)',
            'Market Dynamics (MD)',
            'Soil Micro Mechanics (SMM)',
            'Transport Engineering and Management (TEM)',
            'Transport Planning (TP)',
        ],
        'Design, Production and Management (DPM)'        : [
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
        'Thermal and Fluid Engineering (TFE)'            : [
            'Engineering Fluid Dynamics (EFD)',
            'Multi-Scale Mechanics (MSM)',
            'Thermal Engineering (TE)',
        ],
    }
}
UTRESEARCHGROUPS_FLAT: dict[str, str] = {
    'Advanced Membranes for Aqueous Applications (AMAA)'   : 'TNW',
    'Adaptive Quantum Optics (AQO)'                        : 'TNW',
    'Analog signal processing devices and systems (ASPDS)' : 'TNW',
    'Applied Stem Cell Technologies (AST)'                 : 'TNW',
    'Bioelectric signaling and engineering (BIOEE)'        : 'TNW',
    'Bioelectronics (BE)'                                  : 'TNW',
    'Advanced Organ bioengineering and Therapeutics (AOT) ': 'TNW',
    'Biomedical Photonic Imaging (BMPI)'                   : 'TNW',
    'Biomolecular Nanotechnology (BNT)'                    : 'TNW',
    'Cardiovascular and Respiratory Physiology (CRPH)'     : 'TNW',
    'Catalytic Processes and Materials (CPM)'              : 'TNW',
    'Clinical Neurophysiology (CNPH)'                      : 'TNW',
    'Computational Chemical Physics (CCP)'                 : 'TNW',
    'Complex Photonic Systems (COPS)'                      : 'TNW',
    'Developmental BioEngineering (DBE)'                   : 'TNW',
    'Energy, Materials and Systems (EMS)'                  : 'TNW',
    'Films in Fluids (FIF)'                                : 'TNW',
    'Hybrid Materials for Opto-Electronic (HMOE)'          : 'TNW',
    'Industrial Focus Group XUV Optics (XUV)'              : 'TNW',
    'Inorganic Membranes (IM)'                             : 'TNW',
    'Inorganic Materials Science (IMS)'                    : 'TNW',
    'Interfaces and Correlated Electron Systems (ICE)'     : 'TNW',
    'Integrated Optical Systems (IOS)'                     : 'TNW',
    'Laser Physics and Non-linear Optics (LPNO)'           : 'TNW',
    'Magnetic Detection & Imaging (MD&I)'                  : 'TNW',
    'Materials Science and Technology of Polymers (MTP)'   : 'TNW',
    'Medical Cell BioPhysics (MCBP)'                       : 'TNW',
    'Membrane Process Technology (MPT)'                    : 'TNW',
    'Membrane Surface Science (MSUS)'                      : 'TNW',
    'Mesoscale Chemical Systems (MCS)'                     : 'TNW',
    'Molecular Nanofabrication (MNF)'                      : 'TNW',
    'Multi-Modality Medical Imaging (M3I)'                 : 'TNW',
    'Nanobiophysics (NBP)'                                 : 'TNW',
    'Nonlinear Nanophotonics Group (NLNP)'                 : 'TNW',
    'Optical Sciences (OS)'                                : 'TNW',
    'Photo-catalytic Synthesis (PCS)'                      : 'TNW',
    'Physics of Complex Fluids (PCF)'                      : 'TNW',
    'Physics of Fluids (POF)'                              : 'TNW',
    'Physics of Interfaces and Nanomaterials (PIN)'        : 'TNW',
    'Polymer Chemistry and Biomaterials (PBM)'             : 'TNW',
    'Quantum Transport in Matter (QTM)'                    : 'TNW',
    'Soft matter, Fluidics and Interfaces (SFI)'           : 'TNW',
    'Sustainable Polymer Chemistry (SPC)'                  : 'TNW',
    'Sustainable Process Technology (SPT)'                 : 'TNW',
}


def get_flat_groups() -> dict[str, str]:
    flatgroups = {}
    global UTRESEARCHGROUPS_FLAT
    for fac, grouplist in UTRESEARCHGROUPS_HIERARCHY.items():
        if fac in ['ITC']:
            continue  # ITC still needs to be added
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
    return UTRESEARCHGROUPS_FLAT
