"""Ingest the Contracts Finder CSV the user provided — extract every (council ×
supplier) pair from the 8 award notices and add them to manual_contracts.xlsx
with proper citation back to each Notice Identifier.

Rules followed:
  - Skip notice 1 (VisitBritain Occupancy Survey — non-housing)
  - TC160 notice (Bolton) → all suppliers go to NW Regional, not Bolton Local
  - Every supplier×council pair includes Notice ID + award date for citation
  - Un-drop the 6 NWADCS providers we previously dropped — the TC160 notice
    proves they have a real contract, and the CSV gives addresses we can use.
"""
import csv, re, openpyxl, json
from pathlib import Path
from collections import defaultdict

CSV_PATH = Path(r"C:\Users\paul_\Downloads\notices (14).csv")
MANUAL_XLSX = 'data/manual_contracts.xlsx'
DROP_PATH = 'data/MANUAL_DROP_LIST.json'

# Parse the CSV (it's UTF-8 with some Windows quirks)
with open(CSV_PATH, newline='', encoding='utf-8-sig', errors='replace') as f:
    rows = list(csv.DictReader(f))

print(f"Loaded {len(rows)} notice rows from CSV\n")

def parse_suppliers(s):
    """[Name|Addr|RefType|RefNum|IsSME|IsVCSE][...] → list of dicts."""
    if not s: return []
    out = []
    # Each supplier block is enclosed in [ ] separated by ][
    blocks = re.split(r'\]\s*\[', s.strip('[]'))
    for b in blocks:
        parts = [p.strip() for p in b.split('|')]
        if not parts or not parts[0]: continue
        out.append({
            'name': parts[0].strip(),
            'addr': parts[1].strip() if len(parts) > 1 else '',
            'ch':   parts[3].strip() if len(parts) > 3 else '',
            'sme':  (parts[4].strip().lower() == 'yes') if len(parts) > 4 else None,
            'vcse': (parts[5].strip().lower() == 'yes') if len(parts) > 5 else None,
        })
    return out

# Manually-derived metadata per notice (council key + scope override + skip flag)
NOTICE_META = {
    'BIP253136590':                              {'skip': True, 'reason': 'VisitBritain Occupancy Survey - non-housing'},
    'LPOOL001-DN658473-41613729':                {'council': 'Liverpool City Council',                'scope': 'Local',  'region': 'North West'},
    'BOLT001-DN680551-93060379':                 {'council': 'North West regional framework',         'scope': 'Regional','region': 'North West', 'note': 'TC160 NWADCS FPS — pan-NW'},
    'KMCCYP-129 Further competitions October 2022 - September 2023': {'council': 'Kirklees Council',  'scope': 'Local',  'region': 'Yorkshire & The Humber'},
    '20220815144905-103277':                     {'council': 'City of Bradford Metropolitan District Council', 'scope': 'Local', 'region': 'Yorkshire & The Humber'},
    'MANC001-DN554293-10993059':                 {'council': 'Manchester City Council',               'scope': 'Local',  'region': 'North West'},
    'Retrospective CLA Specialist Mental Health provision': {'council': 'East Riding of Yorkshire Council', 'scope': 'Local', 'region': 'Yorkshire & The Humber'},
    'LEEDSCITY001-DN355373-81001485':            {'council': 'Leeds City Council',                    'scope': 'Local',  'region': 'Yorkshire & The Humber'},
}

# 1. Un-drop the 6 NWADCS providers we previously dropped — we now have
#    proper addresses from the TC160 award notice
UNDROP = {
    'Altus Social Ltd',
    'Avensis Support Ltd',
    'Dynamis Enterprises Ltd',
    'Horizons Plus',
    'Revolve Therapy and Training',
    'Right Step Limited (RSL)',
}

# Update MANUAL_DROP_LIST.json
drop_list = json.load(open(DROP_PATH, encoding='utf-8'))
before = len(drop_list)
drop_list = [n for n in drop_list if n not in UNDROP]
json.dump(drop_list, open(DROP_PATH, 'w', encoding='utf-8'), indent=2)
print(f"MANUAL_DROP_LIST: {before} → {len(drop_list)}  (un-dropped 6 NWADCS providers)\n")

# 2. Parse each notice + collect contract rows
contracts_to_add = []   # list of dicts ready to write to CCS sheet
suppliers_seen = set()  # to dedup supplier addresses for Companies sheet

