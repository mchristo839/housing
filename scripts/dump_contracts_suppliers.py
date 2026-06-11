"""
Dump every contract with all suppliers awarded to it.
Inverse of dump_suppliers_contracts.py — one heading per contract,
all suppliers underneath.

Outputs:
  data/scraped/CONTRACTS_AND_SUPPLIERS.md
  data/scraped/CONTRACTS_AND_SUPPLIERS.csv  (flat — already exists as
       SUPPLIERS_AND_CONTRACTS.csv, but resorted contract-first here)
"""
import openpyxl, csv, sys, io, re
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SRC = 'data/scraped/curated_scraped.xlsx'
OUT_MD = 'data/scraped/CONTRACTS_AND_SUPPLIERS.md'

wb = openpyxl.load_workbook(SRC, read_only=True)
ws = wb.active

C_CO=0; C_COUNCIL=2; C_CATS=10; C_AWARD=11; C_TITLE=12; C_SCOPE=15
C_PORTAL=17; C_URL=18; C_SID=19; C_VAL=22

rows = []
for r in ws.iter_rows(min_row=2, values_only=True):
    if not r[C_CO] or not r[C_COUNCIL]:
        continue
    val = ''
    try:
        v = float(str(r[C_VAL]).replace(',', '').strip())
        if v >= 1_000_000:
            val = f'£{v/1_000_000:.1f}M'
        elif v > 0:
            val = f'£{int(v):,}'
    except Exception:
        pass
    title = re.sub(r'\s+', ' ', str(r[C_TITLE] or '')).strip()
    rows.append({
        'supplier': str(r[C_CO]).strip(),
        'council':  str(r[C_COUNCIL]).strip(),
        'title':    title,
        'cats':     str(r[C_CATS] or '').strip(),
        'award':    str(r[C_AWARD] or '').strip(),
        'value':    val,
        'scope':    str(r[C_SCOPE] or '').strip(),
        'portal':   str(r[C_PORTAL] or '').strip(),
        'url':      str(r[C_URL] or '').strip(),
        'sid':      str(r[C_SID] or '').strip(),
    })

print(f"Loaded {len(rows)} supplier×contract pairs")

# Group by contract. Contract identity = (source_id) when available,
# else (council, title). This is what binds suppliers together as
# "awarded to the same contract".
def contract_key(r):
    if r['sid']:
        return ('sid', r['sid'])
    # Strip the trailing "(Bidstats nnnn; Status · supplier @ Loc)" annotation
    # so different supplier rows for the same contract collapse together.
    t = re.sub(r'\s*\([^)]*?bidstats[^)]*\)\s*$', '', r['title'], flags=re.I)
    t = re.sub(r'\s*\([^)]*?supplier @[^)]*\)\s*$', '', t, flags=re.I)
    return ('ct', (r['council'].lower(), t.lower()[:120]))

by_contract = defaultdict(list)
for r in rows:
    by_contract[contract_key(r)].append(r)

# London ordering for council headings
LONDON = ['Barking and Dagenham','Barnet','Bexley','Brent','Bromley','Camden',
         'City of London','Croydon','Ealing','Enfield','Greenwich','Hackney',
         'Hammersmith and Fulham','Haringey','Harrow','Havering','Hillingdon',
         'Hounslow','Islington','Kensington and Chelsea','Kingston upon Thames',
         'Lambeth','Lewisham','Merton','Newham','Redbridge','Richmond upon Thames',
         'Southwark','Sutton','Tower Hamlets','Waltham Forest','Wandsworth','Westminster']

def borough_of(council):
    cl = council.lower()
    for b in LONDON:
        if b.lower() in cl: return b
        if cl.startswith('royal borough of') and b.split()[0].lower() in cl:
            # rough match
            pass
    if 'kingston' in cl: return 'Kingston upon Thames'
    if 'richmond' in cl: return 'Richmond upon Thames'
    if 'kensington' in cl or 'rbkc' in cl: return 'Kensington and Chelsea'
    if 'tower hamlets' in cl: return 'Tower Hamlets'
    if 'hammersmith' in cl or 'fulham' in cl: return 'Hammersmith and Fulham'
    return council

# Sort contracts by (borough, council, title)
def sort_key(kv):
    items = kv[1]
    r0 = items[0]
    b = borough_of(r0['council'])
    pri = (LONDON.index(b), b) if b in LONDON else (99, b)
    return (pri, r0['council'], r0['title'].lower())

contracts_sorted = sorted(by_contract.items(), key=sort_key)

# Build markdown
lines = []
lines.append('# Contracts and the suppliers awarded to them\n\n')
lines.append(f'_{len(by_contract)} unique contracts · {len(rows)} supplier awards · {len(set(r["supplier"] for r in rows))} unique suppliers._\n\n')
lines.append('Sorted by London borough A-Z. Each contract heading shows: buyer, contract title, value, source. The bullet list under it is every supplier awarded to that contract.\n\n')
lines.append('---\n\n')

current_borough = None
for key, items in contracts_sorted:
    r0 = items[0]
    b = borough_of(r0['council'])
    if b != current_borough:
        current_borough = b
        lines.append(f'\n## {b}\n\n')

    val = f' — **{r0["value"]}**' if r0['value'] else ''
    src = f' · [source]({r0["url"]})' if r0['url'] else ''
    # Strip the per-supplier trailing annotation from the contract title
    t = re.sub(r'\s*\([^)]*?bidstats[^)]*\)\s*$', '', r0['title'], flags=re.I)
    t = re.sub(r'\s*\([^)]*?supplier @[^)]*\)\s*$', '', t, flags=re.I)
    t = t.strip()

    lines.append(f'### {r0["council"]} — {t[:180]}{val}{src}\n\n')
    lines.append(f'**{len(items)} supplier{"s" if len(items)>1 else ""} awarded:**\n\n')

    # Sort suppliers A-Z
    for r in sorted(items, key=lambda x: x['supplier'].lower()):
        # Pull supplier location from the trailing annotation if it had one
        loc_match = re.search(r'supplier @ ([^)]+)\)', r['title'], flags=re.I)
        loc = f' _({loc_match.group(1).strip()})_' if loc_match and loc_match.group(1).strip() not in ('None','') else ''
        lines.append(f'- {r["supplier"]}{loc}\n')
    lines.append('\n')

with open(OUT_MD, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f"Wrote {OUT_MD}")
print(f"  Contracts        : {len(by_contract)}")
print(f"  Supplier awards  : {len(rows)}")
print(f"  Unique suppliers : {len(set(r['supplier'] for r in rows))}")
print(f"\nLargest contracts by supplier count:")
for key, items in sorted(by_contract.items(), key=lambda x: -len(x[1]))[:12]:
    r0 = items[0]
    t = re.sub(r'\s*\([^)]*?bidstats[^)]*\)\s*$', '', r0['title'], flags=re.I)[:55]
    print(f"  {len(items):3d} suppliers · {r0['council'][:25]:25s} · {t}")
