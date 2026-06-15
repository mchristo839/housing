"""
Find a Housing Provider — data pipeline (expanded universe).

Provider universe = every company in the enriched database that does MORE than
homecare (i.e. has at least one housing / supported-living / accommodation
category) AND is reachable (has an email, a contact page, or a verified website).
Homecare-only companies are excluded.

Sources (all in data/, mirror of care-housing-data/):
  care_housing_database_v2_ENRICHED.xlsx
    - "Companies"               → master list: contacts, contract counts, councils, charity
    - "Company × Council × Sector" → categories per company
    - "Councils"                → council → ONS region + asylum contractor
  Care_Database_Employee_Numbers.xlsx → employee counts (matched where possible)
  CareLeads_Provider_Contacts.xlsx    → curated 58 "in-network" contacts (override)

Emits:
  public/providers.json  — filtered provider records
  public/db.json         — {c: council->[], r: region->[], n: []} index for the engine

Re-run: python build_data.py
"""
import os, re, json, html, openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT  = os.path.join(HERE, "api", "_data")      # server-only — NOT publicly served
PUB  = os.path.join(HERE, "public")            # public, aggregate-safe data only
os.makedirs(OUT, exist_ok=True)
os.makedirs(PUB, exist_ok=True)
# Input workbook. Override per month with:  FAHP_INPUT=data/your_file.xlsx npm run data
ENRICHED = os.environ.get("FAHP_INPUT") or os.path.join(DATA, "care_housing_database_v2_ENRICHED.xlsx")
if not os.path.isabs(ENRICHED):
    ENRICHED = os.path.join(HERE, ENRICHED)
print(f"Input: {os.path.relpath(ENRICHED, HERE)}")

# Atomic categories that count as "more than homecare".
HOUSING_CATS = {
    "Supported living", "Supported accommodation", "Community accommodation",
    "Emergency accommodation", "Emergency housing", "Asylum housing",
    "Extra care housing", "Children's homes", "Housing",
}
# Display preference order for a provider's primary category.
PRIMARY_PREF = [
    "Supported living", "Supported accommodation", "Community accommodation",
    "Emergency accommodation", "Emergency housing", "Asylum housing",
    "Extra care housing", "Children's homes", "Housing", "Homecare",
]

# obvious non-provider / placeholder rows in the procurement data
JUNK_NAME = re.compile(r"^(see |please see|tbc\b|n/?a$|\d+$|.*attachment|.*breakdown|.*weblink|.*supplier)", re.I)

# Manual per-name drop list — names verified to be NOT actual housing suppliers,
# or whose only stored contact is for an unrelated business with no findable
# real contact that relates to the actual supplier. Survives monthly refreshes.
import json as _json, os as _os
def _load_drop_list():
    p = _os.path.join("data", "MANUAL_DROP_LIST.json")
    if not _os.path.exists(p): return set()
    try:
        return {n.lower().strip() for n in _json.load(open(p, encoding='utf-8'))}
    except Exception:
        return set()
MANUAL_DROP_LIST = _load_drop_list()

# Verification status — providers we've put through the 4-step check live in
# data/verification/VERIFIED.json. Map keys are normalised lowercase company
# names. Anything in this map gets a "verified": true flag on its provider
# record so the UI can render a Verified badge. Everything else defaults to
# the "Listed" tier (on a government framework, awaiting manual verification).
def _load_verified():
    p = _os.path.join("data", "verification", "VERIFIED.json")
    if not _os.path.exists(p): return {}
    try:
        raw = _json.load(open(p, encoding='utf-8'))
        return {k.lower().strip(): v for k, v in raw.items()}
    except Exception:
        return {}
VERIFIED_MAP = _load_verified()

# Tender-document text fragments that ended up in the supplier-name column —
# these aren't real entities, they're notes from procurement portals.
TENDER_TEXT_NAME = re.compile(
    r"^(?:None awarded|Not awarded|Please Note|Lot\s*\d+\b|"
    r"Sai-?pac \(on behalf|None\b\s*$|tbc$|tbd$|Tender (?:closed|withdrawn)|"
    r"Not selected|Discontin|Award (?:withdrawn|cancelled)|"
    r"Place holder|placeholder|on behalf of)",
    re.I,
)

# Domain blacklist — websites that aren't a real supplier homepage but ended
# up as the website field for a row (hotel booking sites, directories,
# unrelated commercial sites, dictionaries, etc.). Drop the supplier entirely.
BLACKLIST_DOMAINS = {
    'bluepillow.com','br.bluepillow.com','booking.com','expedia.com',
    'tripadvisor.com','visitwestwardho.co.uk',
    'amazon.co.uk','amazon.com','ebay.co.uk','mapquest.com',
    'tracxn.com','tinytax.co.uk','companywall.co.uk','company-check.co.uk',
    'companiesintheuk.co.uk','okredo.lt','wikipedia.org',
    'merriam-webster.com','piliapp.com',
    'gcw.co.uk','weirbags.co.uk','sseenergysolutions.co.uk','paypoint.com',
    'graftonmerchantinggb.co.uk','ssi-schaefer.com','btinternet.com',
    'roosacademyofperformingarts.co.uk','inspirations-oadby.co.uk',
    'canleyclassics.com','cms.law','bajajconsumercare.com',
    'caseboard.io','d3tenders.com','collab365.com',
    'elder.org','consolidate.org.uk','londonconsultancy4you.co.uk',
    'iwm.org.uk','shop.fsip.biz','immi.homeaffairs.gov.au',
    'executivecompass.co.uk','rocketreach.co','zoominfo.com',
    'fazz.com',  # cryptocurrency wallet
    'nookres.com.au',  # wrong jurisdiction
    # New (from name-vs-domain audit June 2026): wrong-attribution domains where
    # the URL points to an unrelated business or to a listing page rather than
    # the supplier's own site. Drops the website but the provider stays
    # (their council/contract evidence is still valid via build pipeline).
    'thegazette.co.uk','dreams.co.uk','premierinn.com','thepsychictree.co.uk',
    'masonicarms.co.uk','akmbuilders.co.uk','auditcare.com','axiomsoftware.com',
    'ecommercefulfilment.com','gis-solved.com','infiniteengineering.co.uk',
    'sheffielddirectory.org.uk','joinerybath.co.uk','recruiter.co.uk',
    'greatyarmouthmercury.co.uk','bexley.cylex-uk.co.uk',
    # Council-directory landing pages — these are placeholders not own sites
    # (when a provider's "website" is a council page, we have no real site)
    'walthamforest.gov.uk','westminster.gov.uk','croydon.gov.uk',
    'towerhamlets.gov.uk','ealing.gov.uk','lambeth.gov.uk','merton.gov.uk',
    # Sweep 2 (from ambiguous list verification): more wrong attributions.
    # Each one verified to be a completely unrelated business, retail/tech/
    # gov/agency, or wrong-jurisdiction site.
    'store.steampowered.com',          # Steam game store
    'libertylondon.com',               # Liberty London department store
    'jnj.com',                         # Johnson & Johnson
    'reddit.com',                      # Reddit social media
    'restore.co.uk',                   # Restore data management (NOT housing)
    'm.yelp.com','yelp.com',           # Yelp directory
    'forestry.gov.scot',               # Scottish Forestry
    'mortuary-supplies.co.uk',         # Mortuary supplies
    'patchplants.com',                 # Plant retailer
    'cider-review.com',                # Cider review site
    'mrnaexplainer.org',               # mRNA explainer
    'pomanda.com','prospeo.io','northdata.com',  # business directory sites
    'tungaloyuk.co.uk',                # Industrial cutting tools
    'belmontproperty.com','planglow.com','stepnell.co.uk',  # different unrelated cos
    'totalmobile.co.uk','autumna.co.uk','wellgate.com','clydeconcept.com',
    'clinks.org',                      # Clinks (criminal justice charity, not provider)
    'parallelparents.com','myfamilyourneeds.co.uk',
    'pkfsmithcooper.com',              # PKF accountants
    'host-students.com','unitestudents.com',   # student accommodation co's
    'mccarthyandstoneresales.co.uk',   # retirement property
    'circlehealthgroup.co.uk',         # Circle Health (private hospital chain)
    'contractfinderpro.com',           # tender finder portal
    'vision-net.ie',                   # Irish biz directory
    'staffordshireconnects.info',      # Staffordshire signposting
    'choiceandcontrol.co.uk','succeedingwithsen.com',
    'aspremovalsandstorage.co.uk',     # removals
    'tellwrightconsulting.co.uk','warnersgroup.co.uk',
    'thisisfresh.com',                 # not Calico's site
    'host-students.com','greystonecottages.co.uk',
    'allabout-u.co.uk','impeccableservice.co.uk',
    'theholbrookmanor.com',            # Holbrook Manor not Hilbroke
    'pgbaileyandson.co.uk',            # not P G Ingoldby
    '2bactivemidlands.co.uk','obmsltd.com','alexallpress.co.uk',
    'wiserr.co.uk','scmsassociates.com','sbtiservices.com',
    'skyline-group.net','helgroup.com','tdfgroupltd.co.uk',
    'fortice.co.uk','nsttec.com','ubu.me.uk','pcconsultants.co.uk',
    'emc-dnl.co.uk','dshees.com','zpdltd.com','wiio.co.uk',
    'waymark.digital','ghoat.co.uk','iatltd.com','rnetso.net',
    'londonptc.com','jesouthproperty.com','stmsltd.co.uk','smcgroup.co.uk',
    'rhs24.net','milesplatting.co.uk',  # Miles Platting (Adactus merged into Jigsaw)
    'gogloscomms.co.uk',
}

