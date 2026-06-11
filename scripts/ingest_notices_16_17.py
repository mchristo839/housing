"""Cross-check two new CSVs against current DB, ingest only missing pairs.

Same rules:
  - Only housing notices
  - Citation-backed per (supplier x council) pair
  - Joint-commissioner multi-council fanout
  - Skip if (supplier x council) already in DB
"""
import csv, re, openpyxl, json
from pathlib import Path
from collections import defaultdict

CSVs = [r'C:\Users\paul_\Downloads\notices (16).csv',
        r'C:\Users\paul_\Downloads\notices (17).csv']
MANUAL_XLSX = 'data/manual_contracts.xlsx'

def parse_suppliers(s):
    if not s: return []
    out = []
    for b in re.split(r'\]\s*\[', s.strip().strip('[]')):
        parts = [p.strip() for p in b.split('|')]
        if not parts or not parts[0]: continue
        addr = re.sub(r'\s+', ' ', parts[1] if len(parts) > 1 else '').strip(', ')
        out.append({
            'name': re.sub(r'\s+', ' ', parts[0]).strip(),
            'addr': addr,
            'ch':   parts[3].strip() if len(parts) > 3 else '',
            'sme':  (parts[4].strip().lower() == 'yes') if len(parts) > 4 else None,
            'vcse': (parts[5].strip().lower() == 'yes') if len(parts) > 5 else None,
        })
    return out

def is_housing(row):
    title = (row.get('Title') or '').lower()
    HOUSING = ('supported living', 'supported accommodation', 'supported housing',
               'learning disabilit', 'autism', 'mental health', 'community supported',
               'community based', 'enablement', 'complex', 'placements', 'accommodation',
               'leaving care', 'homelessness', 'rough sleeping', 'extra care',
               'shared lives', 'community support', 'independent living')
    NON_HOUSING = ('reablement', 'transport only', 'training only', 'equipment',
                   'live in care only', 'home care only')
    return any(h in title for h in HOUSING) and not any(n in title for n in NON_HOUSING)

REGION_MAP = {
    'east of england': 'East of England', 'east midlands': 'East Midlands',
    'london': 'London', 'north east': 'North East', 'north west': 'North West',
    'south east': 'South East', 'south west': 'South West',
    'west midlands': 'West Midlands', 'yorkshire and the humber': 'Yorkshire & The Humber',
}

PORTAL_ORG_MAP = {
    'IN-TEND LIMITED': 'Hertfordshire County Council',
    'EU SUPPLY LIMITED': None,
    'ONESOURCE PARTNERSHIP LTD': 'London Borough of Havering',
    'CAPITAL ESOURCING C.I.C.': 'Royal Borough of Kensington and Chelsea',
    'CAPITAL ESOURCING': 'Royal Borough of Kensington and Chelsea',
    'NEPRO SOLUTIONS LIMITED': None,
    'PCR PLUS LIMITED': None,
}

JOINT_PATTERNS = [
    (re.compile(r'(Bristol(?:, |/| and )?North Somerset(?:, | and )?South Gloucestershire|BNSSG)', re.I),
     [('Bristol City Council', 'South West'),
      ('North Somerset Council', 'South West'),
      ('South Gloucestershire Council', 'South West')]),
    (re.compile(r'Hampshire (?:and|&) Isle of Wight Integrated Care Board|Hampshire (?:and|&) IoW', re.I),
     [('Hampshire County Council', 'South East'),
      ('Isle of Wight Council', 'South East')]),
    (re.compile(r'(?:Cumberland (?:and|&) Westmorland|Westmorland (?:and|&) Furness)', re.I),
     [('Cumberland Council', 'North West'),
      ('Westmorland and Furness Council', 'North West')]),
    (re.compile(r'Tees Valley', re.I),
     [('Hartlepool Borough Council', 'North East'),
      ('Stockton-on-Tees Borough Council', 'North East'),
      ('Middlesbrough Council', 'North East'),
      ('Redcar & Cleveland Borough Council', 'North East'),
      ('Darlington Borough Council', 'North East')]),
]

