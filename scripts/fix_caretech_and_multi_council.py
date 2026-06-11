"""Two fixes the user asked for:

A. CareTech dedup — merge 3 entries (Caretech, Caretech Community Services,
   CTC (a part of Caretech Community Services Ltd)) into one master record
   keyed to Companies House 1955207 (Caretech Community Services Ltd).

B. Multi-council linking from contract descriptions — re-scan the previously-
   ingested Caretech/CIC CSV. For every notice, scan the Description for OTHER
   councils explicitly named (e.g. "Bristol, North Somerset and South
   Gloucestershire" / "Cumberland and Westmorland & Furness" / "Hampshire and
   Isle of Wight ICB") and add the supplier to each named council too.
"""
import csv, re, openpyxl, json
from pathlib import Path

CSV_PATH = Path(r"C:\Users\paul_\Downloads\caretech.csv")
MANUAL_XLSX = 'data/manual_contracts.xlsx'

# ── A. CareTech dedup — add alias names so build_data merges them ────────────
NAME_ALIAS_TARGET = "Caretech Community Services"   # canonical
# We can't rename in-place inside providers.json easily, but build_data.py merges
# by norm(name). We achieve dedup by REWRITING the Companies sheet entries to
# the canonical name and removing the dupes.

print("=== Fix A — CareTech dedup ===")
wb = openpyxl.load_workbook(MANUAL_XLSX)
companies = wb['Companies']
ccs = wb['Company × Council × Sector']

CT_ALIASES = {'caretech', 'caretech community services',
              'caretech community services limited',
              'ctc (a part of caretech community services ltd)',
              'caretech community services ltd'}

# Rewrite Companies sheet — collapse all CT aliases into one row
ct_rows = []
for r in range(2, companies.max_row + 1):
    v = (companies.cell(row=r, column=1).value or '').strip().lower()
    if v in CT_ALIASES:
        ct_rows.append(r)
print(f"  Companies sheet has {len(ct_rows)} CareTech variant rows")
# Keep the first, mark others for deletion
keep_row = None
for r in ct_rows:
    if not keep_row: keep_row = r; companies.cell(row=r, column=1).value = NAME_ALIAS_TARGET
for r in reversed(ct_rows):
    if r != keep_row:
        companies.delete_rows(r)

# Rewrite CCS — every CT alias → canonical name
n_ccs_renamed = 0
for r in range(2, ccs.max_row + 1):
    v = (ccs.cell(row=r, column=1).value or '').strip().lower()
    if v in CT_ALIASES:
        ccs.cell(row=r, column=1).value = NAME_ALIAS_TARGET
        n_ccs_renamed += 1
print(f"  Renamed {n_ccs_renamed} CCS rows to '{NAME_ALIAS_TARGET}'")

# ── B. Multi-council description linking ────────────────────────────────────
print("\n=== Fix B — Multi-council linking from descriptions ===")
with open(CSV_PATH, encoding='utf-8-sig', errors='replace') as f:
    rows = list(csv.DictReader(f))

# Patterns for joint commissioning that name additional councils
# (commissioner X + Y + Z patterns I see in supported living frameworks)
JOINT_PATTERNS = [
    # BNSSG = Bristol, N Somerset, S Gloucs (NHS ICB area)
    (re.compile(r'(Bristol(?:, |/| and )?North Somerset(?:, | and )?South Gloucestershire|BNSSG)', re.I),
     [('Bristol City Council', 'South West'),
      ('North Somerset Council', 'South West'),
      ('South Gloucestershire Council', 'South West')]),
    # Hampshire + Isle of Wight ICB
    (re.compile(r'Hampshire (?:and|&) Isle of Wight Integrated Care Board|Hampshire (?:and|&) IoW', re.I),
     [('Hampshire County Council', 'South East'),
      ('Isle of Wight Council', 'South East')]),
    # Cumbria (post 2023 split = Cumberland + Westmorland)
    (re.compile(r'(?:Cumberland (?:and|&) Westmorland|Westmorland (?:and|&) Furness)', re.I),
     [('Cumberland Council', 'North West'),
      ('Westmorland and Furness Council', 'North West')]),
    # Tees Valley (5 NE councils)
    (re.compile(r'Tees Valley', re.I),
     [('Hartlepool Borough Council', 'North East'),
      ('Stockton-on-Tees Borough Council', 'North East'),
      ('Middlesbrough Council', 'North East'),
      ('Redcar & Cleveland Borough Council', 'North East'),
      ('Darlington Borough Council', 'North East')]),
    # Bath, NE Somerset, Swindon, Wiltshire ICB area (BSW)
    (re.compile(r'\bBSW\b|Bath (?:and|&) North East Somerset.*?(?:Swindon|Wiltshire)', re.I),
     [('Bath and North East Somerset Council', 'South West'),
      ('Wiltshire Council', 'South West'),
      ('Swindon Borough Council', 'South West')]),
    # West London Alliance — 6 NW London boroughs
    (re.compile(r'West London Alliance|\bWLA\b', re.I),
     [('London Borough of Barnet Council', 'London'),
      ('London Borough of Brent', 'London'),
      ('London Borough of Ealing', 'London'),
      ('Harrow Council', 'London'),
      ('London Borough of Hillingdon', 'London'),
      ('London Borough of Hounslow', 'London')]),
]