DIRECTORY_DOMAINS = re.compile(
    r"(?:carechoices\.co\.uk|carehome\.co\.uk|192\.com|"
    r"patient\.info|cqc\.org\.uk|ofsted\.gov\.uk|"
    r"find-and-update\.company-information|nhs\.uk/services|"
    r"linkedin\.com|facebook\.com)", re.I)

# companies whose business is clearly NOT care/housing (FM, construction, staffing, hotels…)
NONCARE_NAME = re.compile(
    r"\bhotel\b|\bmotel\b|\bstaffing\b|\brecruit|security services|facilities management|"
    r"\bcleaning\b|\bcatering\b|\belectrical\b|\bplumbing\b|scaffold|\broofing\b|\bconstruction\b|"
    r"\blogistics\b|\binsurance\b|\bvehicle|\bmotors?\b|\bsoftware\b|hospitality|surveyors?|"
    r"\barchitect|solicitor|\bchambers\b|distributors|\bfactors\b|asbestos|air conditioning|"
    r"refrigeration|\bbuilders\b|scaffolding|furniture|furnishing|\btravel\b|travel management|"
    r"\blogistics\b|salvage|\bmarine\b|conferences?|knotweed|\bkpmg\b|\bipsos\b|\baecom\b|"
    r"caledonia|interior services|research services|opinion research", re.I)

# Individual care facilities (not housing-provider landlord-prospects).
# These operate from their own/leased single buildings under CQC — they ARE the
# facility, they aren't looking for property to operate out of. User decision:
# remove from the supported-housing universe.
# "Extra Care" providers are EXEMPT (they operate over many housing schemes).
CARE_FACILITY_NAME = re.compile(
    r"\b(?:"
    r"care home(?:s)?|"
    r"nursing home(?:s)?|"
    r"residential home(?:s)?|"
    r"residential care home|"
    r"care centre|care center|"
    r"care lodge|care manor"
    r")\b",
    re.I,
)
CARE_FACILITY_EXEMPT = re.compile(r"\bextra care\b", re.I)

# Homecare/domiciliary agencies (visit clients in clients' own homes).
# By name pattern — they're delivery agencies, not landlord-prospects looking
# for property to lease/buy. Filter at build time same as care-facility.
# Exempt = providers whose name says housing/supported-living explicitly.
HOMECARE_NAME = re.compile(
    r"\b(?:"
    r"home care(?:s)?|"
    r"homecare(?:s)?|"
    r"domiciliary care|"
    r"home-care"
    r")\b",
    re.I,
)
HOMECARE_EXEMPT = re.compile(
    r"\b(?:supported (?:living|housing|accommodation)|housing association|"
    r"housing trust|housing group|extra care)\b",
    re.I,
)

# Hotels / guesthouses / B&Bs — they operate their own buildings under their
# own brand. Councils use them for TA but they don't lease in. Not a
# landlord-prospect customer for the site. Drop by name pattern.
HOTEL_NAME = re.compile(
    r"\b(?:"
    r"hotel(?:s)?(?:\s+group)?|"
    r"hotels?\s+(?:ltd|limited)|"
    r"guest\s*house(?:s)?(?:\s+ltd|\s+limited)?|"
    r"travelodge|premier\s+inn|"
    r"b\s*&\s*b|bed and breakfast|"
    r"queens?\s+head\s+inn|the\s+\w+\s+inn|"
    r"doubletree(?:\s+by)?|hilton(?:\s+hotels)?|marriott|"
    r"holiday\s+inn|ibis(?:\s+styles)?|novotel"
    r")\b",
    re.I,
)

# Construction / contractor / property maintenance — they work on properties
# but don't operate them. Not landlord-prospects.
CONSTRUCTION_NAME = re.compile(
    r"\b(?:"
    r"building contractor(?:s)?|"
    r"joinery(?:\s+and\s+building)?|"
    r"property maintenance(?:\s+services|\s+contractor)?|"
    r"construction services|construction group|"
    r"refurbishment contractor|civil engineering(?:\s+ltd|\s+limited)|"
    r"plant hire"
    r")\b",
    re.I,
)

# Estate agents / property mgmt / haulage — manage property portfolios or move
# goods, don't operate supported housing themselves.
PROPERTY_MGMT_NAME = re.compile(
    r"\b(?:"
    r"estate agents?|letting agents?|"
    r"property management(?:\s+(?:ltd|limited))?|"
    r"partnering in property"
    r")\b",
    re.I,
)
HAULAGE_NAME = re.compile(
    r"\b(?:haulage|haulier|freight forwarding|logistics ltd)\b",
    re.I,
)

# soft non-care signals (construction / regeneration majors) — only drop if the name
# has no care/housing word (protects e.g. "EMH Housing and Regeneration").
NONCARE_SOFT = re.compile(r"regeneration|\bengie\b|\bequans\b|\blovell\b|\bwates\b|\bkier\b|"
                          r"willmott|galliford|\baxis europe\b|property solutions|property services", re.I)
CARE_EXEMPT = re.compile(r"housing|\bcare\b|support|living|mencap|\btrust\b|association|foundation|"
                         r"\bmind\b|society|cyrenian|centrepoint|depaul|riverside|sanctuary|mungo|"
                         r"shelter|refuge|homes?\b|mental health|disab|autis", re.I)

# client groups inferred from contract titles + categories ("what they do")
CLIENT_GROUPS = [
    ("Learning disabilities", r"learning disab|\bld\b"),
    ("Autism", r"autis"),
    ("Mental health", r"mental health"),
    ("Physical disabilities", r"physical disab|physical and sensory"),
    ("Acquired brain injury", r"brain injur|\babi\b"),
    ("Older people", r"older people|elderly|dementia|extra care"),
    ("Homelessness", r"homeless|rough sleep"),
    ("Young people & care leavers", r"young people|care leaver|leaving care|16-25|18-25|\bchildren\b|cared for"),
    ("Substance misuse", r"substance|drug and alcohol|\balcohol\b"),
    ("Domestic abuse", r"domestic abuse|domestic violence|women'?s refuge|\brefuge\b"),
    ("Asylum & refugees", r"asylum|refugee"),
    ("Sensory impairment", r"sensory|visual impair|hearing impair"),
]
CG_RE = [(label, re.compile(rx, re.I)) for label, rx in CLIENT_GROUPS]

# housing-association detection (organisations that typically own/build their own stock)
HA_KNOWN = re.compile(
    r"housing association|registered provider|peabody|riverside|sanctuary|clarion|guinness|hightown|"
    r"places for people|home group|livewest|salvation army homes|two saints|adullam|framework housing|"
    r"hestia|metropolitan|orbit|stonewater|sovereign|midland heart|bromford|platform housing|"
    r"citizen housing|\babri\b|\bvivid\b|\baster\b|onward|torus|great places|prospect|accent|regenda|"
    r"jigsaw|notting hill|southern housing|network homes|paradigm|catalyst|grand union|futures housing|"
    r"\bemh\b|nottingham community|trident|\bhyde\b|anchor|housing trust|housing plus|community gateway",
    re.I)
def is_housing_assoc(name):
    n = name.lower()
    if HA_KNOWN.search(n): return True
    if "housing" in n and re.search(r"associat|trust|group|partnership|society|\bha\b", n): return True
    if re.search(r"\bhomes\b\s*(ltd|limited)?\s*$", n): return True
    return False

def client_groups_of(full_titles, cats):
    text = (" ".join(full_titles) + " " + " ".join(cats)).lower()
    return sorted({label for label, rx in CG_RE if rx.search(text)})

