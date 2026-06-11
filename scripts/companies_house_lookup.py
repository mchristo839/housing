"""Companies House API lookup — the authoritative UK source.

For each provider in the database, look up the registered company and capture:
  - Company number
  - Active status (not dissolved/liquidated)
  - SIC codes  (which tell us whether they're a CARE / HOUSING business)
  - Registered office address
  - Date of incorporation

This is FREE and the most authoritative verification source available.

SETUP:
  1. Register at https://developer.company-information.service.gov.uk/
  2. Create an API key
  3. Set environment variable:  $env:CH_API_KEY = "your-key"

USAGE:
  python scripts/companies_house_lookup.py            # process whole DB
  python scripts/companies_house_lookup.py 100        # process first 100 only
  python scripts/companies_house_lookup.py status     # show progress

OUTPUT:
  data/verification/companies_house.json
    { "Provider Name": {
        "number":     "12345678",
        "status":     "active",
        "sic_codes":  ["87200", "87300"],
        "address":    "Registered office, ...",
        "incorporated": "2019-10-10",
        "is_housing": true,         # SIC matches housing/care codes
        "looked_up":  "2026-06-10"
      }, ... }
"""
import os, sys, json, time, base64, urllib.parse
from pathlib import Path
import requests

API_KEY = os.environ.get('CH_API_KEY', '')
API_BASE = 'https://api.company-information.service.gov.uk'
OUT_FILE = Path('data/verification/companies_house.json')

# SIC codes that indicate a HOUSING / CARE business
# Source: https://resources.companieshouse.gov.uk/sic/
HOUSING_SIC = {
    # Residential care
    '86101': 'Hospital activities',
    '86220': 'Specialist medical practice',
    '86900': 'Other human health activities',
    '87100': 'Residential nursing care activities',
    '87200': 'Residential care activities for LD/mental health/substance abuse',
    '87300': 'Residential care activities for the elderly and disabled',
    '87900': 'Other residential care activities',
    '88100': 'Social work activities without accommodation, elderly/disabled',
    '88910': 'Child day-care activities',
    '88990': 'Other social work activities without accommodation',
    # Housing
    '41100': 'Development of building projects',
    '68100': 'Buying and selling of own real estate',
    '68201': 'Renting/operating of Housing Association real estate',
    '68209': 'Other letting and operating of own/leased real estate',
    '68310': 'Real estate agencies',
    '68320': 'Management of real estate on a fee basis',
    # Voluntary
    '94990': 'Activities of other membership organisations n.e.c.',
}

def auth_header():
    """Companies House uses HTTP Basic with API key as username, blank password."""
    if not API_KEY:
        print("ERROR: CH_API_KEY not set. See setup instructions in script docstring.")
        sys.exit(1)
    raw = f"{API_KEY}:".encode('ascii')
    return {'Authorization': f'Basic {base64.b64encode(raw).decode()}'}

def search_company(name):
    """Search by name, return best match."""
    url = f'{API_BASE}/search/companies'
    params = {'q': name, 'items_per_page': 5}
    try:
        r = requests.get(url, headers=auth_header(), params=params, timeout=10)
        if r.status_code == 429:
            time.sleep(2); return search_company(name)
        r.raise_for_status()
        results = r.json().get('items', [])
        # Best match: prefer exact title match
        nl = name.lower().strip()
        for item in results:
            if item.get('title', '').lower().strip() == nl:
                return item
        # Otherwise return top result
        return results[0] if results else None
    except Exception as e:
        print(f"  search error for '{name}': {e}")
        return None

def get_profile(number):
    """Fetch full company profile by number."""
    url = f'{API_BASE}/company/{number}'
    try:
        r = requests.get(url, headers=auth_header(), timeout=10)
        if r.status_code == 429:
            time.sleep(2); return get_profile(number)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  profile error for {number}: {e}")
        return None

def format_address(addr_dict):
    if not addr_dict: return ''
    parts = [addr_dict.get(k, '') for k in
             ('care_of', 'po_box', 'address_line_1', 'address_line_2',
              'locality', 'region', 'postal_code', 'country')]
    return ', '.join(p for p in parts if p)

def lookup_one(name):
    """Full 2-step lookup for one provider."""
    s = search_company(name)
    if not s: return None
    number = s.get('company_number')
    if not number: return None
    p = get_profile(number) or s
    sic = p.get('sic_codes', []) or s.get('sic_codes', [])
    return {
        'number':       number,
        'status':       p.get('company_status', s.get('company_status', '')),
        'matched_name': s.get('title', ''),
        'sic_codes':    sic,
        'sic_labels':   [HOUSING_SIC.get(c, '') for c in sic if c in HOUSING_SIC],
        'address':      format_address(p.get('registered_office_address') or
                                       s.get('address') or {}),
        'incorporated': p.get('date_of_creation', s.get('date_of_creation', '')),
        'is_housing':   any(c in HOUSING_SIC for c in sic),
        'looked_up':    time.strftime('%Y-%m-%d'),
    }

def cmd_run(limit=None):
    prov = json.load(open('api/_data/providers.json', encoding='utf-8'))
    cache = json.load(open(OUT_FILE, encoding='utf-8')) if OUT_FILE.exists() else {}

    todo = [p for p in prov if p['name'] not in cache]
    if limit: todo = todo[:limit]
    print(f"Cached: {len(cache)}.  To look up: {len(todo)}")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    for i, p in enumerate(todo, 1):
        name = p['name']
        res = lookup_one(name)
        if res:
            cache[name] = res
            tag = 'HOUSING' if res['is_housing'] else 'OTHER  '
            print(f"  [{i:>4d}/{len(todo)}] {tag} {res['status']:<10s} {res['number']} — {name[:50]}")
        else:
            cache[name] = {'looked_up': time.strftime('%Y-%m-%d'), 'not_found': True}
            print(f"  [{i:>4d}/{len(todo)}] NOT FOUND — {name[:50]}")
        # Save every 25 to allow safe interruption
        if i % 25 == 0:
            json.dump(cache, open(OUT_FILE, 'w', encoding='utf-8'), indent=2)
        time.sleep(0.6)   # rate-limit: CH allows 600 req/5min = ~2/s, we go slower
    json.dump(cache, open(OUT_FILE, 'w', encoding='utf-8'), indent=2)
    print(f"\nDone. Total cached: {len(cache)}")

def cmd_status():
    if not OUT_FILE.exists():
        print("No lookups yet."); return
    d = json.load(open(OUT_FILE, encoding='utf-8'))
    active = sum(1 for v in d.values() if v.get('status') == 'active')
    dissolved = sum(1 for v in d.values() if v.get('status') == 'dissolved')
    is_housing = sum(1 for v in d.values() if v.get('is_housing'))
    not_found = sum(1 for v in d.values() if v.get('not_found'))
    print(f"Total looked up:     {len(d)}")
    print(f"  Active companies:  {active}")
    print(f"  Dissolved:         {dissolved}")
    print(f"  Housing SIC code:  {is_housing}")
    print(f"  Not found:         {not_found}")

if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else 'run'
    if arg == 'status':         cmd_status()
    elif arg.isdigit():         cmd_run(limit=int(arg))
    else:                       cmd_run()
