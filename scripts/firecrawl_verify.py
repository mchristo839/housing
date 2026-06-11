"""Firecrawl-based verification — superior to plain Apify for JS-heavy sites.

Two modes:

  MODE A — /scrape + local keywords (CHEAPER)
    Hit each provider's homepage with Firecrawl /scrape (returns clean markdown).
    Then run our own keyword detection. 1 credit per page.
    1,792 providers ≈ 1,792 credits (~$50/month plan covers it).

  MODE B — /extract with JSON schema (SMARTER but pricier)
    Ask Firecrawl's LLM to extract a structured verdict from each site:
      { company_name_on_site, ltd_company_match, offers_supported_living,
        services_list, email, phone, address, ltd_company_number }
    No keyword regex needed — the LLM judges semantically. Catches "we work
    with adults in their own homes AND in shared supported living houses"
    that simple keywords would miss.

SETUP:
  1. Sign up at https://firecrawl.dev
  2. Get API key (Settings → API Keys)
  3. Set:  $env:FIRECRAWL_API_KEY = "fc-..."

USAGE:
  python scripts/firecrawl_verify.py scrape 50     # MODE A — first 50, $1.50 ish
  python scripts/firecrawl_verify.py scrape        # MODE A — full run
  python scripts/firecrawl_verify.py extract 50    # MODE B — smarter, costlier
  python scripts/firecrawl_verify.py extract       # MODE B — full run
  python scripts/firecrawl_verify.py status

OUTPUT:
  data/verification/firecrawl_analysed.json
    { "Provider Name": {
        "url":           "https://...",
        "name_match":    true,
        "housing_terms": ["supported living", "care home"],
        "non_housing":   [],
        "emails":        ["info@..."],
        "phones":        ["01234..."],
        "address":       "...",
        "verdict":       "KEEP" | "DROP" | "UNCLEAR" | "NEEDS_SEARCH",
        "mode":          "scrape" | "extract",
        "checked_at":    "2026-06-10",
    }, ... }
"""
import os, sys, json, time, re
from pathlib import Path
import requests

API_KEY = os.environ.get('FIRECRAWL_API_KEY', '')
BASE    = 'https://api.firecrawl.dev/v1'
OUT     = Path('data/verification/firecrawl_analysed.json')

HOUSING_KEYWORDS = [
    'supported living', 'assisted living', 'supported accommodation',
    'supported housing', 'extra care', 'residential care', 'care home',
    'nursing home', 'asylum accommodation', 'homelessness', 'homeless',
    'refuge', 'hostel', 'sheltered housing', 'care leaver', 'leaving care',
    '16+ supported', 'young people housing', "children's home",
    'mental health accommodation', 'transitional accommodation',
    'semi-independent', 'rough sleeping', 'temporary accommodation',
    'crisis accommodation', 'housing first', 'domestic abuse refuge',
    'family accommodation', 'tenancy support', 'shared lives',
]
NON_HOUSING_TERMS = [
    'pizza', 'takeaway only', 'restaurant menu',
    'veterinary practice', 'animal hospital', 'pet clinic',
    'plumbing services', 'heating engineer', 'gas safe registered',
    'plastics manufacturing', 'packaging supplier',
    'department store', 'retail outlet',
    'recruitment agency', 'staffing solutions', 'temp agency',
    'training courses', 'training academy', 'school of nursing',
    'software development', 'web design agency', 'digital marketing agency',
]

# ---------------------------------------------------------------------------
def check_key():
    if not API_KEY:
        print("ERROR: FIRECRAWL_API_KEY not set. See setup in script docstring.")
        sys.exit(1)

def fc_post(path, body, timeout=120):
    """Generic Firecrawl POST with retry."""
    url = f'{BASE}{path}'
    headers = {'Authorization': f'Bearer {API_KEY}',
               'Content-Type': 'application/json'}
    for attempt in range(3):
        try:
            r = requests.post(url, headers=headers, json=body, timeout=timeout)
            if r.status_code == 429:
                time.sleep(2 ** attempt); continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == 2: raise
            time.sleep(1 + attempt)
    return {}