for row in rows:
    nid = (row.get('Notice Identifier') or '').strip()
    if not nid: continue
    meta = NOTICE_META.get(nid)
    if not meta:
        print(f"  ! no metadata for notice {nid!r}, skipping")
        continue
    if meta.get('skip'):
        print(f"  ⊘ SKIP {nid[:50]} — {meta['reason']}")
        continue
    title    = row.get('Title') or ''
    awarded  = row.get('Awarded Date') or ''
    value    = row.get('Awarded Value') or ''
    end      = row.get('Contract end date') or ''
    suppliers = parse_suppliers(row.get('Supplier [Name|Address|Ref type|Ref Number|Is SME|Is VCSE]') or row.get('Supplier') or '')
    council  = meta['council']
    scope    = meta['scope']
    region   = meta['region']

    print(f"  ✓ {nid[:48]:<50s}  →  {council:<40s}  ({len(suppliers)} suppliers)")
    for sup in suppliers:
        sup_name = sup['name'].strip()
        if not sup_name: continue
        # Build short citation
        citation = (
            f"{title[:80]} — {council}. "
            f"Awarded {awarded}. Value £{value}. "
            f"Notice {nid[:30]}."
        )
        contracts_to_add.append({
            'company': sup_name,
            'council': council,
            'scope':   scope,
            'region':  region,
            'title':   citation,
            'address': sup['addr'],
            'is_sme':  sup['sme'],
            'is_vcse': sup['vcse'],
            'ch':      sup['ch'],
            'notice':  nid,
        })
        suppliers_seen.add(sup_name.lower().strip())

print(f"\nExtracted {len(contracts_to_add)} (supplier × council) contracts across notices")
print(f"Unique suppliers across all notices: {len(suppliers_seen)}\n")

# 3. Write to manual_contracts.xlsx
wb = openpyxl.load_workbook(MANUAL_XLSX)
companies = wb['Companies']
ccs = wb['Company × Council × Sector']

# Build set of existing company names (lowercased) for dedup
existing_companies = set()
for r in range(2, companies.max_row + 1):
    v = (companies.cell(row=r, column=1).value or '').strip().lower()
    if v: existing_companies.add(v)

# Collect address-per-supplier (using first address seen)
supplier_addresses = {}
for c in contracts_to_add:
    nl = c['company'].lower().strip()
    if nl not in supplier_addresses and c['address']:
        supplier_addresses[nl] = c

# 4. Add Companies sheet rows for new suppliers
n_new_companies = 0
for nl, c in supplier_addresses.items():
    if nl in existing_companies: continue
    # Skip junk names
    if len(nl) < 3 or nl in {'none','na','tbc','fsip','just one','llyon health'}: continue
    next_row = companies.max_row + 1
    companies.cell(row=next_row, column=1).value  = c['company']
    companies.cell(row=next_row, column=2).value  = 0  # Total — build_data will compute
    companies.cell(row=next_row, column=5).value  = 1  # Housing — flag as housing (mandatory for build)
    companies.cell(row=next_row, column=7).value  = 'No'  # Both Sectors?
    companies.cell(row=next_row, column=8).value  = c['ch']
    companies.cell(row=next_row, column=9).value  = 'Yes' if c['is_sme'] else 'No' if c['is_sme'] is False else None
    companies.cell(row=next_row, column=10).value = 'Yes' if c['is_vcse'] else 'No' if c['is_vcse'] is False else None
    companies.cell(row=next_row, column=12).value = c['address']
    existing_companies.add(nl)
    n_new_companies += 1

print(f"Added {n_new_companies} new Companies-sheet entries")

# 5. Add CCS rows
n_ccs_added = 0
for c in contracts_to_add:
    next_row = ccs.max_row + 1
    ccs.cell(row=next_row, column=1).value  = c['company']
    ccs.cell(row=next_row, column=2).value  = 'Housing'
    ccs.cell(row=next_row, column=3).value  = c['council']
    ccs.cell(row=next_row, column=4).value  = 1
    ccs.cell(row=next_row, column=9).value  = 'Yes' if c['is_sme'] else 'No' if c['is_sme'] is False else None
    ccs.cell(row=next_row, column=10).value = 'Yes' if c['is_vcse'] else 'No' if c['is_vcse'] is False else None
    ccs.cell(row=next_row, column=11).value = 'Supported accommodation | Care leavers | Young people'
    ccs.cell(row=next_row, column=12).value = ''  # Most Recent Award - left for build
    ccs.cell(row=next_row, column=13).value = c['title']
    ccs.cell(row=next_row, column=14).value = c['region']
    ccs.cell(row=next_row, column=15).value = 'Local Authority'
    ccs.cell(row=next_row, column=16).value = c['scope']
    n_ccs_added += 1

print(f"Added {n_ccs_added} new CCS rows")

wb.save(MANUAL_XLSX)
print(f"\n✓ Saved {MANUAL_XLSX}")

# Bedspace summary
print("\n=== BEDSPACE summary from this ingest ===")
bedspace_contracts = [c for c in contracts_to_add if 'bedspace' in c['company'].lower()]
for c in bedspace_contracts:
    print(f"  · {c['council']:<48s}  scope={c['scope']:<10s}  notice={c['notice'][:30]}")