# council key shared with the LHA join + the engine (matches postcodes.io admin_district)
def norm_council_key(s):
    s = str(s or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    drop = {"council","borough","county","city","district","the","of","metropolitan",
            "unitary","authority","corporation","mbc","mdc","cc"}
    return " ".join(t for t in s.split() if t not in drop)

def load_lha():
    path = os.path.join(DATA, "LHA_Rates_by_Council_2026_27.xlsx")
    if not os.path.exists(path): return {}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["LHA Rates 2026-27"]
    out = {}
    for r in ws.iter_rows(min_row=3, values_only=True):
        if not r[0]: continue
        out[norm_council_key(r[0])] = {
            "council": r[0], "brma": r[1],
            "shared": r[2], "bed1": r[3], "bed2": r[4], "bed3": r[5], "bed4": r[6],
        }
    wb.close()
    return out

# facilities-management / works contract titles (used to strip noise and detect FM-only firms)
FM_TITLE = re.compile(
    r"decorat|re-?roof|roofing|\brepairs?\b|decarbon|cyclical|\bmaintenance\b|works framework|"
    r"\brefurb|call handling|out of hours|grounds|\bcleaning\b|\bcatering\b|\bsecurity\b|cctv|"
    r"fire (safety|alarm|risk)|gas servic|\belectrical\b|\bplumbing\b|painting|\bvoid|capital works|"
    r"planned works|\bfencing\b|window|asbestos|legionella|vaccinat|interpret|translation|stationery|"
    r"software|\bict\b|\bvehicle|fleet|\binsurance\b|\bsurvey|valuation|consultanc|\baudit\b|"
    r"agency (staff|worker)|temporary staff|recruit|managed print|print servic|telephony|utilities|"
    r"landscap|pest control|waste |hhsrs|damp and mould|improvement works|"
    r"\blighting\b|highways?|carriageway|gritting|street works|term contract for", re.I)

# one-off / non-care contract titles (COVID emergency, furniture, travel, logistics, training…)
IRRELEVANT_TITLE = re.compile(
    r"covid|\bwave\s*2\b|\bfurniture\b|furnishing|\btravel\b|venue hire|conference|"
    r"\blogistics\b|\bmarine\b|salvage|knotweed|\bweed\b|road marking|sign installation|"
    r"learning and development|\btraining\b|framework design|goods for syria|"
    r"global logistics|managed travel|corporate travel|charter of|embassy|"
    r"outcome framework|sector awareness|independent care sector|"
    r"meat and dairy|\bsupplier\b|\bsupplies\b|catering|catered|\bkitchen|\bfood\b|"
    r"\bmeals?\b|meals on wheels|ready meals|prepared meals|frozen|bakery|beverage|produce|"
    r"grocer|provisions|laundry|uniform|stationery|vending|"
    r"accommodation assessment|needs assessment|opinion research|market research|"
    r"\bresearch\b|feasibility|"
    r"gp surgery|\bsurgery\b|health centre|medical centre|\bclinic\b|\bdental\b|pharmacy|gp practice", re.I)

def is_junk_title(t):
    return bool(FM_TITLE.search(t) or IRRELEVANT_TITLE.search(t))

# A contract counts only if HOUSING is part of the agreement — i.e. it's a Housing-sector
# contract, or its title names supported living / accommodation / housing. Pure domiciliary
# homecare ("Support to Live at Home", "Home Care", etc.) is stripped.
HOUSING_TITLE = re.compile(
    r"supported living|supported accommodation|supported housing|housing support|"
    r"housing related support|\bhousing\b|extra care|sheltered|\bhostel\b|\brefuge\b|"
    r"emergency accommodation|temporary accommodation|\basylum\b|move[ -]?on|"
    r"\btenanc|\baccommodation\b|\bsupported\b|"
    # HMPPS Community Accommodation Service (CAS-1 Approved Premises / CAS-2 bail / CAS-3 transitional)
    r"community accommodation service|\bcas[- ]?[123]\b|"
    r"approved premises|bail accommodation|probation accommodation", re.I)

# care DELIVERED to residents (not housing the provider supplies) — strip even if the
# title mentions a housing scheme. The provider here delivers care, not property.
HOMECARE_OVERRIDE = re.compile(
    r"home[- ]?based care|home care service|\bdomiciliar|care at home|"
    r"care and support in the home|home support service|reablement|"
    r"\bday care\b|day opportunities|short breaks|\brespite\b|sitting service", re.I)

def rec_is_housing(rec):
    titles = rec.get("titles", "")
    if is_junk_title(titles):          # food/FM/supplier/research/etc never count as housing
        return False
    if HOMECARE_OVERRIDE.search(titles):   # care delivery, not housing provision
        return False
    if rec.get("sector") == "Housing":
        return True
    return bool(HOUSING_TITLE.search(titles))

# place-name → region lookup, so a "National" contract whose TITLE names a specific
# county/town (e.g. "…in Hertfordshire") can be reclassified to that area's region.
_COUNCIL_KW = re.compile(r"\b(metropolitan district council|metropolitan borough council|"
                         r"county council|borough council|district council|city council|"
                         r"unitary authority|corporation|council)\b", re.I)
def _place_of(council):
    c = council.split(" - ")[0]                       # drop "- Adult Care Services" suffixes
    c = re.sub(r"(london|royal) borough of", " ", c, flags=re.I)
    c = _COUNCIL_KW.split(c)[0]                        # text before the council-type keyword
    c = re.sub(r"[^a-z ]", " ", c.lower())
    return re.sub(r"\s+", " ", c).strip()

def build_place_maps(council_region):
    place_region = {}
    place_county = {}                                  # place -> (county_name, region) for county councils
    county_abbrev = {}                                 # WSCC -> (west sussex, region)
    place_council = {}                                 # place -> (council display, scope, county-key, region) ALL councils
    # place keys too generic/ambiguous to match safely in free text
    region_names = {r.lower() for r in council_region.values() if r}
    PLACE_STOP = region_names | {"london", "england", "city", "council", "care", "health",
                                 "common", "central", "valley", "shared services"}
    for council, region in council_region.items():
        if not region: continue
        name = _place_of(council)
        if not name or len(name) < 4: continue
        if name in place_region and place_region[name] != region: place_region[name] = None
        elif name not in place_region: place_region[name] = region
        if "county council" in council.lower():
            place_county[name] = (name, region)
            base = council.split(" - ")[0]
            abbr = "".join(w[0] for w in base.split() if w[:1].isalpha()).upper()
            if 2 <= len(abbr) <= 6: county_abbrev[abbr] = (name, region)
            if name not in PLACE_STOP: place_council.setdefault(name, (council, "County", name, region))
        elif name not in PLACE_STOP:
            place_council.setdefault(name, (council, "Local", "", region))
    place_region = {k: v for k, v in place_region.items() if v}
    return place_region, place_county, county_abbrev, place_council

# Curated multi-borough abbreviations (London bi/tri-boroughs etc.) → member councils.
# These resolve to the actual councils the framework covers, not the whole region.
GROUP_ABBREV = {
    "RBKC": [("Royal Borough of Kensington and Chelsea", "Local", "", "London"),
             ("Westminster City Council", "Local", "", "London")],   # bi-borough
    "LBTH": [("London Borough of Tower Hamlets", "Local", "", "London")],
    "LBHF": [("London Borough of Hammersmith & Fulham", "Local", "", "London")],
    "LBBD": [("London Borough of Barking and Dagenham", "Local", "", "London")],
    "LBWF": [("London Borough of Waltham Forest", "Local", "", "London")],
    "RBG":  [("Royal Borough Of Greenwich", "Local", "", "London")],
    "RBWM": [("Royal Borough of Windsor and Maidenhead", "Local", "", "South East")],
}
PAN_RE = re.compile(r"pan[- ]?london|london[- ]?wide|all (london|boroughs)|"
                    r"pan[- ]?region|region[- ]?wide|sub[- ]?regional", re.I)

def classify_title(text, place_region, place_county, county_abbrev, place_council):
    """Work out which council(s)/area a contract or commissioner names.
    Returns ('members', [(council,scope,county,region),...]) | ('region', reg) | (None, None)."""
    raw = str(text or "")
    members = []
    for tok in re.findall(r"\b[A-Z][A-Za-z]{1,5}\b", raw):
        if tok in GROUP_ABBREV: members += GROUP_ABBREV[tok]
        elif tok in county_abbrev:
            cp, reg = county_abbrev[tok]
            members.append((cp.title() + " County Council", "County", cp, reg))
    # Normalize the input text the SAME way _place_of() normalized the place keys:
    # (1) strip "(london|royal) borough of" so "Royal Borough of Kingston upon Thames" matches
    #     the place key "kingston upon thames"; (2) collapse multiple spaces left by stripping
    #     "&" so "Redcar & Cleveland" matches the place key "redcar cleveland".
    norm = re.sub(r"(london|royal) borough of", " ", raw, flags=re.I)
    norm = re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", norm.lower())).strip()
    tl = " " + norm + " "
    hits = [p for p in place_council if len(p) >= 4 and f" {p} " in tl]
    # drop a place that is a sub-phrase of a longer matched place
    # (e.g. "lincolnshire" inside "north east lincolnshire")
    hits = [p for p in hits if not any(p != q and f" {p} " in f" {q} " for q in hits)]
    for p in hits:
        members.append(place_council[p])
    if members:
        seen, uniq = set(), []
        for m in members:
            if m[0] not in seen: seen.add(m[0]); uniq.append(m)
        return ("members", uniq)
    regions = {place_region[p] for p in place_region if f" {p} " in tl}
    if len(regions) == 1:
        return ("region", next(iter(regions)))
    return (None, None)

# procurement portals / platforms / HAs / NHS bodies recorded as the "council" —
# region is unreliable, so geography is taken from the title (else excluded).
COMMISSIONER_JUNK = re.compile(
    r"shared services|in-?tend|e-?tendering|procurement|\bportal\b|consortium|\besi\b|"
    r"capital ?esourcing|eu supply|due north|business services|\blgss\b|supply hertfordshire|"
    r"housing association|housing group|housing trust|housing society|\bhousing limited\b|"
    r"commissioning support|\bicb\b|\bccg\b|foundation trust", re.I)

# Direct commissioner override map — for awkward commissioner names where the resolver
# can't honestly infer the council(s). Each entry: (regex, [(council, scope, county_key, region), ...]).
# Conservative on purpose: only documented 1-to-1 or small, bounded mappings.
# A hit here SHORT-CIRCUITS all other resolution (consortium / classify_title / scope reconciliation).
# This is the surgical fix for cases like NHS-FT-as-commissioner where match.js can never find
# the right council via its normCouncilKey() lookup.
COMMISSIONER_MAP = [
    # NHS CCGs/ICBs/Trusts with a documented single-council catchment
    (re.compile(r"\bnhs north east lincolnshire (clinical commissioning group|ccg|icb)\b", re.I),
     [("North East Lincolnshire Council", "Local", "", "Yorkshire & The Humber")]),
    (re.compile(r"\bnhs sheffield (ccg|icb|clinical commissioning group)\b", re.I),
     [("Sheffield City Council", "Local", "", "Yorkshire & The Humber")]),
    (re.compile(r"^salford royal nhs|salford health.*salford royal", re.I),
     [("Salford City Council", "Local", "", "North West")]),
    # Oxleas NHS FT — documented clinical catchment is SE London. We map only the boroughs
    # present in our data (Bexley, Bromley). Greenwich would be added if/when it appears.
    (re.compile(r"\boxleas nhs\b", re.I),
     [("London Borough of Bexley", "Local", "", "London"),
      ("London Borough of Bromley", "Local", "", "London")]),
    # LGSS = Local Government Shared Services — joint Cambs + Northants procurement function
    (re.compile(r"\blgss\b", re.I),
     [("Cambridgeshire County Council", "County", "cambridgeshire", "East of England"),
      ("Northamptonshire County Council", "County", "northamptonshire", "East Midlands")]),
]
def match_commissioner_override(council):
    for rx, members in COMMISSIONER_MAP:
        if rx.search(council):
            return members
    return None

# commissioners that don't commission supported HOUSING at all — drop their contracts
# (universities = student accommodation, police/fire, government departments, catering).
# NB: "ministry of justice" used to be here but was removed — MOJ/HMPPS genuinely
# commissions supported/probation accommodation (CAS-2 Nacro national contract,
# CAS-3 regional lots to Mears Group / The Housing Network / others).
COMMISSIONER_EXCLUDE = re.compile(
    r"universit|\bcollege\b|\bpolice\b|\bcrime\b|fire (and|&) rescue|constabulary|"
    r"\bcatering\b|legal aid|cabinet office|\bforeign\b|commonwealth|"
    r"maritime|coastguard|\bjncc\b|improvement and development|department for|"
    r"international development|crown commercial", re.I)

# Purchasing CONSORTIA: contracts they let cover ALL their member authorities, so a
# consortium framework surfaces for every member area. Each member: (display council,
# scope, county-key, region). Researched memberships (ESPO/YPO/Welland).
CONSORTIA = [
    ("ESPO framework", re.compile(r"\bespo\b|eastern shires", re.I), [
        ("Leicestershire County Council", "County", "leicestershire", "East Midlands"),
        ("Lincolnshire County Council", "County", "lincolnshire", "East Midlands"),
        ("Cambridgeshire County Council", "County", "cambridgeshire", "East of England"),
        ("Norfolk County Council", "County", "norfolk", "East of England"),
        ("Warwickshire County Council", "County", "warwickshire", "West Midlands"),
        ("Peterborough City Council", "Local", "", "East of England"),
    ]),
    ("YPO framework", re.compile(r"\bypo\b|yorkshire purchasing", re.I), [
        ("North Yorkshire Council", "County", "north yorkshire", "Yorkshire & The Humber"),
        ("Barnsley Metropolitan Borough Council", "Local", "", "Yorkshire & The Humber"),
        ("Bradford Metropolitan District Council", "Local", "", "Yorkshire & The Humber"),
        ("Calderdale Council", "Local", "", "Yorkshire & The Humber"),
        ("Doncaster Council", "Local", "", "Yorkshire & The Humber"),
        ("Kirklees Council", "Local", "", "Yorkshire & The Humber"),
        ("Rotherham Metropolitan Borough Council", "Local", "", "Yorkshire & The Humber"),
        ("Wakefield Council", "Local", "", "Yorkshire & The Humber"),
        ("Bolton Council", "Local", "", "North West"),
        ("Knowsley Council", "Local", "", "North West"),
        ("Wigan Council", "Local", "", "North West"),
        ("St Helens Council", "Local", "", "North West"),
    ]),
    ("Welland Procurement", re.compile(r"welland procurement", re.I), [
        ("Melton Borough Council", "Local", "", "East Midlands"),
        ("Harborough District Council", "Local", "", "East Midlands"),
        ("Rutland County Council", "County", "rutland", "East Midlands"),
        ("South Kesteven District Council", "Local", "", "East Midlands"),
    ]),
    ("Coventry–Solihull–Warwickshire", re.compile(r"coventry\s*[-,]\s*solihull", re.I), [
        ("Coventry City Council", "Local", "", "West Midlands"),
        ("SOLIHULL METROPOLITAN BOROUGH COUNCIL", "Local", "", "West Midlands"),
        ("Warwickshire County Council", "County", "warwickshire", "West Midlands"),
    ]),
    ("EEM framework", re.compile(r"efficiency east midlands|\beem\b", re.I), [
        ("East Midlands (EEM framework)", "Regional", "", "East Midlands"),
    ]),
    # London consortia — user-supplied membership (June 2026 refresh).
    # Critical for surfacing London borough coverage because most London boroughs
    # commission supported / temporary accommodation through these bodies rather
    # than direct, so direct-council scrapes find nothing under their own name.
    ("Capital Letters", re.compile(
        r"capital letters|pan[- ]?london\s+(temporary|accommodation)|"
        r"london councils.*capital", re.I), [
        ("London Borough of Barnet Council", "Local", "", "London"),
        ("London Borough of Brent", "Local", "", "London"),
        ("London Borough of Camden", "Local", "", "London"),
        ("London Borough of Croydon", "Local", "", "London"),
        ("London Borough of Ealing", "Local", "", "London"),
        ("London Borough of Enfield", "Local", "", "London"),
        ("London Borough of Hackney", "Local", "", "London"),
        ("London Borough of Hammersmith & Fulham", "Local", "", "London"),
        ("London Borough of Haringey", "Local", "", "London"),
        ("Harrow Council", "Local", "", "London"),
        ("London Borough of Hillingdon", "Local", "", "London"),
        ("London Borough of Hounslow", "Local", "", "London"),
        ("Islington Council", "Local", "", "London"),
        ("Royal Borough of Kensington and Chelsea", "Local", "", "London"),
        ("The Royal Borough of Kingston upon Thames", "Local", "", "London"),
        ("London Borough of Lambeth", "Local", "", "London"),
        ("London Borough of Lewisham", "Local", "", "London"),
        ("London Borough of Merton", "Local", "", "London"),
        ("London Borough of Newham", "Local", "", "London"),
        ("London Borough of Redbridge", "Local", "", "London"),
        ("London Borough of Richmond upon Thames", "Local", "", "London"),
        ("London Borough of Southwark", "Local", "", "London"),
        ("London Borough of Sutton", "Local", "", "London"),
        ("Tower Hamlets", "Local", "", "London"),
        ("London Borough of Waltham Forest", "Local", "", "London"),
        ("London Borough of Wandsworth", "Local", "", "London"),
        ("Westminster City Council", "Local", "", "London"),
    ]),
    ("West London Alliance (WLA)", re.compile(
        r"west london alliance|\bwla\b", re.I), [
        ("London Borough of Barnet Council", "Local", "", "London"),
        ("London Borough of Brent", "Local", "", "London"),
        ("London Borough of Ealing", "Local", "", "London"),
        ("Harrow Council", "Local", "", "London"),
        ("London Borough of Hillingdon", "Local", "", "London"),
        ("London Borough of Hounslow", "Local", "", "London"),
    ]),
    # LIIA — London Innovation and Improvement Alliance (ALDCS, hosted by London Councils).
    # Pan-London children's services commissioning. Runs Pan-London SCH, PLV, London
    # Accommodation Pathfinder. Membership: every London borough (32 + City of London).
    # NOTE: user-supplied data labelled this "Commissioning Alliance — 21 boroughs"
    # but cross-checking against liia.london confirms it's LIIA. The actual body called
    # "Commissioning Alliance" is a different (smaller, 14-LA) Ealing-hosted body —
    # captured below as a separate entry.
    ("LIIA / Pan-London Children's Services", re.compile(
        r"\bliia\b|london innovation and improvement|pan[- ]?london children|"
        r"pan[- ]?london (sch|secure|accommodation pathfinder|vehicle for children)", re.I), [
        ("London Borough of Camden", "Local", "", "London"),
        ("Islington Council", "Local", "", "London"),
        ("London Borough of Haringey", "Local", "", "London"),
        ("London Borough of Enfield", "Local", "", "London"),
        ("London Borough of Hackney", "Local", "", "London"),
        ("Tower Hamlets", "Local", "", "London"),
        ("London Borough of Newham", "Local", "", "London"),
        ("London Borough of Waltham Forest", "Local", "", "London"),
        ("London Borough of Barking and Dagenham", "Local", "", "London"),
        ("London Borough of Redbridge", "Local", "", "London"),
        ("London Borough of Havering", "Local", "", "London"),
        ("Royal Borough Of Greenwich", "Local", "", "London"),
        ("London Borough of Lewisham", "Local", "", "London"),
        ("London Borough of Southwark", "Local", "", "London"),
        ("London Borough of Lambeth", "Local", "", "London"),
        ("London Borough of Croydon", "Local", "", "London"),
        ("London Borough of Sutton", "Local", "", "London"),
        ("London Borough of Merton", "Local", "", "London"),
        ("London Borough of Wandsworth", "Local", "", "London"),
        ("The Royal Borough of Kingston upon Thames", "Local", "", "London"),
        ("London Borough of Richmond upon Thames", "Local", "", "London"),
    ]),
    # The Commissioning Alliance (Ealing-hosted, descended from WLA).
    # Per their official 2021 Provider Information Pack (WLA-hosted PDF):
    # umbrella partnership with 34 LAs; Children's Social Care service area
    # extends to the 17 LAs named below. Runs the WL252400 light-touch
    # framework for Supported Accommodation + Semi-Independent Living, plus
    # the Semi-Independent Accommodation & Support DPV via CarePlace.
    ("Commissioning Alliance (Children's Social Care)", re.compile(
        r"commissioning alliance|the commissioning alliance|\bwl\d{6}\b|"
        r"semi[- ]?independent (accommodation|living) (dpv|dynamic purchasing)|"
        r"\bcareplace\b", re.I), [
        ("London Borough of Barnet Council", "Local", "", "London"),
        ("London Borough of Barking and Dagenham", "Local", "", "London"),
        ("London Borough of Brent", "Local", "", "London"),
        ("London Borough of Bromley", "Local", "", "London"),
        ("City of London Corporation", "Local", "", "London"),
        ("London Borough of Ealing", "Local", "", "London"),
        ("London Borough of Hammersmith & Fulham", "Local", "", "London"),
        ("Harrow Council", "Local", "", "London"),
        ("London Borough of Hillingdon", "Local", "", "London"),
        ("London Borough of Hounslow", "Local", "", "London"),
        ("Royal Borough of Kensington and Chelsea", "Local", "", "London"),
        ("London Borough of Merton", "Local", "", "London"),
        ("London Borough of Redbridge", "Local", "", "London"),
        ("London Borough of Southwark", "Local", "", "London"),
        ("London Borough of Wandsworth", "Local", "", "London"),
        ("Westminster City Council", "Local", "", "London"),
        ("Buckinghamshire Council", "Local", "", "South East"),
    ]),
    ("Achieving for Children", re.compile(
        r"achieving for children", re.I), [
        ("The Royal Borough of Kingston upon Thames", "Local", "", "London"),
        ("London Borough of Richmond upon Thames", "Local", "", "London"),
    ]),
]
def match_consortium(council):
    for name, rx, members in CONSORTIA:
        if rx.search(council):
            return name, members
    return None

def geo_from_title(titles, place_region, place_county, county_abbrev):
    """Derive geography from a contract title: a county-council abbreviation (WSCC) or
    county name → County; else a single region name → Regional."""
    raw = str(titles or "")
    for tok in re.findall(r"\b[A-Z]{2,6}\b", raw):
        if tok in county_abbrev:
            place, reg = county_abbrev[tok]
            return ("County", reg, place)
    tl = " " + re.sub(r"[^a-z ]", " ", raw.lower()) + " "
    counties = {place_county[p] for p in place_county if f" {p} " in tl}
    if len(counties) == 1:
        cty, reg = next(iter(counties))
        return ("County", reg, cty)
    regions = {place_region[p] for p in place_region if f" {p} " in tl}
    if len(regions) == 1:
        return ("Regional", next(iter(regions)), None)
    return (None, None, None)

DROP = {"limited","ltd","plc","cic","llp","group","the","uk","t","a","trust",
        "services","service","association","ha","society"}
def norm(s):
    if not s: return ""
    s = str(s).lower().replace("&"," and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(t for t in s.split() if t not in DROP)

def to_int(v):
    if v is None: return None
    m = re.search(r"[\d,]+", str(v))
    return int(m.group().replace(",","")) if m else None

def clean(v):
    return ("" if v is None else str(v).strip())

def title_case_company(name):
    # leave acronyms / mixed case mostly alone; only fix ALL-CAPS names
    if name.isupper() and len(name) > 3:
        small = {"of","and","the","at","in","for","to"}
        out = []
        for i, w in enumerate(name.lower().split()):
            out.append(w if (w in small and i) else (w.capitalize() if not re.search(r"\d", w) else w.upper()))
        return " ".join(out)
    return name

# ── councils → region + asylum contractor ────────────────────────────────────
def load_councils(wb):
    ws = wb["Councils"]
    hdr = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    ix = {h: i for i, h in enumerate(hdr)}
    region, asylum = {}, {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        name = clean(r[ix["Council"]])
        if not name: continue
        region[name] = clean(r[ix["ONS Region"]])
        a = clean(r[ix.get("Asylum Contractor", -1)]) if "Asylum Contractor" in ix else ""
        if a: asylum[name] = a
    return region, asylum

# ── categories + contract records per company (council×sector sheet) ─────────
def load_company_sector(wb, place_region, place_county, county_abbrev, place_council):
    ws = wb["Company × Council × Sector"]
    cats, contracts = {}, {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r[0]: continue
        k = norm(r[0])
        s = cats.setdefault(k, set())
        for src in (r[10], r[1]):                      # Categories, Sector
            if src:
                for part in re.split(r"[;|]", str(src)):
                    p = part.strip()
                    if p: s.add(p)
        council = clean(r[2])                          # Council
        if not council:
            continue
        if COMMISSIONER_EXCLUDE.search(council):       # university/police/govt/catering — not housing
            continue
        sector = clean(r[1]); n = to_int(r[3]) or 0; titles = clean(r[12])
        # Umbrella backfill — for blank titles OR opaque procurement codes,
        # prepend the publicly-verifiable umbrella framework name so every
        # contract entry links to a real document.
        _c_lc = council.lower()
        if not titles:
            if 'waltham forest' in _c_lc:
                titles = ("London Borough of Waltham Forest — Adult Social Care "
                          "Supported Living and Accommodation Provider Listing "
                          "(walthamforest.gov.uk/adult-social-care/residential-care-supported-and-sheltered-housing)")
        # Opaque Central Bedfordshire DPS call-off code → prepend umbrella
        if re.match(r'^CBC-\d+-DPS-LS', titles or ''):
            titles = ("Central Bedfordshire DPS for Supported Living and "
                      "Independent Living (Extra Care Housing) — call-off "
                      + (titles or '')
                      + " (Contracts Finder, contractsfinder.service.gov.uk)")
        # Opaque Bristol CSI/CYP placement code → prepend umbrella
        if re.match(r'^CSI/CYP/', titles or ''):
            titles = ("Bristol City Council CSI/CYP — Children's Care and "
                      "Support Services Framework — " + (titles or '')
                      + " (Bidstats 811204732 / Find a Tender)")
        # Strip Bidstats-style annotations that leak supplier-office locations
        # into the title — classify_title would otherwise interpret them as
        # the contract's geography (e.g. a Croydon contract whose Bidstats
        # entry tagged "supplier @ Newcastle upon Tyne" gets routed to Newcastle).
        titles = re.sub(r"\s*\([^)]*?supplier\s*@[^)]*\)\s*", " ", titles, flags=re.I)
        titles = re.sub(r"\s*\(Bidstats\s+\d+[^)]*\)\s*", " ", titles, flags=re.I).strip()

        # DIRECT COMMISSIONER OVERRIDE → re-route to documented council(s).
        # Runs BEFORE everything else so e.g. "Salford Royal NHS FT" lands under
        # "Salford City Council" (where Salford postcodes can find it), not under
        # an NHS-trust key the postcode matcher can never normalise.
        override = match_commissioner_override(council)
        if override:
            for (cncl, sc, cty, reg) in override:
                contracts.setdefault(k, []).append({
                    "council": cncl, "sector": sector, "n": n, "titles": titles,
                    "region": reg, "scope": sc, "county": cty, "via": "",
                })
            continue

        # REGIONAL FRAMEWORK OVERRIDE — some single-council CCS rows are actually
        # pan-regional Flexible Purchasing Systems (e.g. Bolton's TC160 is the
        # NWADCS-administered NW Supported Accommodation FPS covering 23 NW
        # authorities). Without this rule those 61 suppliers would all show up
        # as 'Bolton Local' instead of 'North West Regional'. Promote to Regional
        # tier so they surface for EVERY postcode in the named region.
        _t_lc = (titles or "").lower()
        _regional_framework = None
        _via_label = "regional framework"
        if (("tc160" in _t_lc) or
            ("north west supported accommodation" in _t_lc and "flexible purchasing" in _t_lc) or
            ("north west flexible purchasing system" in _t_lc) or
            ("nwadcs" in _t_lc)):
            _regional_framework = "North West"
            _via_label = "NWADCS FPS"
        elif (("north west send flexible purchasing" in _t_lc) or
              ("north west send fps" in _t_lc)):
            _regional_framework = "North West"
            _via_label = "NWADCS SEND FPS"
        # Bradford 16-25 Leaving Care Framework (notice 20220815144905-103277) —
        # explicit description: "accommodation and support placements across the
        # West Yorkshire region". Bradford-led but regional reach. Same pattern.
        elif (("16-25 year-old leaving care" in _t_lc) or
              ("20220815144905-103277" in _t_lc) or
              ("16-25 year-old leaving care & vulnerable young peoples" in _t_lc) or
              ("vulnerable young peoples accommodation and support" in _t_lc and "bradford" in _t_lc)):
            _regional_framework = "Yorkshire & The Humber"
            _via_label = "Bradford 16-25 Framework (W Yorks regional reach)"
        # Leeds Interim Leaving Care & Vulnerable Young People Framework
        # (notice LEEDSCITY001-DN355373) — Leeds-led 16-25 leaving care framework.
        # Same pattern — suppliers include London, Manchester, Hampshire ops.
        elif (("leeds interim leaving care" in _t_lc) or
              ("leedscity001-dn355373" in _t_lc) or
              ("leeds interim leaving care and vulnerable young people" in _t_lc)):
            _regional_framework = "Yorkshire & The Humber"
            _via_label = "Leeds 16-25 Framework (regional reach)"
        if _regional_framework:
            contracts.setdefault(k, []).append({
                "council": f"{_regional_framework} regional framework",
                "sector": sector, "n": n, "titles": titles,
                "region": _regional_framework, "scope": "Regional",
                "county": "", "via": _via_label,
            })
            continue

        # PURCHASING CONSORTIUM → expand to one record per member authority
        con = match_consortium(council)
        if con:
            name, members = con
            for (cncl, sc, cty, reg) in members:
                contracts.setdefault(k, []).append({
                    "council": cncl, "sector": sector, "n": n, "titles": titles,
                    "region": reg, "scope": sc, "county": cty, "via": name,
                })
            continue

        gs = clean(r[15]) or "Local"                   # Geographic Scope
        ct = clean(r[14])                              # Commissioner Type
        rec_region = clean(r[13])                      # ONS Region

        # Resolve which council(s) qualify from BOTH the commissioner name AND the title.
        # This handles joint/shared commissioners that name several councils
        # (e.g. "Coventry - Solihull - Warwickshire", "WCC/RBKC"), not just single ones.
        comm_res = classify_title(council, place_region, place_county, county_abbrev, place_council)
        title_res = classify_title(titles, place_region, place_county, county_abbrev, place_council)
        comm_members = comm_res[1] if comm_res[0] == "members" else []
        title_members = title_res[1] if title_res[0] == "members" else []

        # PIN only when it's genuinely a GROUP: the commissioner names 2+ councils
        # (joint/shared commissioning) OR the title names specific council(s).
        # A single-council commissioner keeps its recorded scope (don't force Local).
        if (len(comm_members) >= 2 or title_members) and not PAN_RE.search(titles):
            seen_m, members = set(), []
            for m in comm_members + title_members:
                if m[0] not in seen_m: seen_m.add(m[0]); members.append(m)
            for (cncl, sc, cty, reg) in members:
                contracts.setdefault(k, []).append({
                    "council": cncl, "sector": sector, "n": n, "titles": titles,
                    "region": reg, "scope": sc, "county": cty, "via": "",
                })
            continue

        # otherwise: original scope reconciliation (portal / national / region-wide)
        scope = gs
        county = ""
        if PAN_RE.search(titles) or title_res[0] == "region":
            scope = "Regional"
            if title_res[0] == "region": rec_region = title_res[1]
        elif "county council" in council.lower():
            scope, county = "County", _place_of(council)
            rec_region = council_region.get(council, rec_region)
        elif COMMISSIONER_JUNK.search(council) or gs == "National":
            sc, reg, cty = geo_from_title(titles, place_region, place_county, county_abbrev)
            if sc == "County":
                scope, rec_region, county = "County", reg, cty
            elif sc == "Regional":
                scope, rec_region = "Regional", reg
            elif gs == "National":
                if ct == "Local Council":
                    scope = "Local"
                elif ct in ("Regional Framework", "Housing Association"):
                    scope = "Regional"
            elif COMMISSIONER_JUNK.search(council):
                rec_region = ""
        contracts.setdefault(k, []).append({
            "council": council, "sector": sector, "n": n, "titles": titles,
            "region": rec_region, "scope": scope, "county": county, "via": "",
        })
    return cats, contracts

# ── manual additions (CAS-2/3 + any other curated rows) ──────────────────────
# Lives in data/manual_contracts.xlsx with the same sheet/column structure as
# the main workbook. Loaded AFTER the main file so its rows merge into the same
# (cats, contracts, Companies) state. Survives monthly refreshes of the main
# xlsx because it's a separate file the refresh doesn't touch.
def load_manual_additions(place_region, place_county, county_abbrev, place_council):
    path = os.path.join(DATA, "manual_contracts.xlsx")
    if not os.path.exists(path):
        return {}, {}, None
    wb_m = openpyxl.load_workbook(path, read_only=True, data_only=True)
    extra_cats, extra_contracts = load_company_sector(
        wb_m, place_region, place_county, county_abbrev, place_council
    )
    return extra_cats, extra_contracts, wb_m

def pretty_council(name):
    if name.isupper():
        small = {"of","and","the","upon","on"}
        return " ".join(w if w in small else w.capitalize() for w in name.lower().split())
    return name

# replicate the engine's normCouncil() so generated map keys match its lookups.
# IMPORTANT: keep in sync with src/engine_maps.js → normCouncil().
def norm_council_js(name):
    n = str(name).lower().strip()
    n = n.replace("&", " and ")
    n = re.sub(r",\s*city of$", " city", n)
    n = re.sub(r"^city of london corporation$", "city of london", n)
    n = re.sub(r"^(?:the\s+)?(?:london borough of|royal borough of)\s+", "", n)
    n = re.sub(r"\b(council|metropolitan borough|borough|county|district|unitary authority|mbc|lbc|the )\b", " ", n)
    if n != "city of london" and not n.startswith("city of london "):
        n = re.sub(r"\bcity\b", " ", n)
    n = re.sub(r"[^\w\s]", " ", n)
    return re.sub(r"\s+", " ", n).strip()

def _lc(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())

def clean_contract_title(t, council, company):
    """Strip the trailing commissioner (council) / supplier (company) names and AWARD tag,
    leaving just what the contract is for."""
    t = re.sub(r"\s*[-–]\s*award\s*$", "", t.strip(), flags=re.I)
    parts = re.split(r"\s+[-–]\s+", t)
    cl, co = _lc(council), _lc(company)
    while len(parts) > 1:
        p = _lc(parts[-1])
        if p and (p == cl or p == co or (cl and cl in p and len(p) <= len(cl) + 6)
                  or (co and co in p and len(p) <= len(co) + 6)):
            parts.pop()
        else:
            break
    return " - ".join(parts).strip(" -–")

SCOPE_RANK = {"National": 4, "Regional": 3, "County": 2, "Local": 1, "Unknown": 0}

def build_contracts_list(recs, company):
    """Aggregate a company's council×sector rows into per-council contract records
    with full, cleaned contract names and the broadest Geographic Scope per council.

    Grouping is by (council, scope, region) — NOT council alone — so that a single
    commissioner (e.g. "Ministry of Justice") who lets several DIFFERENT regional
    contracts (CAS-3 North West, CAS-3 Yorkshire & Humber, etc.) keeps them as
    separate per-region rows instead of collapsing into one.
    """
    by = {}
    for rec in recs:
        c = rec["council"]
        eff_scope = rec.get("scope", "Local")
        # Region precedence:
        #  - consortium expansion: trust the via row's region
        #  - explicit Regional/County scope: trust the row's region (don't let the
        #    council's canonical region override — e.g. MOJ is canonically "National"
        #    but commissions individual REGIONAL CAS-3 contracts in NW/Y&H/etc.)
        #  - otherwise: use the council's canonical region, with row region as fallback
        if rec.get("via") or eff_scope in ("Regional", "County"):
            eff_region = rec.get("region")
        else:
            eff_region = council_region.get(c, rec.get("region"))
        key = (c, eff_scope, eff_region or "")
        g = by.setdefault(key, {"council": pretty_council(c),
                              "region": eff_region,
                              "n": 0, "sectors": set(), "titles": [], "scope": "Local", "county": "", "via": ""})
        g["n"] += rec["n"]
        if rec["sector"]: g["sectors"].add(rec["sector"])
        if SCOPE_RANK.get(rec.get("scope", "Local"), 1) > SCOPE_RANK.get(g["scope"], 1):
            g["scope"] = rec["scope"]
        if rec.get("county"): g["county"] = rec["county"]
        if rec.get("via"): g["via"] = rec["via"]
        for raw in re.split(r"\s*;\s*", html.unescape(rec["titles"])):
            t = clean_contract_title(raw, c, company)
            if t and t not in g["titles"]:
                g["titles"].append(t)
    out = []
    for g in by.values():
        out.append({
            "council": g["council"], "region": g["region"], "n": g["n"],
            "scope": g["scope"], "county": g["county"], "via": g["via"],
            "sectors": sorted(g["sectors"]),
            "titles": g["titles"][:25],
        })
    out.sort(key=lambda x: x["n"], reverse=True)
    return out

def strip_fm_titles(contracts_list):
    """Remove facilities-management / one-off / non-care titles from the display list."""
    for g in contracts_list:
        g["titles"] = [t for t in g["titles"] if not is_junk_title(t)]
    return contracts_list

# ── employee counts ──────────────────────────────────────────────────────────
def load_employees():
    path = os.path.join(DATA, "Care_Database_Employee_Numbers.xlsx")
    if not os.path.exists(path): return {}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Employee Numbers"]
    idx = {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r[0]: continue
        idx[norm(r[0])] = {"employees": to_int(r[1]),
                           "confidence": clean(r[2])}
    wb.close()
    return idx

# ── curated in-network contacts (override DB contacts where present) ──────────
def load_curated():
    path = os.path.join(DATA, "CareLeads_Provider_Contacts.xlsx")
    if not os.path.exists(path): return {}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Outreach List"]
    cur = {}
    for r in ws.iter_rows(min_row=3, values_only=True):
        name = r[0]
        if not name or str(name).strip() in ("", "Provider Name"): continue
        cur[norm(name)] = {
            "name": str(name).strip(),
            "contracts": to_int(r[1]),
            "email": clean(r[3]) or clean(r[2]),
            "phone": clean(r[4]),
            "website": clean(r[5]),
            "hq": clean(r[6]),
            "notes": clean(r[7]),
        }
    wb.close()
    return cur

def primary_cat(cats):
    for p in PRIMARY_PREF:
        if p in cats: return p
    return sorted(cats)[0] if cats else "Housing"

def slugify(name):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")

# ── build ─────────────────────────────────────────────────────────────────────
wb = openpyxl.load_workbook(ENRICHED, read_only=True, data_only=True)
council_region, council_asylum = load_councils(wb)
place_region, place_county, county_abbrev, place_council = build_place_maps(council_region)
categories, contracts_raw = load_company_sector(wb, place_region, place_county, county_abbrev, place_council)

# Merge manual additions (curated CAS-2/3 rows etc) on top of the main load.
# Same company key (via norm()) → contract records append; new companies appear in
# their own Companies sheet inside manual_contracts.xlsx and get merged in pass 1.
extra_cats, extra_contracts, wb_manual = load_manual_additions(
    place_region, place_county, county_abbrev, place_council
)
for k, cats_set in extra_cats.items():
    categories.setdefault(k, set()).update(cats_set)
for k, recs in extra_contracts.items():
    contracts_raw.setdefault(k, []).extend(recs)
if extra_contracts:
    print(f"manual additions: +{sum(len(v) for v in extra_contracts.values())} contract rows "
          f"across {len(extra_contracts)} companies")

ws = wb["Companies"]
hdr = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
ix = {h: i for i, h in enumerate(hdr)}
def G(r, name):
    i = ix.get(name)
    return r[i] if i is not None and i < len(r) else None

emp = load_employees()
curated = load_curated()

VALID_REGIONS = {
    "East Midlands","East of England","London","North East","North West",
    "South East","South West","West Midlands","Yorkshire & The Humber",
}

# ── pass 1: merge Companies rows by normalised name (the sheet has near-dupes) ─
def better(a, b):                    # prefer a non-empty / longer contact string
    return a if (a and len(a) >= len(b)) else (b or a)

merged = {}
n_total = 0
for r in ws.iter_rows(min_row=2, values_only=True):
    company = clean(G(r, "Company"))
    if not company: continue
    n_total += 1
    key = norm(company)
    if not key: continue
    m = merged.get(key)
    rec = {
        "company": company,
        "email": clean(G(r, "Email")),
        "contact_page": clean(G(r, "Contact Page")),
        "website": clean(G(r, "Website")),
        "phone": clean(G(r, "Telephone")),
        "address": clean(G(r, "Address")),
        "unverified": clean(G(r, "Website Review")).lower() == "needs review",
        "councils": set(c.strip() for c in clean(G(r, "All Councils")).split(";") if c.strip()),
        "housing": to_int(G(r, "Housing Contracts")) or 0,
        "homecare": to_int(G(r, "Homecare Contracts")) or 0,
        "total": to_int(G(r, "Total Contracts")) or 0,
        "is_sme": (clean(G(r, "Is SME")).lower() == "yes") if G(r, "Is SME") is not None else None,
        "charity_number": clean(G(r, "Charity Number")),
        "charity_income": clean(G(r, "Charity Income (GBP)")),
        "charity_status": clean(G(r, "Charity Status")),
        "charity_activities": clean(G(r, "Charity Activities")),
    }
    if not m:
        merged[key] = rec
    else:
        m["company"] = rec["company"] if len(rec["company"]) > len(m["company"]) else m["company"]
        for fld in ("email","contact_page","website","phone","address",
                    "charity_number","charity_income","charity_status","charity_activities"):
            m[fld] = better(m[fld], rec[fld])
        m["councils"] |= rec["councils"]
        m["housing"] = max(m["housing"], rec["housing"])
        m["homecare"] = max(m["homecare"], rec["homecare"])
        m["total"] = max(m["total"], rec["total"])
        m["unverified"] = m["unverified"] and rec["unverified"]   # verified if any row verified
        if m["is_sme"] is None: m["is_sme"] = rec["is_sme"]

# Merge any Companies rows from manual_contracts.xlsx (e.g. Mears Group). Same logic
# as the main loop — net-new companies become their own merged entry, existing keys
# get their contact info improved by `better()`.
if wb_manual is not None and "Companies" in wb_manual.sheetnames:
    ws_m = wb_manual["Companies"]
    hdr_m = [c.value for c in next(ws_m.iter_rows(min_row=1, max_row=1))]
    ix_m = {h: i for i, h in enumerate(hdr_m)}
    def Gm(r, name):
        i = ix_m.get(name); return r[i] if i is not None and i < len(r) else None
    for r in ws_m.iter_rows(min_row=2, values_only=True):
        company = clean(Gm(r, "Company"))
        if not company: continue
        key = norm(company)
        if not key: continue
        rec = {
            "company": company,
            "email": clean(Gm(r, "Email")), "contact_page": clean(Gm(r, "Contact Page")),
            "website": clean(Gm(r, "Website")), "phone": clean(Gm(r, "Telephone")),
            "address": clean(Gm(r, "Address")),
            "unverified": clean(Gm(r, "Website Review")).lower() == "needs review",
            "councils": set(c.strip() for c in clean(Gm(r, "All Councils")).split(";") if c.strip()),
            "housing": to_int(Gm(r, "Housing Contracts")) or 0,
            "homecare": to_int(Gm(r, "Homecare Contracts")) or 0,
            "total": to_int(Gm(r, "Total Contracts")) or 0,
            "is_sme": (clean(Gm(r, "Is SME")).lower() == "yes") if Gm(r, "Is SME") is not None else None,
            "charity_number": clean(Gm(r, "Charity Number")),
            "charity_income": clean(Gm(r, "Charity Income (GBP)")),
            "charity_status": clean(Gm(r, "Charity Status")),
            "charity_activities": clean(Gm(r, "Charity Activities")),
        }
        m = merged.get(key)
        if not m:
            merged[key] = rec
        else:
            # manual file's display name wins if the existing one is a generic
            # "X Limited" / "X Ltd" and the manual gives a more specific group/brand.
            existing_l = m["company"].lower()
            if (("limited" in existing_l or "ltd" in existing_l)
                and "limited" not in rec["company"].lower() and "ltd" not in rec["company"].lower()):
                m["company"] = rec["company"]
            # Manual contacts OVERRIDE main-source contacts when manual provides
            # a value. This lets us fix wrong-attribution cases (e.g. main source
            # tied "Moore Care Ltd" to moorevets.co.uk — manual entry corrects to
            # moorecare.co.uk and wins despite being shorter).
            for fld in ("email","contact_page","website","phone","address"):
                if rec[fld]: m[fld] = rec[fld]
                elif not m[fld]: m[fld] = rec[fld]
            m["councils"] |= rec["councils"]

# ── pass 2: build provider records ───────────────────────────────────────────
providers = []
seen_slugs = {}
n_homecare_only = n_unreachable = n_noncare = n_carefacility = n_homecareagency = 0
n_tender_text = n_blacklist_domain = n_directory = 0
n_hotel = n_construction = 0

def _domain_of(url):
    if not url: return ''
    import re as _re
    u = url.strip()
    if not _re.match(r'^https?://', u): u = 'https://' + u
    try:
        from urllib.parse import urlparse as _up
        h = _up(u).netloc.lower()
        return _re.sub(r'^www\.', '', h)
    except Exception:
        return ''

for key, m in merged.items():
    company = m["company"]
    cats = categories.get(key, set())

    # filter 0: drop placeholder / non-provider rows
    if JUNK_NAME.match(company.strip()):
        continue

    # filter 0z: MANUAL drop list — verified not-an-actual-supplier or
    # wrong-domain-no-real-contact. See data/MANUAL_DROP_LIST.json.
    if company.lower().strip() in MANUAL_DROP_LIST:
        continue

    # filter 0c: drop tender-document text fragments masquerading as supplier names
    # (e.g. "None awarded", "Please Note This Tender Resulted...", "Lot 1 Greenbrook")
    if TENDER_TEXT_NAME.match(company.strip()):
        n_tender_text += 1
        continue

    # filter 0d: drop rows whose website domain is blacklisted (hotel-booking,
    # generic directories, unrelated commercial sites). The website is the
    # only contact path we have for many of these; if it's nonsense, drop.
    _dom = _domain_of(m.get("website") or "")
    if _dom and _dom in BLACKLIST_DOMAINS:
        n_blacklist_domain += 1
        continue
    if _dom and DIRECTORY_DOMAINS.search(_dom):
        n_directory += 1
        continue

    # filter 0e: hotels / guesthouses / B&Bs — they run their own buildings,
    # don't lease in. Not landlord-prospects.
    if HOTEL_NAME.search(company):
        n_hotel += 1
        continue

    # filter 0f: building contractors / property maintenance — they work on
    # properties, don't operate them. Not landlord-prospects.
    if CONSTRUCTION_NAME.search(company):
        n_construction += 1
        continue

    # filter 0g: estate agents / property management / haulage. Not operators.
    if PROPERTY_MGMT_NAME.search(company) or HAULAGE_NAME.search(company):
        n_construction += 1   # bucket with construction for stats
        continue

    # filter 0a: drop individual care facilities (care homes / nursing homes /
    # residential homes / care centres). These ARE the facility — they don't
    # lease or buy property, so they're not landlord-prospect customers for
    # this site. Extra-care providers stay (they operate across schemes).
    if CARE_FACILITY_NAME.search(company) and not CARE_FACILITY_EXEMPT.search(company):
        n_carefacility += 1
        continue

    # filter 0a-2: drop homecare / domiciliary agencies by name pattern.
    # These visit clients in clients' existing homes — they aren't looking
    # for property to lease/buy. Even if they happen to hold one supported-
    # living contract, the provider's identity is delivery, not housing supply.
    # Exemption protects entities whose name says housing/supported-living too
    # (e.g. "Look Ahead Care and Support" — keep).
    if HOMECARE_NAME.search(company) and not HOMECARE_EXEMPT.search(company):
        n_homecareagency += 1
        continue
    # Also catch via email/website domain — some homecare agencies have
    # generic names ("Lifestyle Care Support") but their email/site domain
    # contains "homecare" (e.g. lifestyle-homecare.co.uk).
    em = (m.get("email") or "")
    ws = (m.get("website") or "")
    if HOMECARE_NAME.search(em) or HOMECARE_NAME.search(ws):
        if not HOMECARE_EXEMPT.search(company):
            n_homecareagency += 1
            continue

    # filter 0b: drop facilities-management / construction / staffing / non-care firms.
    # By name (unambiguous), or if EVERY contract they hold is a facilities/works contract.
    recs = contracts_raw.get(key, [])
    hrecs = [r for r in recs if rec_is_housing(r)]   # contracts where housing is part of the deal
    full_titles = [t.strip() for rec in recs
                   for t in re.split(r"\s*;\s*", rec["titles"]) if t.strip()]
    soft_noncare = NONCARE_SOFT.search(company) and not CARE_EXEMPT.search(company)
    if (NONCARE_NAME.search(company) or soft_noncare
            or (full_titles and all(is_junk_title(t) for t in full_titles))):
        n_noncare += 1
        continue

    # filter 1: housing-led — must hold housing contracts, and housing must be at
    # least as significant as homecare (drops homecare-dominant agencies). In-network
    # curated contacts are always kept if they have any housing footprint.
    h, hc = m["housing"], m["homecare"]
    cur_keep = key in curated and (h > 0 or bool(cats & HOUSING_CATS))
    if not (cur_keep or (h > 0 and h >= hc)):
        n_homecare_only += 1
        continue
    # and they must actually hold at least one housing-relevant contract
    if not hrecs:
        n_homecare_only += 1
        continue

    # contacts (DB), possibly overridden by curated in-network record
    cur = curated.get(key)
    email   = m["email"]
    contact_page = m["contact_page"]
    website = m["website"]
    phone   = m["phone"]
    unverified = m["unverified"]
    if cur:
        email   = cur["email"] or email
        phone   = cur["phone"] or phone
        website = cur["website"] or website

    # filter 2: must be reachable
    reachable = bool(email) or bool(contact_page) or (bool(website) and not unverified)
    if not reachable:
        n_unreachable += 1
        continue

    # councils + regions — based ONLY on councils where they hold a housing contract
    councils = sorted({r["council"] for r in hrecs})
    regions = sorted({council_region.get(c, "") for c in councils} & VALID_REGIONS)

    housing_contracts = m["housing"]
    total_contracts   = m["total"]
    rank_contracts = (cur["contracts"] if cur and cur["contracts"] else None) or total_contracts

    # scope (derived)
    council_count = len(councils)
    if len(regions) >= 6 or council_count >= 40:
        scope = "National"
    elif len(regions) >= 2:
        scope = "Regional"
    else:
        scope = "Local"

    e = emp.get(key) or {}
    is_sme = m["is_sme"]

    charity = None
    if m["charity_number"] or m["charity_status"]:
        charity = {
            "number": m["charity_number"],
            "income": m["charity_income"],
            "status": m["charity_status"],
            "activities": m["charity_activities"],
        }

    display_name = cur["name"] if cur else title_case_company(company)
    slug = slugify(display_name) or slugify(company)
    if slug in seen_slugs:                     # keep names unique-ish for React keys
        seen_slugs[slug] += 1; slug = f"{slug}-{seen_slugs[slug]}"
    else:
        seen_slugs[slug] = 0

    description = ""
    if charity and charity["activities"]:
        description = charity["activities"]
    elif cur and cur["notes"]:
        description = cur["notes"]

    # Verification tier — Verified (passed 4-step check) vs Listed (on framework only)
    _vinfo = VERIFIED_MAP.get(display_name.lower().strip())
    verification = {
        "tier":         "Verified" if _vinfo else "Listed",
        "verified":     bool(_vinfo),
        "verified_at":  (_vinfo or {}).get("verified_at", ""),
        "services":     (_vinfo or {}).get("services", ""),
    }

    providers.append({
        "id": slug,
        "name": display_name,
        "website": website,
        "website_unverified": unverified,
        "verification": verification,
        "email": email,
        "contact_page": contact_page,
        "phone": phone,
        "regions": regions,
        "councils": councils,
        "council_count": council_count,
        "scope": scope,
        "employees": e.get("employees"),
        "employee_confidence": e.get("confidence", ""),
        "sector": sorted(cats),
        "primary_cat": primary_cat(cats),
        "client_groups": client_groups_of(full_titles, cats),
        "is_housing_association": is_housing_assoc(display_name),
        "description": description,
        "notes": (cur["notes"] if cur else ""),
        "hq_address": (cur["hq"] if cur and cur["hq"] else m["address"]),
        "contracts": rank_contracts,
        "housing_contracts": housing_contracts,
        "total_contracts": total_contracts,
        "contracts_list": strip_fm_titles(build_contracts_list(hrecs, company)),
        "is_sme": is_sme,
        "in_network": bool(cur),
        "charity": charity,
    })

wb.close()

# in-network first, then by contracts, then employees
providers.sort(key=lambda p: (
    not p["in_network"],
    -(p["contracts"] or 0),
    -(p["employees"] or 0),
))

# ── db.json index (server-side) ──────────────────────────────────────────────
# db maps council/region → ordered list of provider IDs (and a national list).
# Every provider is listed under each council/region it holds a contract with —
# including national ones — so a UK-wide provider with a contract in THIS council
# surfaces in the council tier. The engine dedups council > region > national.
by_id = {p["id"]: p for p in providers}
db = {"c": {}, "county": {}, "r": {}, "n": []}
seen_nat = set()
for p in providers:
    clist = p["contracts_list"]
    # LOCAL: a contract directly with the council
    for council in p["councils"]:
        db["c"].setdefault(council, []).append(p["id"])
    # COUNTY: a county-council framework (covers the whole county)
    counties = {e["county"] for e in clist if e.get("scope") == "County" and e.get("county")}
    for cty in counties:
        db["county"].setdefault(cty, []).append(p["id"])
    # REGIONAL: a genuinely Regional-scope contract in that region
    reg_regions = {e["region"] for e in clist if e.get("scope") == "Regional" and e.get("region")}
    for reg in reg_regions:
        db["r"].setdefault(reg, []).append(p["id"])
    # NATIONAL: a National-scope contract
    if any(e.get("scope") == "National" for e in clist) and p["id"] not in seen_nat:
        db["n"].append(p["id"]); seen_nat.add(p["id"])

contracts_of = lambda i: by_id[i]["contracts"] or 0
db["n"].sort(key=contracts_of, reverse=True)
for grp in ("county", "r", "c"):
    for k in db[grp]: db[grp][k].sort(key=contracts_of, reverse=True)

# ── complete council normalisation map (every council with contracts) ─────────
councilmap = {}
for k in db["c"]:
    nk = norm_council_js(k)
    if nk:
        councilmap.setdefault(nk, [])
        if k not in councilmap[nk]: councilmap[nk].append(k)

# ── write server-only data (api/_data) ───────────────────────────────────────
with open(os.path.join(OUT,"providers.json"),"w",encoding="utf-8") as f:
    json.dump(providers, f, ensure_ascii=False, separators=(",",":"))
with open(os.path.join(OUT,"db.json"),"w",encoding="utf-8") as f:
    json.dump(db, f, ensure_ascii=False, separators=(",",":"))
with open(os.path.join(OUT,"councilmap.json"),"w",encoding="utf-8") as f:
    json.dump(councilmap, f, ensure_ascii=False, separators=(",",":"))

# ── write public aggregate-safe stats (no names / contacts) ───────────────────
# distinct supported-living / social-housing contracts processed across the dataset
_contract_titles = set()
for p in providers:
    for row in (p.get("contracts_list") or []):
        for t in (row.get("titles") or []):
            if t and t.strip():
                _contract_titles.add(t.strip())
stats = {
    "providers": len(providers),
    "councils": len({c for p in providers for c in p["councils"]}),
    "regions": len({r for p in providers for r in p["regions"]}),
    "in_network": sum(1 for p in providers if p["in_network"]),
    "contracts": len(_contract_titles),
}
with open(os.path.join(PUB,"stats.json"),"w",encoding="utf-8") as f:
    json.dump(stats, f)

# ── LHA rates by council (server-side; public data, surfaced via the API) ─────
lha = load_lha()
with open(os.path.join(OUT,"lha.json"),"w",encoding="utf-8") as f:
    json.dump(lha, f, ensure_ascii=False)
print(f"LHA councils: {len(lha)}  | providers with client groups: "
      f"{sum(1 for p in providers if p['client_groups'])}  | housing associations: "
      f"{sum(1 for p in providers if p['is_housing_association'])}")

# ── remove any stale public copies of the gated data ──────────────────────────
for stale in ("providers.json", "db.json"):
    sp = os.path.join(PUB, stale)
    if os.path.exists(sp): os.remove(sp)

in_net = stats["in_network"]
withcontact = sum(1 for p in providers if p["email"] or p["contact_page"])
print(f"scanned: {n_total}  dropped homecare-only: {n_homecare_only}  "
      f"dropped non-care/FM: {n_noncare}  dropped care-facility: {n_carefacility}  "
      f"dropped homecare-agency: {n_homecareagency}  "
      f"dropped hotel: {n_hotel}  dropped construction: {n_construction}  "
      f"dropped tender-text: {n_tender_text}  "
      f"dropped blacklist-domain: {n_blacklist_domain}  "
      f"dropped directory-domain: {n_directory}  "
      f"dropped unreachable: {n_unreachable}")
print(f"PROVIDERS KEPT: {len(providers)}  (in-network: {in_net})")
print(f"national: {len(db['n'])}  regions: {len(db['r'])}  councils: {len(db['c'])}")
print(f"with email/contact-page: {withcontact}  unverified-website: {sum(1 for p in providers if p['website_unverified'])}")
sz = lambda n: f"{os.path.getsize(os.path.join(OUT,n))/1024:.0f}KB"
print(f"api/_data/providers.json {sz('providers.json')}  db.json {sz('db.json')}  (server-only)")
print("\nTop 8 (in-network first):")
for p in providers[:8]:
    print(f"  {'★' if p['in_network'] else ' '} {p['contracts'] or 0:>4}  {p['name'][:32]:32} {p['scope']:9} {p['primary_cat']}")