def parse_suppliers(s):
    if not s: return []
    out = []
    for b in re.split(r'\]\s*\[', s.strip().strip('[]')):
        parts = [p.strip() for p in b.split('|')]
        if not parts or not parts[0]: continue
        out.append(re.sub(r'\s+', ' ', parts[0]).strip())
    return out

# Map orgs → councils same as before
PORTAL_REMAP = {
    'IT-285-8247-HCC2314888 - AWARD':       ('Hertfordshire County Council',     'East of England'),
    'LB Havering Complex Placements Frame': ('London Borough of Havering',       'London'),
    '20230519141505-103835':                ('City of Bradford Metropolitan District Council', 'Yorkshire & The Humber'),
    'C307872':                              ('North East Lincolnshire Council',  'Yorkshire & The Humber'),
}

new_pairs = []
for row in rows:
    nid = (row.get('Notice Identifier') or '').strip()
    desc = (row.get('Description') or '') + ' ' + (row.get('Title') or '')
    if not desc: continue
    # Find which joint pattern matches
    extra_councils = []
    for rx, councils in JOINT_PATTERNS:
        if rx.search(desc):
            extra_councils.extend(councils)
    if not extra_councils: continue

    # Already-mapped primary council
    primary = PORTAL_REMAP.get(nid, (row.get('Organisation Name','').strip(), ''))[0]

    # For each supplier on this notice, add CCS rows for each extra council
    suppliers = parse_suppliers(row.get('Supplier [Name|Address|Ref type|Ref Number|Is SME|Is VCSE]','') or '')
    for sup in suppliers:
        if not sup or sup.lower() in {'none','na','tbc'}: continue
        for (cncl, reg) in extra_councils:
            if cncl == primary: continue
            new_pairs.append({'company': sup, 'council': cncl, 'region': reg,
                              'title': f"{(row.get('Title') or '')[:80]} — multi-council framework "
                                       f"({primary} + co-commissioners). Notice {nid[:30]}.",
                              'notice': nid})

print(f"  Multi-council pairs derived from descriptions: {len(new_pairs)}")
# Add the new CCS rows
for c in new_pairs:
    next_row = ccs.max_row + 1
    ccs.cell(row=next_row, column=1).value  = c['company']
    ccs.cell(row=next_row, column=2).value  = 'Housing'
    ccs.cell(row=next_row, column=3).value  = c['council']
    ccs.cell(row=next_row, column=4).value  = 1
    ccs.cell(row=next_row, column=11).value = 'Supported living | Learning disability | Joint commissioning'
    ccs.cell(row=next_row, column=13).value = c['title']
    ccs.cell(row=next_row, column=14).value = c['region']
    ccs.cell(row=next_row, column=15).value = 'Joint commissioning (multi-council)'
    ccs.cell(row=next_row, column=16).value = 'Local'

wb.save(MANUAL_XLSX)
print(f"\n✓ Saved {MANUAL_XLSX}")
print(f"  Added {len(new_pairs)} multi-council CCS rows from description parsing")
