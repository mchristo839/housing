"""Produce three subset CSVs alongside the master SUPPLIERS_FOR_CLAY.csv:
   1. SUPPLIERS_LONDON_FOR_CLAY.csv     — only providers with a London Local contract
   2. SUPPLIERS_NETNEW_FOR_CLAY.csv     — only providers we discovered this session (not in main DB)
   3. SUPPLIERS_INNETWORK_FOR_CLAY.csv  — only the 53 in-network priority providers
"""
import json, csv, sys, io, re, openpyxl
from urllib.parse import urlparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

OUT_DIR = 'data/scraped'

def norm(s):
    return re.sub(r'[^a-z0-9]', '', str(s or '').lower())

def extract_domain(url):
    if not url: return ''
    url = url.strip()
    if not re.match(r'^https?://', url): url = 'https://' + url
    try: host = urlparse(url).netloc.lower()
    except Exception: return ''
    return re.sub(r'^(www\.|m\.)', '', host)

prov = json.load(open('api/_data/providers.json', encoding='utf-8'))
db   = json.load(open('api/_data/db.json',        encoding='utf-8'))
m    = json.load(open('api/_data/councilmap.json', encoding='utf-8'))

# London council keys (postcodes.io admin_district names)
LONDON_BOROUGHS = ['Barking and Dagenham','Barnet','Bexley','Brent','Bromley',
    'Camden','City of London','Croydon','Ealing','Enfield','Greenwich','Hackney',
    'Hammersmith and Fulham','Haringey','Harrow','Havering','Hillingdon','Hounslow',
    'Islington','Kensington and Chelsea','Kingston upon Thames','Lambeth','Lewisham',
    'Merton','Newham','Redbridge','Richmond upon Thames','Southwark','Sutton',
    'Tower Hamlets','Waltham Forest','Wandsworth','Westminster']

def norm_council(name):
    n = name.lower().strip().replace('&', ' and ')
    n = re.sub(r',\s*city of$', ' city', n)
    n = re.sub(r'^city of london corporation$', 'city of london', n)
    n = re.sub(r'^(?:the\s+)?(?:london borough of|royal borough of)\s+', '', n)
    n = re.sub(r'\b(council|metropolitan borough|borough|county|district|unitary authority|mbc|lbc|the )\b', ' ', n)
    if n != 'city of london' and not n.startswith('city of london '):
        n = re.sub(r'\bcity\b', ' ', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    return re.sub(r'\s+', ' ', n).strip()

# Build London-supplier set (anyone with a Local contract in a London borough)
london_ids = set()
for b in LONDON_BOROUGHS:
    nk = norm_council(b)
    for key in m.get(nk, []):
        london_ids.update(db['c'].get(key, []))

# Build net-new supplier set (in providers.json but NOT in original main DB)
wb_main = openpyxl.load_workbook('data/care_housing_database_v2_ENRICHED.xlsx',
                                  read_only=True, data_only=True)
main_suppliers = set()
for r in wb_main['Company × Council × Sector'].iter_rows(min_row=2, values_only=True):
    if r[0]: main_suppliers.add(norm(r[0]))
for r in wb_main['Companies'].iter_rows(min_row=2, values_only=True):
    if r[0]: main_suppliers.add(norm(r[0]))

# Hydrate each provider into a row
def to_row(p):
    sectors = p.get('sector') or []
    if isinstance(sectors, str): sectors = [sectors]
    councils, regions = [], set()
    for c in (p.get('contracts_list') or []):
        cn = c.get('council','')
        if cn and cn not in councils: councils.append(cn)
        if c.get('region'): regions.add(c['region'])
    return {
        'company_name':     p.get('name',''),
        'domain':           extract_domain(p.get('website') or ''),
        'website_url':      (p.get('website') or '').strip(),
        'email':            (p.get('email') or '').strip(),
        'phone':            (p.get('phone') or '').strip(),
        'primary_category': p.get('primary_cat',''),
        'sectors':          ' | '.join(sectors[:8]),
        'in_network':       'yes' if p.get('in_network') else '',
        'total_contracts':  p.get('contracts') or 0,
        'councils_count':   len(councils),
        'councils_top':     ' | '.join(councils[:5]),
        'regions':          ' | '.join(sorted(regions)),
        'tier_hint':        p.get('scope') or '',
    }

FIELDS = ['company_name','domain','website_url','email','phone','primary_category',
          'sectors','in_network','total_contracts','councils_count','councils_top',
          'regions','tier_hint']

# ─── Subset 1: London ─────────────────────────────────────────────────────
london_rows = [to_row(p) for p in prov if p['id'] in london_ids]
london_rows.sort(key=lambda r: (0 if r['domain'] else 1, r['company_name'].lower()))
with open(f'{OUT_DIR}/SUPPLIERS_LONDON_FOR_CLAY.csv', 'w', newline='',
          encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader()
    for r in london_rows: w.writerow(r)
print(f"SUPPLIERS_LONDON_FOR_CLAY.csv     : {len(london_rows)} suppliers "
      f"({sum(1 for r in london_rows if r['domain'])} with domain)")

# ─── Subset 2: Net-new ────────────────────────────────────────────────────
netnew_rows = [to_row(p) for p in prov if norm(p['name']) not in main_suppliers]
netnew_rows.sort(key=lambda r: (0 if r['domain'] else 1, r['company_name'].lower()))
with open(f'{OUT_DIR}/SUPPLIERS_NETNEW_FOR_CLAY.csv', 'w', newline='',
          encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader()
    for r in netnew_rows: w.writerow(r)
print(f"SUPPLIERS_NETNEW_FOR_CLAY.csv     : {len(netnew_rows)} suppliers "
      f"({sum(1 for r in netnew_rows if r['domain'])} with domain)")

# ─── Subset 3: In-network ─────────────────────────────────────────────────
innet_rows = [to_row(p) for p in prov if p.get('in_network')]
innet_rows.sort(key=lambda r: -r['total_contracts'])
with open(f'{OUT_DIR}/SUPPLIERS_INNETWORK_FOR_CLAY.csv', 'w', newline='',
          encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader()
    for r in innet_rows: w.writerow(r)
print(f"SUPPLIERS_INNETWORK_FOR_CLAY.csv  : {len(innet_rows)} suppliers "
      f"({sum(1 for r in innet_rows if r['domain'])} with domain)")

# ─── Combined intersections ───────────────────────────────────────────────
ln_set = {r['company_name'].lower() for r in london_rows}
nn_set = {r['company_name'].lower() for r in netnew_rows}
in_set = {r['company_name'].lower() for r in innet_rows}
print(f"\nCross-tabulations:")
print(f"  London ∩ Net-new       : {len(ln_set & nn_set)}")
print(f"  London ∩ In-network    : {len(ln_set & in_set)}")
print(f"  Net-new ∩ In-network   : {len(nn_set & in_set)}")
print(f"  London ∩ Net-new ∩ In  : {len(ln_set & nn_set & in_set)}")
