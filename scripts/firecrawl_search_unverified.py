"""Cleanup pass: find and verify the 189 providers that aren't Verified yet.

For each non-Verified provider:
  1. Use Firecrawl /search to find their actual website by company name
  2. Pick the best result (UK domain, name match, housing-related context)
  3. Run /extract on that URL with the same schema as the main run
  4. Save to firecrawl_analysed.json for the apply step

This catches:
  - Providers with NO website in source data
  - Providers whose source-data website was wrong (NEEDS_SEARCH)
  - ERROR cases that need a retry on the discovered URL

USAGE:
  python scripts/firecrawl_search_unverified.py [limit] [--workers N]
"""
import os, sys, json, time, threading, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests

API_KEY    = os.environ.get('FIRECRAWL_API_KEY', '')
BASE       = 'https://api.firecrawl.dev/v1'
PROVIDERS  = Path('api/_data/providers.json')
VERIFIED   = Path('data/verification/VERIFIED.json')
DROPS      = Path('data/MANUAL_DROP_LIST.json')
ANALYSED   = Path('data/verification/firecrawl_analysed.json')
DISCOVERED = Path('data/verification/firecrawl_discovered_urls.json')

# Inherit schema + classifier from main script
sys.path.insert(0, str(Path('scripts').absolute()))
from firecrawl_verify import EXTRACT_SCHEMA, classify_extracted, poll_extract

def fc_post(path, body, timeout=180):
    headers = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}
    for attempt in range(3):
        try:
            r = requests.post(f'{BASE}{path}', headers=headers, json=body, timeout=timeout)
            if r.status_code == 429:
                time.sleep(2 ** attempt); continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == 2: raise
            time.sleep(1 + attempt)
    return {}

def search_for_provider(name):
    """Firecrawl /search — returns URL of best match (UK, housing-related)."""
    # Clean name: drop legal suffixes that hurt search
    import re
    q = re.sub(r'\s+(Limited|Ltd\.?|PLC|LLP|CIC)$', '', name, flags=re.I).strip()
    query = f'"{q}" supported living OR supported accommodation OR care UK'

    res = fc_post('/search', {'query': query, 'limit': 5})
    items = (res or {}).get('data') or res.get('items') or []
    if not items: return None

    # Score results: prefer UK domains + name in URL/title
    nl = q.lower().replace(' ', '')
    def score(it):
        url = (it.get('url') or '').lower()
        title = (it.get('title','') + ' ' + it.get('description','')).lower()
        s = 0
        if '.co.uk' in url or '.org.uk' in url: s += 3
        if nl[:8] in url.replace('-', '').replace('.',''): s += 5
        if q.lower() in title: s += 3
        # Avoid directory listing sites and known marketplaces
        for bad in ('cqc.org.uk', 'companies-house', 'find-and-update',
                    'nhs.uk/services', 'autumna.co.uk', 'carehome.co.uk',
                    'connecttosupport', 'patient.info', 'linkedin.com',
                    'facebook.com', 'instagram.com', 'twitter.com',
                    'yelp', 'gov.uk', 'find-a-tender'):
            if bad in url: s -= 5
        return s
    items_sorted = sorted(items, key=score, reverse=True)
    best = items_sorted[0]
    return {'url': best.get('url'), 'title': best.get('title','')}

def extract_at_url(url, name):
    """Same /extract call as main script, but for a discovered URL."""
    base = url.rstrip('/')
    urls = [url, f"{base}/contact-us", f"{base}/about-us"]
    body = {
        'urls':   urls,
        'prompt': (f"Verify that this website belongs to the UK limited company "
                   f"'{name}' AND that the organisation offers housing-related "
                   f"services. Mixed providers (homecare + supported living) count."),
        'schema': EXTRACT_SCHEMA,
    }
    return fc_post('/extract', body, timeout=240)

# ---- Main loop ---------------------------------------------------------------
def main():
    if not API_KEY:
        print("ERROR: FIRECRAWL_API_KEY not set."); sys.exit(1)

    workers = 6
    limit = None
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a.isdigit(): limit = int(a)
        if a == '--workers' and i+1 < len(args): workers = int(args[i+1])

    prov = json.load(open(PROVIDERS, encoding='utf-8'))
    verified = json.load(open(VERIFIED, encoding='utf-8'))
    drops_lc = {n.lower().strip() for n in json.load(open(DROPS, encoding='utf-8'))}

    # Non-verified, non-dropped providers
    todo = [p for p in prov
            if p['name'] not in verified
            and p['name'].lower().strip() not in drops_lc]
    if limit: todo = todo[:limit]
    print(f"To search + verify: {len(todo)}", flush=True)

    # Existing search cache (don't re-search what we already did)
    discovered = json.load(open(DISCOVERED, encoding='utf-8')) if DISCOVERED.exists() else {}
    analysed   = json.load(open(ANALYSED,   encoding='utf-8')) if ANALYSED.exists() else {}

    lock = threading.Lock()
    counter = [0]

    def process(p):
        name = p['name']
        try:
            # Step 1: search for real URL
            if name in discovered:
                real = discovered[name]
            else:
                real = search_for_provider(name)
                with lock:
                    discovered[name] = real
                    json.dump(discovered, open(DISCOVERED, 'w', encoding='utf-8'), indent=2)

            if not real or not real.get('url'):
                with lock:
                    analysed[name] = {'url':'', 'verdict':'NEEDS_SEARCH',
                                      'mode':'extract', 'notes':'no search result',
                                      'checked_at': time.strftime('%Y-%m-%d')}
                    counter[0] += 1
                    json.dump(analysed, open(ANALYSED,'w',encoding='utf-8'), indent=2)
                    print(f"  [{counter[0]:>3d}/{len(todo)}] NO_URL  {name[:48]}", flush=True)
                return

            # Step 2: extract from the discovered URL
            raw = extract_at_url(real['url'], name)
            if raw.get('data'):
                extracted = raw['data'] if isinstance(raw['data'], dict) else raw['data'][0]
            elif raw.get('id'):
                extracted = poll_extract(raw['id'])
            else:
                extracted = {}
            res = classify_extracted(name, extracted)
            res['url'] = real['url']
            res['notes'] = f"discovered via search: {real.get('title','')[:60]}"
            with lock:
                analysed[name] = res
                counter[0] += 1
                json.dump(analysed, open(ANALYSED,'w',encoding='utf-8'), indent=2)
                print(f"  [{counter[0]:>3d}/{len(todo)}] {res['verdict']:<14s}"
                      f"  {name[:42]}  -> {real['url'][:35]}", flush=True)
        except Exception as e:
            with lock:
                analysed[name] = {'url':'', 'verdict':'ERROR',
                                  'error': str(e)[:120], 'mode':'extract',
                                  'checked_at': time.strftime('%Y-%m-%d')}
                counter[0] += 1
                json.dump(analysed, open(ANALYSED,'w',encoding='utf-8'), indent=2)
                print(f"  [{counter[0]:>3d}/{len(todo)}] ERROR  {name}: {str(e)[:60]}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(process, p) for p in todo]
        for f in as_completed(futures):
            f.result()

    print(f"\nDone. Processed: {counter[0]}", flush=True)
    # Apply at end
    import subprocess
    subprocess.run(['python', 'scripts/apply_firecrawl.py'], check=False)

if __name__ == '__main__':
    main()