# ---------------------------------------------------------------------------
# MODE A — /scrape + local keyword detection
# ---------------------------------------------------------------------------
def scrape_one(url):
    """Hit /scrape, return cleaned markdown + simple page metadata."""
    res = fc_post('/scrape', {
        'url':              url,
        'formats':          ['markdown'],
        'onlyMainContent':  True,
        'waitFor':          1000,    # wait 1s for JS to settle
        'timeout':          30000,
    })
    data = (res or {}).get('data', {}) or res
    md = data.get('markdown', '') or ''
    meta = data.get('metadata', {}) or {}
    return md, meta

def classify_local(name, markdown, meta):
    """Run keyword detection on the scraped page text."""
    text = (markdown + ' ' + (meta.get('title', '') or '') + ' '
            + (meta.get('description', '') or '')).lower()
    nl = (name or '').lower().strip()
    name_clean = re.sub(r'\s+(limited|ltd\.?|plc|llp)$', '', nl, flags=re.I).strip()

    name_match = bool(name_clean and (name_clean in text or
                                       name_clean.replace(' ', '') in text.replace(' ', '')))
    housing = [k for k in HOUSING_KEYWORDS if k in text]
    negative = [k for k in NON_HOUSING_TERMS if k in text]

    # Extract emails/phones from markdown
    emails = list({m for m in re.findall(r'[\w.+-]+@[\w.-]+\.\w+', markdown)
                   if 'example.com' not in m and '@2x' not in m})[:5]
    phones = list({m for m in re.findall(
        r'(?:\+?44|0)\s?\d{2,4}[\s-]?\d{3,4}[\s-]?\d{3,4}', markdown)})[:3]

    if negative and not housing:
        verdict = 'DROP'
    elif housing:
        verdict = 'KEEP'
    elif name_match:
        verdict = 'UNCLEAR'
    else:
        verdict = 'NEEDS_SEARCH'

    return {
        'name_match':    name_match,
        'housing_terms': housing,
        'non_housing':   negative,
        'emails':        emails,
        'phones':        phones,
        'address':       '',
        'verdict':       verdict,
        'mode':          'scrape',
        'checked_at':    time.strftime('%Y-%m-%d'),
    }

