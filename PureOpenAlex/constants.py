FACULTYNAMES = ["EEMCS", "BMS", "ET", "ITC", "TNW", 'eemcs', 'bms', 'et', 'itc','tnw']
TAGLIST = ["UT-Hybrid-D", "UT-Gold-D", "NLA", "N/A OA procedure"]
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
start_year = 2000
end_year = 2030

for year in range(start_year, end_year + 1):
    TAGLIST.append(f"{year} OA procedure")

# Now TAGLIST has all the OA procedures up till 2030
TWENTENAMESDELETE = [
    "university of twente",
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
