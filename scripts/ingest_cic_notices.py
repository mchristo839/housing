"""Ingest the Community Integrated Care contracts CSV — 102 notices, ~1000+
supplier-mentions. Extract every (supplier × council) pair with citation.

Same rules as the previous ingest:
  - Skip non-housing notices
  - For procurement-portal notices, derive the actual buyer from the title/contact
  - All these notices are single-council frameworks, so treat as Local
  - Add new Companies entries for new suppliers with their CH-verified addresses
"""
import csv, re, openpyxl, json
from pathlib import Path
from collections import defaultdict

CSV_PATH = Path(r"C:\Users\paul_\Downloads\Community intergrated care contracts.csv")
MANUAL_XLSX = 'data/manual_contracts.xlsx'

with open(CSV_PATH, newline='', encoding='utf-8-sig', errors='replace') as f:
    rows = list(csv.DictReader(f))
print(f"Loaded {len(rows)} notice rows from CSV\n")

# Map procurement-portal notice IDs → actual commissioning council + region
PORTAL_REMAP = {
    'IT-285-8247-HCC2314888 - AWARD':       ('Hertfordshire County Council',     'East of England'),
    'CF-1653800D0O000000rwimUAA':           (None, None),                              # Health Education England — skip (non-housing)
    'LB Havering Complex Placements Frame': ('London Borough of Havering',       'London'),
    '20230519141505-103835':                ('City of Bradford Metropolitan District Council', 'Yorkshire & The Humber'),
    'C307872':                              ('North East Lincolnshire Council',  'Yorkshire & The Humber'),
}

# Notice IDs to SKIP entirely (non-housing or 0-supplier or duplicate)
SKIP = {
    'CF-1653800D0O000000rwimUAA',   # Health Education England funding to CIC, not commissioning
}

# Region normalisation (matches our internal ONS regions)
REGION_MAP = {
    'east of england': 'East of England',
    'east midlands': 'East Midlands',
    'london': 'London',
    'north east': 'North East',
    'north west': 'North West',
    'south east': 'South East',
    'south west': 'South West',
    'west midlands': 'West Midlands',
    'yorkshire and the humber': 'Yorkshire & The Humber',
    'yorkshire and the humber ': 'Yorkshire & The Humber',
    'england': '',
    'united kingdom': '',
    'any region': '',
}

def parse_suppliers(s):
    if not s: return []
    out = []
    blocks = re.split(r'\]\s*\[', s.strip().strip('[]'))
    for b in blocks:
        parts = [p.strip() for p in b.split('|')]
        if not parts or not parts[0]: continue
        # The address often contains \r\n inside the field — flatten
        addr = parts[1].strip() if len(parts) > 1 else ''
        addr = re.sub(r'\s+', ' ', addr).strip(', ')
        out.append({
            'name': re.sub(r'\s+', ' ', parts[0]).strip(),
            'addr': addr,
            'ch':   parts[3].strip() if len(parts) > 3 else '',
            'sme':  (parts[4].strip().lower() == 'yes') if len(parts) > 4 else None,
            'vcse': (parts[5].strip().lower() == 'yes') if len(parts) > 5 else None,
        })
    return out

def is_housing_notice(row):
    """Filter out clearly non-housing notices."""
    title = (row.get('Title') or '').lower()
    cpv   = (row.get('Cpv Codes') or '').lower()
    HOUSING_HINT = ('supported living', 'supported accommodation', 'supported housing',
                    'learning disabilit', 'autism', 'mental health',
                    'community living', 'community support', 'extra care',
                    'leaving care', 'care leaver', 'care framework',
                    'placements framework', 'accommodation framework',
                    'inclusive lives', 'enablement', 'complex placements',
                    'supported accommodation', 'community based support',
                    'shared lives', 'community integrated care')
    return any(h in title for h in HOUSING_HINT)

# Parse + collect
all_contracts = []
skipped_nonhousing = []
skipped_other = []

