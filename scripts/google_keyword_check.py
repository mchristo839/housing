"""Alternative to bulk scraping — use Google Programmable Search to detect
key terms on a site without actually scraping it.

For each provider we run:
   site:provider-website.co.uk ("supported living" OR "assisted living" OR
                                 "supported accommodation" OR "asylum" OR
                                 "homelessness" OR "care home")
plus a name-match query:
   site:provider-website.co.uk "[Company Name Limited]"

Google returns whether ANY page on the site matches — so it implicitly searches
the WHOLE site, not just the homepage. No need to crawl multiple pages.

WHEN TO USE THIS vs Apify:
  Apify  → fetches the actual page text (slower, $ cost, but you get contacts/emails)
  Google → just answers "do these keywords appear anywhere on the site?"
           Cheaper, faster, but doesn't extract contact details

For VERIFICATION you can use Google for the keyword check + Companies House
for everything else, skipping Apify entirely.

SETUP:
  1. Get API key:  https://developers.google.com/custom-search/v1/introduction
  2. Create a Programmable Search Engine at https://programmablesearchengine.google.com
     (set "Sites to search" = nothing — defaults to the whole web; we add site: in the query)
  3. Set environment vars:
       $env:GOOGLE_API_KEY = "..."
       $env:GOOGLE_CSE_ID  = "..."
  Free tier: 100 queries/day. So full 1,800-provider run = ~$50 paid usage,
  OR spread across 30-day free quota for free verification.

USAGE:
  python scripts/google_keyword_check.py 50    # check first 50 providers
  python scripts/google_keyword_check.py       # process whole DB (paged)
  python scripts/google_keyword_check.py status

OUTPUT:
  data/verification/google_keyword.json
    { "Provider Name": {
        "site":         "providersite.co.uk",
        "name_match":   true,           # site mentions the company name
        "housing_hits": ["supported living", "care home"],
        "verdict":      "KEEP" | "DROP" | "UNCLEAR",
        "checked_at":   "2026-06-10"
    }, ... }
"""
import os, sys, json, time, urllib.parse, re
from pathlib import Path
import requests

API_KEY  = os.environ.get('GOOGLE_API_KEY', '')
CSE_ID   = os.environ.get('GOOGLE_CSE_ID', '')
OUT_FILE = Path('data/verification/google_keyword.json')
API_URL  = 'https://www.googleapis.com/customsearch/v1'

HOUSING_TERMS = [
    'supported living', 'assisted living', 'supported accommodation',
    'supported housing', 'extra care', 'residential care', 'care home',
    'nursing home', 'asylum accommodation', 'homelessness',
    'refuge', 'hostel', 'sheltered housing', 'care leaver',
    'mental health accommodation', 'semi-independent',
]

def check_keys():
    if not API_KEY or not CSE_ID:
        print("ERROR: GOOGLE_API_KEY and GOOGLE_CSE_ID must be set.")
        print("See setup instructions in script docstring.")
        sys.exit(1)

def domain_of(url):
    if not url: return ''
    try:
        return urllib.parse.urlparse(url if '//' in url else 'http://'+url).netloc.lstrip('www.')
    except Exception:
        return ''

def google_search(query):
    r = requests.get(API_URL, params={
        'key': API_KEY, 'cx': CSE_ID, 'q': query, 'num': 3
    }, timeout=15)
    if r.status_code == 429:
        time.sleep(2); return google_search(query)
    if r.status_code != 200:
        return {'error': f'{r.status_code}: {r.text[:120]}'}
    return r.json()

def check_one(name, website):
    """Run 2 Google queries: name-match + housing-keyword search."""
    site = domain_of(website)
    if not site:
        return {'verdict': 'UNCLEAR', 'site': '', 'note': 'no website'}

    # Query 1: do any pages on the site mention the company name?
    name_clean = re.sub(r'\s+(Limited|Ltd|Ltd\.?|PLC|LLP)$', '', name, flags=re.I).strip()
    q1 = f'site:{site} "{name_clean}"'
    r1 = google_search(q1)
    name_match = bool(r1.get('items'))

    # Query 2: do any pages on the site contain housing keywords?
    keyword_or = ' OR '.join(f'"{t}"' for t in HOUSING_TERMS[:8])
    q2 = f'site:{site} ({keyword_or})'
    r2 = google_search(q2)
    items = r2.get('items', [])
    housing_hits = []
    for it in items:
        snippet = (it.get('snippet', '') + ' ' + it.get('title','')).lower()
        for t in HOUSING_TERMS:
            if t in snippet and t not in housing_hits:
                housing_hits.append(t)

    if housing_hits and name_match:
        verdict = 'KEEP'
    elif housing_hits:
        verdict = 'KEEP'  # site has housing services even if name not literal match
    elif name_match:
        verdict = 'UNCLEAR'  # site is theirs but no obvious housing service
    else:
        verdict = 'NEEDS_SEARCH'

    return {
        'site':         site,
        'name_match':   name_match,
        'housing_hits': housing_hits,
        'top_titles':   [it.get('title','') for it in items[:3]],
        'verdict':      verdict,
        'checked_at':   time.strftime('%Y-%m-%d'),
    }

def cmd_run(limit=None):
    check_keys()
    prov = json.load(open('api/_data/providers.json', encoding='utf-8'))
    cache = json.load(open(OUT_FILE, encoding='utf-8')) if OUT_FILE.exists() else {}
    todo = [p for p in prov if p['name'] not in cache and p.get('website')]
    if limit: todo = todo[:limit]
    print(f"Cached: {len(cache)}.  To check: {len(todo)}")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(todo, 1):
        try:
            res = check_one(p['name'], p['website'])
            cache[p['name']] = res
            print(f"  [{i:>4d}/{len(todo)}] {res['verdict']:<13s}"
                  f"  {p['name'][:42]:<44s}  hits={len(res.get('housing_hits',[]))}")
        except Exception as e:
            cache[p['name']] = {'verdict':'ERROR','error':str(e)[:80],
                                'checked_at': time.strftime('%Y-%m-%d')}
            print(f"  [{i:>4d}/{len(todo)}] ERROR  {p['name']}: {e}")
        if i % 20 == 0:
            json.dump(cache, open(OUT_FILE, 'w', encoding='utf-8'), indent=2)
        time.sleep(0.2)   # respectful rate-limit (free tier ≈ 100/day)
    json.dump(cache, open(OUT_FILE, 'w', encoding='utf-8'), indent=2)
    print(f"\nDone. Total cached: {len(cache)}")

def cmd_status():
    if not OUT_FILE.exists(): print("No checks yet."); return
    d = json.load(open(OUT_FILE, encoding='utf-8'))
    from collections import Counter
    c = Counter(v.get('verdict','?') for v in d.values())
    print(f"Total checked: {len(d)}")
    for v, n in c.most_common(): print(f"  {v}: {n}")

if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else 'run'
    if   arg == 'status':  cmd_status()
    elif arg.isdigit():    cmd_run(limit=int(arg))
    else:                  cmd_run()
