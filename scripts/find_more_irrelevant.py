"""Scan the 1,930 live providers for the remaining categories that may not
fit the landlord-prospect profile:
   - Recruitment / staffing agencies (deliver people, not property)
   - Training providers (deliver courses, not housing operations)
   - IT / software / tech consultancies
   - Legal / financial / professional services
   - Property management / letting agents (manage existing portfolios, don't operate)
   - Catering / cleaning / FM (services into properties)
   - Transport / logistics
   - Energy / utilities
   - Generic services consultancies
"""
import json, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

prov = json.load(open('api/_data/providers.json', encoding='utf-8'))

# A "supported-housing exempt" pattern — providers who clearly belong despite
# having one of the keywords below (e.g. "Look Ahead Care and Support")
SAFE = re.compile(
    r"\bsupported (?:living|housing|accommodation)|"
    r"housing association|housing trust|housing group|housing limited|"
    r"extra care|care leaver|young people|asylum|"
    r"mental health (?:support|services|services ltd)|"
    r"learning disab|autism|domestic abuse|refuge|"
    r"homeless|rough sleep|"
    r"care and support|support and care|"
    r"social care(?: services| ltd)?$|care services ltd$",
    re.I)

PATTERNS = {
    'recruitment / staffing': re.compile(
        r"\b(?:"
        r"recruitment(?:\s+(?:ltd|limited|services|group|agency))?|"
        r"staffing(?:\s+(?:ltd|limited|services|solutions|agency))?|"
        r"workforce(?:\s+solutions)?|"
        r"locum agency|temporary staffing|agency staff|"
        r"talent (?:solutions|agency)|"
        r"hr solutions|payroll services"
        r")\b", re.I),

    'training / courses': re.compile(
        r"\b(?:"
        r"training(?:\s+(?:ltd|limited|services|solutions|group|academy))?|"
        r"academy of |college of |"
        r"learning solutions|education solutions|"
        r"skills (?:training|development)|"
        r"qualifications? services|qcf|"
        r"awarding (?:body|organisation)"
        r")\b", re.I),

    'IT / software / tech': re.compile(
        r"\b(?:"
        r"it services(?:\s+(?:ltd|limited))?|"
        r"software(?:\s+(?:ltd|limited|solutions|services))?|"
        r"technology services|technology solutions|"
        r"telecoms|telecommunications|"
        r"saas|"
        r"digital (?:solutions|services|agency)|"
        r"data services|data solutions|"
        r"systems integrator"
        r")\b", re.I),

    'legal / financial / professional': re.compile(
        r"\b(?:"
        r"solicitors(?:\s+(?:ltd|llp))?|legal services|law firm|"
        r"chartered accountants|accountancy|accountants(?:\s+(?:ltd|llp))?|"
        r"insurance (?:brokers?|services|ltd)|insurance group|"
        r"audit services|tax services|"
        r"actuarial|underwriting|"
        r"bid writing|bid management"
        r")\b", re.I),

    'property mgmt / letting agents': re.compile(
        r"\b(?:"
        r"letting agents?|estate agents?|"
        r"property management(?:\s+(?:ltd|limited|services))?|"
        r"property services(?: ltd)?|"
        r"property investment|property portfolio|"
        r"asset management(?: ltd)?|"
        r"facilities management|fm services"
        r")\b", re.I),

    'catering / cleaning / FM': re.compile(
        r"\b(?:"
        r"catering(?:\s+(?:ltd|limited|services|company))?|"
        r"cleaning(?:\s+(?:ltd|limited|services|company))?|"
        r"laundry services|"
        r"facilities management|hard fm|soft fm|"
        r"grounds maintenance|landscaping|"
        r"waste management|recycling services"
        r")\b", re.I),

    'transport / logistics': re.compile(
        r"\b(?:"
        r"transport (?:ltd|limited|services|solutions|group)|"
        r"logistics(?:\s+(?:ltd|limited|services|solutions))?|"
        r"haulage|haulier|"
        r"taxi services|minibus|coach hire|"
        r"removals(?:\s+(?:ltd|limited))?|"
        r"courier services|delivery services|"
        r"freight(?: forwarding)?"
        r")\b", re.I),

    'energy / utilities': re.compile(
        r"\b(?:"
        r"energy (?:services|solutions|group|ltd|limited)|"
        r"utilities(?:\s+(?:ltd|limited|services))?|"
        r"power (?:services|solutions|ltd|limited)|"
        r"gas (?:services|ltd|limited)(?!\s*board)|"
        r"renewables|solar (?:services|ltd|limited)|"
        r"telecoms infrastructure"
        r")\b", re.I),

    'generic consultancy': re.compile(
        r"\b(?:"
        r"consultancy (?:ltd|limited|services|group)|"
        r"consultants(?:\s+(?:ltd|limited))?|"
        r"advisory (?:services|group|ltd|limited)|"
        r"management consultancy|"
        r"strategy consultants|business consulting"
        r")\b", re.I),
}

# Some safe overrides — these names look like consultancies/etc but are legit
KNOWN_LEGIT = {
    'expert link',                # lived-experience charity
    'capital letters',            # London Councils housing co
    'commissioning alliance',     # housing consortium
    'achieving for children',     # children's services
    'commissioning support unit', # NHS
}

hits_by_cat = {k: [] for k in PATTERNS}
for p in prov:
    name = (p.get('name') or '').strip()
    if name.lower() in KNOWN_LEGIT: continue
    blob = name + ' ' + ' '.join(p.get('sector') or [])
    if SAFE.search(blob): continue
    for cat, rx in PATTERNS.items():
        if rx.search(name):
            hits_by_cat[cat].append(name)
            break  # one cat per hit, to avoid double-print

total = 0
for cat, hits in hits_by_cat.items():
    if not hits: continue
    hits = sorted(set(hits))
    total += len(hits)
    print(f"\n=== {cat.upper()} ({len(hits)}) ===")
    for n in hits[:60]: print(f"  {n}")
    if len(hits) > 60: print(f"  ... +{len(hits)-60} more")

print(f"\n{'='*55}")
print(f"  Total flagged across all categories: {total}")
print(f"{'='*55}")
