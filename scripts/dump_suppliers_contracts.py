"""
Dump every (supplier × contract) pair from the review DB in a flat,
scannable form. Groups by supplier so duplicates roll up.

Outputs:
  data/scraped/SUPPLIERS_AND_CONTRACTS.md       — grouped by supplier (A-Z)
  data/scraped/SUPPLIERS_AND_CONTRACTS.csv      — flat csv for sort/filter
"""
import openpyxl, csv, sys, io, re
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SRC = 'data/scraped/curated_scraped.xlsx'
OUT_MD = 'data/scraped/SUPPLIERS_AND_CONTRACTS.md'
OUT_CSV = 'data/scraped/SUPPLIERS_AND_CONTRACTS.csv'

wb = openpyxl.load_workbook(SRC, read_only=True)
ws = wb.active

# col idx
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

# group by supplier
by_supplier = defaultdict(list)
for r in rows:
    by_supplier[r['supplier']].append(r)

# write csv (flat)
with open(OUT_CSV, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['Supplier', 'Council', 'Contract Title', 'Categories',
                'Award Date', 'Value', 'Scope', 'Source Portal', 'Source URL', 'Source ID'])
    for r in sorted(rows, key=lambda x: (x['supplier'].lower(), x['council'].lower())):
        w.writerow([r['supplier'], r['council'], r['title'], r['cats'],
                    r['award'], r['value'], r['scope'], r['portal'], r['url'], r['sid']])

# write markdown (grouped by supplier)
lines = []
lines.append(f'# Suppliers and the contracts they relate to\n\n')
lines.append(f'_{len(rows)} (supplier × contract) pairs from `data/scraped/curated_scraped.xlsx`._\n')
lines.append(f'_{len(by_supplier)} unique suppliers._\n\n')
lines.append('Sorted A-Z by supplier. Each supplier shows every contract we have for them.\n\n')
lines.append('---\n\n')

multi = sum(1 for s, items in by_supplier.items() if len(items) > 1)
lines.append(f'**{multi} suppliers appear under more than one contract** (rolled up below).\n\n')

for supplier in sorted(by_supplier, key=lambda s: s.lower()):
    items = by_supplier[supplier]
    if len(items) == 1:
        r = items[0]
        title = r['title'][:200]
        val = f' — **{r["value"]}**' if r['value'] else ''
        src = f' · [source]({r["url"]})' if r['url'] else ''
        lines.append(f'### {supplier}\n')
        lines.append(f'- **{r["council"]}** · {title}{val}{src}\n\n')
    else:
        lines.append(f'### {supplier}  _({len(items)} contracts)_\n')
        for r in sorted(items, key=lambda x: x['council'].lower()):
            title = r['title'][:200]
            val = f' — **{r["value"]}**' if r['value'] else ''
            src = f' · [source]({r["url"]})' if r['url'] else ''
            lines.append(f'- **{r["council"]}** · {title}{val}{src}\n')
        lines.append('\n')

with open(OUT_MD, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f"Wrote {OUT_MD} ({len(by_supplier)} unique suppliers)")
print(f"Wrote {OUT_CSV} ({len(rows)} pairs)")
print(f"\nTop 15 suppliers by contract count:")
for s, items in sorted(by_supplier.items(), key=lambda x: -len(x[1]))[:15]:
    print(f"  {len(items):3d} contracts  {s}")
