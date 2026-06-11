"""Append a single provider's 4-step verification result.

USAGE:
  python scripts/record_v2_result.py <NAME> <STEP1> <STEP2_URL> <STEP3> <EMAIL> <PHONE> <CONTACT_URL> <VERDICT> <NOTES>

Where:
  NAME          = provider name (quote if spaces)
  STEP1         = Y (website matches company) / N (doesn't) / NO_SITE
  STEP2_URL     = real URL from web search if step1=N, else empty
  STEP3         = comma-separated housing services matched, or NONE
  EMAIL         = verified email or empty
  PHONE         = verified phone or empty
  CONTACT_URL   = /contact-us URL if no email/phone
  VERDICT       = KEEP / DROP / UPDATE
  NOTES         = free text

Pass "-" for any field to mean empty.
"""
import csv, sys
from pathlib import Path

RESULTS = Path('data/scraped/VERIFICATION_V2_RESULTS.csv')
FIELDS = ['name', 'step1_url_owner', 'step2_real_url', 'step3_services',
          'step4_email', 'step4_phone', 'step4_contact', 'verdict', 'notes']

if len(sys.argv) < 9:
    print(__doc__); sys.exit(1)

args = [a if a != '-' else '' for a in sys.argv[1:10]]
while len(args) < 9: args.append('')

row = dict(zip(FIELDS, args))

write_header = not RESULTS.exists()
RESULTS.parent.mkdir(parents=True, exist_ok=True)
with open(RESULTS, 'a' if RESULTS.exists() else 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    if write_header: w.writeheader()
    w.writerow(row)

print(f"Recorded: {row['name']}  →  step1={row['step1_url_owner']}  verdict={row['verdict']}")
