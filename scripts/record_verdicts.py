"""Record verdicts to a persistent CSV + auto-apply drops to MANUAL_DROP_LIST.

Usage:
    python scripts/record_verdicts.py "Name 1|DROP" "Name 2|KEEP" "Name 3|UNCLEAR" ...
"""
import json, csv, sys
from pathlib import Path

VERDICTS_CSV = Path('data/scraped/VERIFICATION_VERDICTS.csv')
DROP_LIST = Path('data/MANUAL_DROP_LIST.json')

# Append rows
new_drops = []
existing = []
if VERDICTS_CSV.exists():
    with open(VERDICTS_CSV, encoding='utf-8') as f:
        existing = list(csv.DictReader(f))

with open(VERDICTS_CSV, 'a' if VERDICTS_CSV.exists() else 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    if not existing:
        w.writerow(['name', 'verdict'])
    for arg in sys.argv[1:]:
        if '|' not in arg: continue
        name, verdict = arg.rsplit('|', 1)
        name, verdict = name.strip(), verdict.strip().upper()
        w.writerow([name, verdict])
        if verdict == 'DROP':
            new_drops.append(name)

# Apply drops
dl = json.load(open(DROP_LIST, encoding='utf-8'))
before = len(dl)
for n in new_drops:
    if n not in dl: dl.append(n)
json.dump(dl, open(DROP_LIST, 'w', encoding='utf-8'), indent=2)
print(f"Verdicts recorded: {len(sys.argv)-1}")
print(f"MANUAL_DROP_LIST: {before} -> {len(dl)}  (+{len(dl)-before})")