all_contracts = []
total_kept = total_skip = 0
for csv_path in CSVs:
    print(f"\n=== {Path(csv_path).name} ===")
    with open(csv_path, encoding='utf-8-sig', errors='replace') as f:
        rows = list(csv.DictReader(f))
    print(f"  {len(rows)} notices")
    n_kept = n_skip = 0
    for row in rows:
        nid = (row.get('Notice Identifier') or '').strip()
        if not nid:
            n_skip += 1; continue
        if not is_housing(row):
            n_skip += 1; continue

        org = row.get('Organisation Name', '').strip()
        title = row.get('Title', '').strip()
        region_raw = (row.get('Region') or '').lower().strip()
        region = REGION_MAP.get(region_raw, '')

        # Map portal/agency org to actual buyer
        council = org
        for portal, real in PORTAL_ORG_MAP.items():
            if portal in org.upper():
                council = real
                break
        if council is None:
            n_skip += 1; continue

        # Standardise
        council = re.sub(r'\bCOUNCIL\b', 'Council', council, flags=re.I)
        council = re.sub(r'^WAKEFIELD COUNCIL$', 'Wakefield Council', council)
        council = re.sub(r'^HAMPSHIRE COUNTY COUNCIL$', 'Hampshire County Council', council)

        suppliers = parse_suppliers(row.get('Supplier [Name|Address|Ref type|Ref Number|Is SME|Is VCSE]', '') or '')
        if not suppliers:
            n_skip += 1; continue

        awd = row.get('Awarded Date', '')
        val = row.get('Awarded Value', '')
        desc = (row.get('Description', '') or '') + ' ' + title

        joint_councils = []
        for rx, cs in JOINT_PATTERNS:
            if rx.search(desc):
                joint_councils.extend(cs)

        for sup in suppliers:
            if not sup['name'] or sup['name'].lower() in {'none', 'na', 'tbc'}:
                continue
            citation = (f"{title[:80]} - {council}. "
                        f"Awarded {awd}. Value GBP {val}. "
                        f"Notice {nid[:30]}.")
            all_contracts.append({
                'company': sup['name'], 'council': council, 'region': region,
                'title': citation, 'address': sup['addr'], 'ch': sup['ch'],
                'is_sme': sup['sme'], 'is_vcse': sup['vcse'], 'notice': nid,
            })
            for (cn, reg) in joint_councils:
                if cn == council: continue
                all_contracts.append({
                    'company': sup['name'], 'council': cn, 'region': reg,
                    'title': citation + ' (joint commissioner)',
                    'address': sup['addr'], 'ch': sup['ch'],
                    'is_sme': sup['sme'], 'is_vcse': sup['vcse'], 'notice': nid,
                })
        n_kept += 1
    print(f"  kept {n_kept} housing notices, skipped {n_skip}")
    total_kept += n_kept
    total_skip += n_skip

print(f"\n=== Total extracted: {len(all_contracts)} (supplier x council) ===")

# Compare against current DB
prov = json.load(open('api/_data/providers.json', encoding='utf-8'))

def norm(name):
    n = (name or '').lower().strip()
    n = re.sub(r'\b(ltd|limited|llp|plc|company|co)\b', '', n)
    n = re.sub(r'[^a-z0-9 ]', ' ', n)
    return ' '.join(n.split())

existing_pairs = set()
for p in prov:
    nm = norm(p['name'])
    for c in (p.get('contracts_list') or []):
        existing_pairs.add((nm, norm(c.get('council', ''))))

new_pairs = []
existing_count = 0
for c in all_contracts:
    if (norm(c['company']), norm(c['council'])) in existing_pairs:
        existing_count += 1
    else:
        new_pairs.append(c)

print(f"Of the extracted:")
print(f"  Already in DB:    {existing_count}")
print(f"  NEW to be added:  {len(new_pairs)}\n")

new_by_council = defaultdict(int)
for c in new_pairs:
    new_by_council[c['council']] += 1
print("Top councils gaining new suppliers:")
for c, n in sorted(new_by_council.items(), key=lambda x: -x[1])[:15]:
    print(f"  {c[:48]:<50s}  +{n}")

# Write new
wb = openpyxl.load_workbook(MANUAL_XLSX)
companies = wb['Companies']
ccs = wb['Company x Council x Sector'] if 'Company x Council x Sector' in wb.sheetnames \
       else wb['Company × Council × Sector']

existing_companies = set()
for r in range(2, companies.max_row + 1):
    v = (companies.cell(row=r, column=1).value or '').strip().lower()
    if v: existing_companies.add(v)

supplier_addresses = {}
for c in new_pairs:
    nl = c['company'].lower().strip()
    if nl not in supplier_addresses and c['address']:
        supplier_addresses[nl] = c

n_co = 0
for nl, c in supplier_addresses.items():
    if nl in existing_companies: continue
    if len(nl) < 3 or nl in {'none', 'na', 'tbc'}: continue
    nr = companies.max_row + 1
    companies.cell(row=nr, column=1).value  = c['company']
    companies.cell(row=nr, column=2).value  = 0
    companies.cell(row=nr, column=5).value  = 1
    companies.cell(row=nr, column=7).value  = 'No'
    companies.cell(row=nr, column=8).value  = c['ch']
    companies.cell(row=nr, column=9).value  = 'Yes' if c['is_sme'] else ('No' if c['is_sme'] is False else None)
    companies.cell(row=nr, column=10).value = 'Yes' if c['is_vcse'] else ('No' if c['is_vcse'] is False else None)
    companies.cell(row=nr, column=12).value = c['address']
    existing_companies.add(nl)
    n_co += 1

n_ccs = 0
for c in new_pairs:
    nr = ccs.max_row + 1
    ccs.cell(row=nr, column=1).value  = c['company']
    ccs.cell(row=nr, column=2).value  = 'Housing'
    ccs.cell(row=nr, column=3).value  = c['council']
    ccs.cell(row=nr, column=4).value  = 1
    ccs.cell(row=nr, column=9).value  = 'Yes' if c['is_sme'] else ('No' if c['is_sme'] is False else None)
    ccs.cell(row=nr, column=10).value = 'Yes' if c['is_vcse'] else ('No' if c['is_vcse'] is False else None)
    ccs.cell(row=nr, column=11).value = 'Supported living | Learning disability | Mental health'
    ccs.cell(row=nr, column=13).value = c['title']
    ccs.cell(row=nr, column=14).value = c['region']
    ccs.cell(row=nr, column=15).value = 'Local Authority'
    ccs.cell(row=nr, column=16).value = 'Local'
    n_ccs += 1

wb.save(MANUAL_XLSX)
print(f"\nAdded: {n_co} Companies entries, {n_ccs} CCS rows")