for row in rows:
    nid = (row.get('Notice Identifier') or '').strip()
    if not nid: continue
    if nid in SKIP:
        skipped_other.append((nid, 'in SKIP'))
        continue
    if not is_housing_notice(row):
        skipped_nonhousing.append((nid, row.get('Title','')[:60]))
        continue

    # Derive council
    org_raw = row.get('Organisation Name','').strip()
    title   = row.get('Title','').strip()
    region_raw = (row.get('Region') or '').lower().strip()
    region = REGION_MAP.get(region_raw, '')

    # Use portal remap if relevant
    if nid in PORTAL_REMAP:
        council, region_override = PORTAL_REMAP[nid]
        if council is None: continue                # skipped via remap
        if region_override: region = region_override
    else:
        # Most rows: org IS the council. Standardise some title-cases.
        council = org_raw
        # Common normalisations
        council = re.sub(r'\bCOUNCIL\b', 'Council', council, flags=re.I)
        council = re.sub(r'^WAKEFIELD COUNCIL$', 'Wakefield Council', council)
        council = re.sub(r'\bWAKEFIELD COUNCIL CUSTOMER SERVICE\b', 'Wakefield Council', council, flags=re.I)
        council = re.sub(r'^HAMPSHIRE COUNTY COUNCIL$', 'Hampshire County Council', council)
        council = re.sub(r'^DURHAM COUNTY COUNCIL$', 'Durham County Council', council)
        council = re.sub(r'^CITY OF BRADFORD METROPOLITAN DISTRICT COUNCIL$',
                        'City of Bradford Metropolitan District Council', council)

    suppliers = parse_suppliers(row.get('Supplier [Name|Address|Ref type|Ref Number|Is SME|Is VCSE]','') or '')
    if not suppliers:
        skipped_other.append((nid, 'no suppliers'))
        continue
    if not council:
        skipped_other.append((nid, 'no council derivable'))
        continue

    awarded = row.get('Awarded Date','') or ''
    val     = row.get('Awarded Value','') or ''
    end     = row.get('Contract end date','') or ''

    for sup in suppliers:
        if not sup['name'] or sup['name'].lower() in {'none','na','tbc'}: continue
        citation = (f"{title[:80]} — {council}. "
                    f"Awarded {awarded}. Value £{val}. "
                    f"Notice {nid[:30]}.")
        all_contracts.append({
            'company': sup['name'],
            'council': council,
            'region':  region,
            'title':   citation,
            'address': sup['addr'],
            'ch':      sup['ch'],
            'is_sme':  sup['sme'],
            'is_vcse': sup['vcse'],
            'notice':  nid,
        })

print(f"Notices: kept {len(rows)-len(skipped_nonhousing)-len(skipped_other)}, "
      f"skipped non-housing {len(skipped_nonhousing)}, skipped other {len(skipped_other)}")
print(f"Total (supplier × council) contracts extracted: {len(all_contracts)}\n")
print(f"=== Skipped non-housing (sample) ===")
for nid, t in skipped_nonhousing[:5]: print(f"  {nid[:30]:<32s}  {t}")
print(f"=== Skipped other ===")
for nid, r in skipped_other[:5]:        print(f"  {nid[:30]:<32s}  {r}")

# Now write
wb = openpyxl.load_workbook(MANUAL_XLSX)
companies = wb['Companies']
ccs = wb['Company × Council × Sector']

existing_companies = set()
for r in range(2, companies.max_row + 1):
    v = (companies.cell(row=r, column=1).value or '').strip().lower()
    if v: existing_companies.add(v)

# Pick one address per supplier (first non-empty seen)
supplier_addresses = {}
for c in all_contracts:
    nl = c['company'].lower().strip()
    if nl not in supplier_addresses and c['address']:
        supplier_addresses[nl] = c

n_new_companies = 0
for nl, c in supplier_addresses.items():
    if nl in existing_companies: continue
    if len(nl) < 3 or nl in {'none','na','tbc','fsip'}: continue
    next_row = companies.max_row + 1
    companies.cell(row=next_row, column=1).value  = c['company']
    companies.cell(row=next_row, column=2).value  = 0
    companies.cell(row=next_row, column=5).value  = 1
    companies.cell(row=next_row, column=7).value  = 'No'
    companies.cell(row=next_row, column=8).value  = c['ch']
    companies.cell(row=next_row, column=9).value  = 'Yes' if c['is_sme'] else 'No' if c['is_sme'] is False else None
    companies.cell(row=next_row, column=10).value = 'Yes' if c['is_vcse'] else 'No' if c['is_vcse'] is False else None
    companies.cell(row=next_row, column=12).value = c['address']
    existing_companies.add(nl)
    n_new_companies += 1
print(f"\nAdded {n_new_companies} new Companies entries")

n_ccs = 0
for c in all_contracts:
    next_row = ccs.max_row + 1
    ccs.cell(row=next_row, column=1).value  = c['company']
    ccs.cell(row=next_row, column=2).value  = 'Housing'
    ccs.cell(row=next_row, column=3).value  = c['council']
    ccs.cell(row=next_row, column=4).value  = 1
    ccs.cell(row=next_row, column=9).value  = 'Yes' if c['is_sme'] else 'No' if c['is_sme'] is False else None
    ccs.cell(row=next_row, column=10).value = 'Yes' if c['is_vcse'] else 'No' if c['is_vcse'] is False else None
    ccs.cell(row=next_row, column=11).value = 'Supported living | Learning disability | Autism | Mental health'
    ccs.cell(row=next_row, column=13).value = c['title']
    ccs.cell(row=next_row, column=14).value = c['region']
    ccs.cell(row=next_row, column=15).value = 'Local Authority'
    ccs.cell(row=next_row, column=16).value = 'Local'
    n_ccs += 1
print(f"Added {n_ccs} new CCS rows")

wb.save(MANUAL_XLSX)
print(f"\n✓ Saved {MANUAL_XLSX}")

# Summary for CIC specifically
cic_contracts = [c for c in all_contracts if 'community integrated care' in c['company'].lower()]
print(f"\n=== Community Integrated Care: {len(cic_contracts)} contracts in this CSV ===")
for c in cic_contracts:
    print(f"  · {c['council'][:46]:<48s}  ({c['region']})")