def cmd_scrape(limit=None):
    check_key()
    prov = json.load(open('api/_data/providers.json', encoding='utf-8'))
    cache = json.load(open(OUT, encoding='utf-8')) if OUT.exists() else {}
    todo = [p for p in prov if p.get('website') and p['name'] not in cache]
    if limit: todo = todo[:limit]
    print(f"Cached: {len(cache)}.  To scrape (mode A): {len(todo)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(todo, 1):
        try:
            md, meta = scrape_one(p['website'])
            res = classify_local(p['name'], md, meta)
            res['url'] = p['website']
            cache[p['name']] = res
            tag = res['verdict']
            print(f"  [{i:>4d}/{len(todo)}] {tag:<14s}"
                  f" hits={len(res['housing_terms']):>2d}"
                  f" name_match={'Y' if res['name_match'] else 'N'}"
                  f"  {p['name'][:42]}")
        except Exception as e:
            cache[p['name']] = {'url': p.get('website',''), 'verdict':'ERROR',
                                'error': str(e)[:120], 'mode':'scrape',
                                'checked_at': time.strftime('%Y-%m-%d')}
            print(f"  [{i:>4d}/{len(todo)}] ERROR  {p['name']}: {e}")
        if i % 20 == 0:
            json.dump(cache, open(OUT, 'w', encoding='utf-8'), indent=2)
        time.sleep(0.3)
    json.dump(cache, open(OUT, 'w', encoding='utf-8'), indent=2)
    print(f"\nDone. Total cached: {len(cache)}")

# ---------------------------------------------------------------------------
# MODE B — /extract with JSON schema (LLM-judged verdict)
# ---------------------------------------------------------------------------
EXTRACT_SCHEMA = {
    'type': 'object',
    'properties': {
        'company_name_on_site':   {'type': 'string',
            'description': 'The trading name / brand shown most prominently'},
        'ltd_company_name_match': {'type': 'boolean',
            'description': 'Does the provided limited company name appear anywhere on the site?'},
        'offers_supported_living':{'type': 'boolean',
            'description': 'Does this organisation operate or provide ANY of: supported living, supported accommodation, supported housing, residential care, care home, nursing home, asylum accommodation, homelessness, refuge, hostel, sheltered housing, care for young people 16+, mental health accommodation, semi-independent accommodation, temporary accommodation? Mixed providers count — answer true if any of these appear anywhere as a real service offering (even alongside homecare/domiciliary work).'},
        'services':              {'type': 'array', 'items': {'type': 'string'},
            'description': 'List of distinct services offered (e.g. ["supported living", "domiciliary care"])'},
        'is_unrelated_business': {'type': 'boolean',
            'description': 'Is this site clearly NOT a housing/care provider (e.g. takeaway, vet, builder, software company, retail)?'},
        'email':                 {'type': 'string'},
        'phone':                 {'type': 'string'},
        'address':               {'type': 'string'},
        'contact_page_url':      {'type': 'string',
            'description': 'Full URL of the Contact Us / Get in Touch page on this site, if one exists. Use the absolute URL (https://...). This is used as a fallback when no email address is visible.'},
        'companies_house_number':{'type': 'string',
            'description': 'UK Companies House number mentioned on the site (e.g. "12345678") if visible'},
    },
}

def extract_one(url, name):
    """Use Firecrawl /extract on homepage + sub-pages for fuller signal.

    We submit FIVE URL patterns per provider so the LLM sees:
      - the homepage (brand, services)
      - the contact page (email, phone, address)
      - the about page (company name, Companies House number)
      - the services page (what they actually do)
      - the supported-living page (specific category match)

    Firecrawl skips 404s automatically. Most sites have at least 3 of these.
    Cost: 5 credits per provider vs 1 credit for homepage-only,
    but contact extraction goes from ~40% coverage to ~90%+.
    """
    base = url.rstrip('/')
    # 3-URL minimum-viable: homepage + most-likely contact + about
    # Drops scrape time ~3x vs the 8-URL crawl while still hitting the
    # pages that hold email, phone, address, and CH number.
    urls = [
        url,
        f"{base}/contact-us",
        f"{base}/about-us",
    ]
    body = {
        'urls':   urls,
        'prompt': (f"You are verifying that this UK website belongs to the "
                   f"limited company '{name}' AND that the organisation offers "
                   f"housing-related services. Mixed providers (homecare AND "
                   f"supported living) count as housing — answer 'true' to "
                   f"offers_supported_living if ANY housing-type service is "
                   f"mentioned anywhere across the pages. Look hard at the "
                   f"contact and about pages for email, phone, address, and "
                   f"Companies House number. Some pages may 404 — that's OK, "
                   f"use whatever pages did load."),
        'schema': EXTRACT_SCHEMA,
    }
    return fc_post('/extract', body, timeout=240)

def classify_extracted(name, extracted):
    """Turn the structured extraction into our verdict shape."""
    d = extracted or {}
    name_match = bool(d.get('ltd_company_name_match'))
    offers = bool(d.get('offers_supported_living'))
    unrelated = bool(d.get('is_unrelated_business'))
    services = d.get('services') or []
    if unrelated and not offers:
        verdict = 'DROP'
    elif offers:
        verdict = 'KEEP'
    elif name_match:
        verdict = 'UNCLEAR'
    else:
        verdict = 'NEEDS_SEARCH'
    return {
        'name_match':    name_match,
        'housing_terms': services if offers else [],
        'non_housing':   ['flagged unrelated by LLM'] if unrelated else [],
        'emails':        [d['email']] if d.get('email') else [],
        'phones':        [d['phone']] if d.get('phone') else [],
        'address':       d.get('address', ''),
        'contact_page':  d.get('contact_page_url', ''),
        'ch_number':     d.get('companies_house_number', ''),
        'site_name':     d.get('company_name_on_site', ''),
        'verdict':       verdict,
        'mode':          'extract',
        'checked_at':    time.strftime('%Y-%m-%d'),
    }

def cmd_extract(limit=None, workers=8, batch_size=300):
    """Run /extract in parallel with N concurrent workers.

    Saves the JSON cache to disk after EVERY provider (zero data loss risk).
    Calls the auto-apply step every `batch_size` providers so VERIFIED.json
    and manual_contracts.xlsx get updated incrementally — if the run stops
    mid-way, what's already processed is already locked in.
    All print output uses flush=True (no Python buffering).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading, subprocess
    check_key()
    prov = json.load(open('api/_data/providers.json', encoding='utf-8'))
    cache = json.load(open(OUT, encoding='utf-8')) if OUT.exists() else {}
    todo = [p for p in prov if p.get('website')
            and (p['name'] not in cache or cache[p['name']].get('mode') != 'extract')]
    if limit: todo = todo[:limit]
    print(f"To /extract (mode B, {workers} workers, batch={batch_size}): {len(todo)}", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    done_count = [0]
    last_apply = [0]   # last point at which we ran the apply step

    def save_cache():
        json.dump(cache, open(OUT, 'w', encoding='utf-8'), indent=2)

    def maybe_apply():
        # Run apply_firecrawl.py if we've added another batch_size since last apply
        if done_count[0] - last_apply[0] >= batch_size:
            last_apply[0] = done_count[0]
            print(f"  --- batch checkpoint: applying {batch_size} verdicts ---", flush=True)
            try:
                subprocess.run(
                    ['python', 'scripts/apply_firecrawl.py'],
                    check=False, timeout=120,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                print(f"  --- batch applied: {done_count[0]} total processed ---", flush=True)
            except Exception as e:
                print(f"  --- batch apply failed: {e} ---", flush=True)

    def process(p):
        try:
            raw = extract_one(p['website'], p['name'])
            if raw.get('data'):
                extracted = raw['data'] if isinstance(raw['data'], dict) else raw['data'][0]
            elif raw.get('id'):
                extracted = poll_extract(raw['id'])
            else:
                extracted = {}
            res = classify_extracted(p['name'], extracted)
            res['url'] = p['website']
            with lock:
                cache[p['name']] = res
                done_count[0] += 1
                save_cache()                                   # save after every provider
                i = done_count[0]
                print(f"  [{i:>4d}/{len(todo)}] {res['verdict']:<14s}"
                      f"  {p['name'][:42]}  {res['housing_terms'][:2]}", flush=True)
                maybe_apply()
        except Exception as e:
            with lock:
                cache[p['name']] = {'url': p.get('website',''), 'verdict':'ERROR',
                                    'error': str(e)[:120], 'mode':'extract',
                                    'checked_at': time.strftime('%Y-%m-%d')}
                done_count[0] += 1
                save_cache()
                print(f"  [{done_count[0]:>4d}/{len(todo)}] ERROR  {p['name']}: {str(e)[:60]}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(process, p) for p in todo]
        for f in as_completed(futures):
            f.result()

    save_cache()
    # final apply
    try:
        subprocess.run(['python', 'scripts/apply_firecrawl.py'], check=False, timeout=120)
    except Exception as e:
        print(f"final apply failed: {e}", flush=True)
    print(f"\nDone. Total cached: {len(cache)}", flush=True)

def poll_extract(job_id, max_wait=120):
    """Some /extract responses are async — poll until done."""
    headers = {'Authorization': f'Bearer {API_KEY}'}
    deadline = time.time() + max_wait
    while time.time() < deadline:
        r = requests.get(f'{BASE}/extract/{job_id}', headers=headers, timeout=15)
        if r.status_code != 200:
            time.sleep(2); continue
        d = r.json()
        if d.get('status') == 'completed':
            return d.get('data', {}) or {}
        if d.get('status') in {'failed', 'cancelled'}:
            return {}
        time.sleep(2)
    return {}

# ---------------------------------------------------------------------------
def cmd_status():
    if not OUT.exists(): print("No Firecrawl runs yet."); return
    d = json.load(open(OUT, encoding='utf-8'))
    from collections import Counter
    verdicts = Counter(v.get('verdict','?') for v in d.values())
    modes    = Counter(v.get('mode','?') for v in d.values())
    print(f"Total: {len(d)}")
    print("Verdicts:")
    for v, n in verdicts.most_common(): print(f"  {v}: {n}")
    print("Modes:")
    for m, n in modes.most_common(): print(f"  {m}: {n}")

# ---------------------------------------------------------------------------
if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'scrape'
    n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else None
    if   cmd == 'scrape':   cmd_scrape(n)
    elif cmd == 'extract':  cmd_extract(n)
    elif cmd == 'status':   cmd_status()
    else:                   print(__doc__)
