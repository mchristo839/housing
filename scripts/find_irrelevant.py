"""Scan the live universe for suppliers that don't fit the landlord-prospect
profile, even though they have a contract:
  - Hotels / guesthouses / B&Bs (operate own buildings, don't lease in)
  - Recruitment / staffing agencies (deliver people, not property)
  - Training-only providers
  - Construction / property maintenance contractors (work on properties, not operators)
  - Generic consultancies
  - Bid-writing / advisory companies
"""
import json, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

prov = json.load(open('api/_data/providers.json', encoding='utf-8'))

# Pattern groups
HOTEL = re.compile(
    r"\b(?:hotel(?:s)?|guest ?house(?:s)?|guesthouse(?:s)?|"
    r"travelodge|premier ?inn|b ?and ?b|bed and breakfast|"
    r"inn(?: hotel)?|lodge hotel)\b", re.I)

RECRUITMENT = re.compile(
    r"\b(?:recruitment|staffing agency|employment agency|workforce solutions|"
    r"locum agency|agency staffing)\b", re.I)

TRAINING_ONLY = re.compile(
    r"\b(?:training (?:and|&) skills|training services|skills training|"
    r"academy of |college of |learning solutions|education solutions)\b", re.I)

CONSTRUCTION = re.compile(
    r"\b(?:construction(?: services| group)?|building contractor|"
    r"property maintenance|maintenance (?:services|contractor)|"
    r"refurbishment|civil engineering|plant hire)\b", re.I)

CONSULTANCY = re.compile(
    r"\b(?:consultancy services|consultancy ltd$|consultants ltd$|"
    r"advisory services|management consultancy|bid (?:writing|consultancy))\b", re.I)

SAFE_EXEMPT = re.compile(
    r"\bsupported (?:living|housing|accommodation)|housing association|"
    r"housing trust|housing group|extra care|care leaver|"
    r"young people|mental health|learning disab", re.I)

def primary_text(p):
    return ' '.join([
        p.get('name',''), p.get('description','') or '',
        ' '.join(p.get('sector') or []),
        ' '.join(str(c.get('titles','')) for c in (p.get('contracts_list') or []))
    ])

candidates = {'hotel': [], 'recruitment': [], 'training-only': [],
              'construction': [], 'consultancy': []}

for p in prov:
    blob = primary_text(p)
    if SAFE_EXEMPT.search(blob):  # safe — has clear housing-provider signal somewhere
        # but still flag hotels by name override (a real hotel will say "Hotel" in name)
        if HOTEL.search(p.get('name','')):
            candidates['hotel'].append(p['name'])
        continue
    if HOTEL.search(p.get('name','')):     candidates['hotel'].append(p['name'])
    if RECRUITMENT.search(blob):           candidates['recruitment'].append(p['name'])
    if TRAINING_ONLY.search(p.get('name','')): candidates['training-only'].append(p['name'])
    if CONSTRUCTION.search(p.get('name','')):  candidates['construction'].append(p['name'])
    if CONSULTANCY.search(p.get('name','')):   candidates['consultancy'].append(p['name'])

print(f"Total providers: {len(prov)}\n")
for cat, hits in candidates.items():
    if not hits: continue
    hits = sorted(set(hits))
    print(f"=== {cat.upper()} ({len(hits)}) ===")
    for n in hits[:50]:
        print(f"  {n}")
    if len(hits) > 50:
        print(f"  ... +{len(hits)-50} more")
    print()

# Also: look for very short / cryptic names that probably aren't real
SHORT_OR_CRYPTIC = []
for p in prov:
    n = p.get('name','').strip()
    if len(n) <= 4 and not re.match(r'^[A-Z][a-z]+$', n):  # all-caps short names
        SHORT_OR_CRYPTIC.append(n)
    if re.match(r'^[a-z\s]+$', n):  # all-lowercase
        SHORT_OR_CRYPTIC.append(n)
if SHORT_OR_CRYPTIC:
    print(f"=== SHORT/CRYPTIC NAMES ({len(SHORT_OR_CRYPTIC)}) ===")
    for n in sorted(set(SHORT_OR_CRYPTIC))[:30]:
        print(f"  '{n}'")
