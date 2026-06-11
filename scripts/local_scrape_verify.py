"""Local Firecrawl/Apify-equivalent verifier.

Stack designed to match Firecrawl + Apify capabilities at zero cost:
  • cloudscraper       — bypasses Cloudflare bot-challenges
  • fake-useragent     — rotates real browser user-agent strings
  • duckduckgo-search  — find websites by name (no captcha, no key)
  • Playwright (Chromium) — fallback for JS-rendered SPAs that block plain HTTP
  • beautifulsoup4     — clean HTML→text extraction
  • Random delays + retry logic — looks like a human

Per supplier name we:
  1. Search DuckDuckGo: "<Name> supported living UK"
  2. Pick the best UK result (skip directories, careers boards, social media)
  3. Multi-page fetch: homepage + /contact-us + /about-us + /services + /supported-living
  4. If a fetch is blocked, fall back to Playwright with stealth headers
  5. Combine text across all pages → classify with context-aware keyword matching
  6. Extract emails / phones / Companies House number via regex
  7. Write same verdict shape as firecrawl_analysed.json so existing apply scripts work

USAGE:
  python scripts/local_scrape_verify.py path/to/names.json [--workers N]

The script auto-skips names already in firecrawl_analysed.json with a non-ERROR
verdict — so it picks up exactly where Firecrawl left off (the 1,335 ERROR ones).
"""
import os, sys, json, time, re, random, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse, urljoin

import cloudscraper
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from duckduckgo_search import DDGS

ANALYSED   = Path('data/verification/firecrawl_analysed.json')
DISCOVERED = Path('data/verification/firecrawl_discovered_urls.json')

# Reuse the same housing/non-housing vocabularies as the rest of the pipeline
HOUSING_TERMS = [
    'supported living', 'assisted living', 'supported accommodation',
    'supported housing', 'extra care', 'residential care', 'care home',
    'nursing home', 'asylum accommodation', 'asylum', 'homelessness', 'homeless',
    'refuge', 'hostel', 'sheltered housing', 'sheltered accommodation',
    'care leaver', 'leaving care', "children's home", 'children home',
    'looked after children', 'looked-after', 'mental health accommodation',
    'transitional accommodation', 'semi-independent', 'rough sleeping',
    'temporary accommodation', 'crisis accommodation', 'housing first',
    'domestic abuse refuge', 'domestic abuse', 'modern slavery',
    'family accommodation', 'tenancy support', 'tenancy sustainment',
    'shared lives', 'housing-related support', 'housing related support',
    'floating support', 'short-term assessment', 'assessment bed',
    'placements', 'day service', 'day opportunit', 'ageing well',
]
HOMECARE_TERMS = [
    'homecare', 'home care', 'home-care', 'domiciliary',
    'in your own home', 'in the comfort of your home',
    'live-in care', 'live in care', 'in-home', 'visiting care',
    'personal care at home',
]
NON_HOUSING_NEGATIVES = [
    'pizza takeaway', 'restaurant menu', 'food delivery',
    'veterinary practice', 'animal hospital', 'pet clinic',
    'plumbing services', 'heating engineer', 'gas safe registered',
    'plastics manufacturing', 'packaging supplier',
    'department store', 'clothing retailer',
    'recruitment agency only', 'staffing agency only',
    'training courses only', 'software development agency',
    'web design agency', 'digital marketing agency',
    'building company', 'civil engineering',
]

# Sub-pages worth visiting for context (matches Firecrawl's pattern)
SUBPAGE_KEYWORDS = (
    'contact', 'about', 'services', 'what-we-do',
    'supported-living', 'supported-accommodation', 'accommodation',
    'who-we-are', 'our-services',
)

UA = UserAgent()
# Skip these domains in search results — they're directories / social, not
# the company's own site.
DOMAIN_BLOCKLIST = (
    'linkedin.com', 'facebook.com', 'instagram.com', 'twitter.com',
    'youtube.com', 'tiktok.com', 'reddit.com', 'pinterest.com',
    'glassdoor.com', 'indeed.com', 'reed.co.uk', 'totaljobs.com',
    'bebee.com', 'jobs.', 'careers.',
    'cqc.org.uk',                                 # CQC directory
    'find-and-update.company-information',        # Companies House
    'gov.uk', 'data.gov.uk', 'find-a-tender',
    'carechoices.co.uk', 'autumna.co.uk', 'homecare.co.uk',
    'connecttosupport', 'patient.info', 'nhs.uk/services',
    'yelp', 'tripadvisor', 'trustpilot',
    'consolidate.org.uk',                         # contract aggregator
    'in-tendhost', 'londontenders',
    'wikipedia.org',
)

def scraper():
    """Build a fresh cloudscraper session with a randomised UA."""
    s = cloudscraper.create_scraper(
        browser={'browser':'chrome','platform':'windows','mobile':False})
    s.headers.update({'User-Agent': UA.random,
                      'Accept-Language': 'en-GB,en;q=0.9',
                      'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'})
    return s

# ── 1. Search by name ─────────────────────────────────────────────────────────
def search_company(name):
    """DuckDuckGo HTML search for the company's actual website."""
    import re as _re
    q = _re.sub(r'\s+(Limited|Ltd\.?|PLC|LLP|CIC)$','', name, flags=_re.I).strip()
    query = f'"{q}" supported living OR residential care OR housing UK'
    try:
        with DDGS() as ddg:
            results = list(ddg.text(query, region='uk-en', max_results=6))
        if not results: return None
        # Score results
        def good(r):
            url = (r.get('href') or '').lower()
            if any(b in url for b in DOMAIN_BLOCKLIST): return -10
            score = 0
            if '.co.uk' in url or '.org.uk' in url: score += 3
            host = urlparse(url).netloc.lower()
            slug = q.lower().replace(' ','').replace('-','')[:10]
            if slug and slug in host.replace('-','').replace('.',''): score += 5
            t = (r.get('title','') + ' ' + r.get('body','')).lower()
            if q.lower() in t: score += 2
            return score
        results.sort(key=good, reverse=True)
        best = results[0]
        if good(best) < 0: return None
        return {'url': best['href'], 'title': best.get('title','')}
    except Exception as e:
        return None

# ── 2. Fetch one page — cloudscraper first, Playwright fallback ───────────────
def fetch_text(sess, url, timeout=15):
    """Returns (text, fetched_url, html_len) or (None, None, 0).
       cloudscraper handles ~80% of sites; Playwright the rest."""
    try:
        r = sess.get(url, timeout=timeout, allow_redirects=True)
        if r.status_code == 200 and r.text and len(r.text) > 1000:
            soup = BeautifulSoup(r.text, 'html.parser')
            for tag in soup(['script','style','noscript']): tag.decompose()
            txt = re.sub(r'\s+',' ', soup.get_text(' ')).strip()
            return txt[:20000], r.url, len(r.text)
    except Exception:
        pass
    return None, None, 0

def fetch_with_playwright(url, timeout=25):
    """For sites that blocked cloudscraper, use a real browser."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True,
                args=['--disable-blink-features=AutomationControlled'])
            ctx = browser.new_context(user_agent=UA.random, locale='en-GB',
                                       viewport={'width':1366,'height':768})
            page = ctx.new_page()
            page.goto(url, timeout=timeout*1000, wait_until='domcontentloaded')
            page.wait_for_timeout(800)
            txt = page.evaluate('document.body.innerText')
            html = page.content()
            browser.close()
            return (re.sub(r'\s+',' ', txt or '').strip()[:20000],
                    url, len(html or ''))
    except Exception:
        return None, None, 0

# ── 3. Multi-page crawl ───────────────────────────────────────────────────────
def crawl(url, max_pages=5):
    """Fetch homepage + up to N relevant sub-pages."""
    sess = scraper()
    pages = []
    text_home, real_url, _ = fetch_text(sess, url)
    if not text_home:
        text_home, real_url, _ = fetch_with_playwright(url)
    if not text_home: return []
    pages.append({'url': real_url, 'kind':'home', 'text': text_home})

    # Parse links for sub-pages
    try:
        r = sess.get(real_url, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        seen = {real_url}
        candidates = []
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if not href or href.startswith(('#','mailto:','tel:')): continue
            try: abs_u = urljoin(real_url, href)
            except: continue
            if urlparse(abs_u).netloc != urlparse(real_url).netloc: continue
            path = urlparse(abs_u).path.lower()
            for kw in SUBPAGE_KEYWORDS:
                if kw in path and abs_u not in seen:
                    candidates.append((abs_u, kw)); seen.add(abs_u); break
            if len(candidates) >= max_pages - 1: break
    except Exception:
        candidates = []

    for u, kind in candidates[:max_pages-1]:
        time.sleep(random.uniform(0.4, 0.9))
        t, _, _ = fetch_text(sess, u)
        if t: pages.append({'url':u, 'kind':kind, 'text':t})
    return pages

# ── 4. Classify — context-aware keyword matching ──────────────────────────────
def classify(pages, name):
    combined = ' '.join(p['text'] for p in pages).lower()
    name_clean = re.sub(r'\s+(limited|ltd|plc|llp|cic)$','', name.lower()).strip()
    name_match = bool(name_clean and (name_clean in combined or
                                       name_clean.replace(' ','') in combined.replace(' ','')))

    # Context-aware: only count a housing match if NOT preceded by a negator
    NEGATORS = (' not ', ' no longer ', ' previously ', ' former ', ' do not ',
                ' does not ', " don't ", " doesn't ", ' help leaving ', ' help leave ')
    def has_term(term):
        i = combined.find(term)
        while i != -1:
            window = combined[max(0,i-50):i].lower()
            if not any(n in window for n in NEGATORS):
                return True
            i = combined.find(term, i+len(term))
        return False

    housing_hits = [t for t in HOUSING_TERMS if has_term(t)]
    homecare_hits = [t for t in HOMECARE_TERMS if has_term(t)]
    negative_hits = [t for t in NON_HOUSING_NEGATIVES if t in combined]

    # Contacts
    emails = list({m for m in re.findall(r'[\w.+-]+@[\w.-]+\.\w+', combined)
                    if 'example.com' not in m and '@2x' not in m})[:5]
    phones = list({m for m in re.findall(
        r'(?:\+?44|0)\s?\d{2,4}[\s-]?\d{3,4}[\s-]?\d{3,4}', combined)})[:3]
    contact_page = next((p['url'] for p in pages if 'contact' in p['kind']), '')

    # Companies House number on site
    ch = ''
    m = re.search(r'company\s*(?:no\.?|number|registration\s*no\.?)\s*[:#]?\s*(\d{6,8})',
                  combined, re.I)
    if m: ch = m.group(1)

    # Verdict — 80%+ CONFIDENCE rule.
    # Only mark a provider as KEEP (→ Verified badge on paid site) when we have
    # ALL of:
    #   1. Name match — the company name actually appears somewhere on the page
    #      (prevents using a different company's website by accident)
    #   2. At least one housing service keyword present
    #   3. At least one contact channel captured (email OR phone OR contact_page)
    #      — without these, the customer can't reach the provider so the
    #         record is useless even if real
    #
    # Anything less rigorous is left UNCLEAR or NEEDS_SEARCH — they stay
    # Listed (grey chip), customers can use the "Verified only" filter to
    # hide them.
    has_contact = bool(emails or phones or contact_page)
    if negative_hits and not housing_hits:
        verdict = 'DROP'
    elif name_match and housing_hits and has_contact:
        verdict = 'KEEP'                         # ✓ all 3 criteria met
    elif name_match and homecare_hits and not housing_hits:
        verdict = 'DROP'                         # explicit homecare-only
    elif name_match and housing_hits and not has_contact:
        verdict = 'UNCLEAR'                      # right co + housing but no contacts
    elif housing_hits and not name_match:
        verdict = 'NEEDS_SEARCH'                 # right keywords, wrong site
    elif name_match:
        verdict = 'UNCLEAR'                      # site is theirs but services unclear
    else:
        verdict = 'NEEDS_SEARCH'                 # neither name nor housing

    return {
        'name_match':    name_match,
        'housing_terms': housing_hits,
        'non_housing':   negative_hits + (homecare_hits if not housing_hits else []),
        'emails':        emails,
        'phones':        phones,
        'contact_page':  contact_page,
        'ch_number':     ch,
        'address':       '',
        'verdict':       verdict,
        'mode':          'local_scrape',
        'checked_at':    time.strftime('%Y-%m-%d'),
    }

# ── 5. Per-name pipeline ──────────────────────────────────────────────────────
def url_is_garbage(url):
    """True if URL is a directory / social / forum we shouldn't trust."""
    if not url: return True
    u = url.lower()
    return any(b in u for b in DOMAIN_BLOCKLIST)

def process_one(name, discovered, analysed, lock, counter, total):
    try:
        # Step 1: discover URL — re-search if cached URL is garbage
        with lock:
            disc = discovered.get(name)
        cached_url = (disc or {}).get('url')
        if cached_url and not url_is_garbage(cached_url):
            url = cached_url
        else:
            disc = search_company(name)
            with lock:
                discovered[name] = disc or {}
                json.dump(discovered, open(DISCOVERED,'w', encoding='utf-8'), indent=2)
            if not disc or not disc.get('url') or url_is_garbage(disc.get('url','')):
                with lock:
                    analysed[name] = {'url':'', 'verdict':'NO_URL',
                                      'mode':'local_scrape', 'notes':'no real website found',
                                      'checked_at': time.strftime('%Y-%m-%d')}
                    counter[0] += 1
                    json.dump(analysed, open(ANALYSED,'w', encoding='utf-8'), indent=2)
                    print(f"  [{counter[0]:>4d}/{total}] NO_URL  {name[:48]}", flush=True)
                return
            url = disc['url']

        # Step 2: crawl
        pages = crawl(url, max_pages=4)
        if not pages:
            with lock:
                analysed[name] = {'url':url, 'verdict':'BLOCKED',
                                  'mode':'local_scrape', 'notes':'all pages blocked',
                                  'checked_at': time.strftime('%Y-%m-%d')}
                counter[0] += 1
                json.dump(analysed, open(ANALYSED,'w', encoding='utf-8'), indent=2)
                print(f"  [{counter[0]:>4d}/{total}] BLOCKED {name[:48]}", flush=True)
            return

        # Step 3: classify
        res = classify(pages, name)
        res['url'] = pages[0]['url']
        res['notes'] = f"local scrape; {len(pages)} pages from {disc.get('title','')[:40]}"
        with lock:
            analysed[name] = res
            counter[0] += 1
            json.dump(analysed, open(ANALYSED,'w', encoding='utf-8'), indent=2)
            print(f"  [{counter[0]:>4d}/{total}] {res['verdict']:<13s}"
                  f"  {name[:42]}  ->  {pages[0]['url'][:35]}", flush=True)
    except Exception as e:
        with lock:
            analysed[name] = {'url':'', 'verdict':'ERROR',
                              'error': str(e)[:120],
                              'mode':'local_scrape',
                              'checked_at': time.strftime('%Y-%m-%d')}
            counter[0] += 1
            json.dump(analysed, open(ANALYSED,'w', encoding='utf-8'), indent=2)
            print(f"  [{counter[0]:>4d}/{total}] ERROR   {name}: {str(e)[:60]}", flush=True)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    name_file = sys.argv[1]
    workers = 6
    for i, a in enumerate(sys.argv):
        if a == '--workers' and i+1 < len(sys.argv):
            workers = int(sys.argv[i+1])

    names = json.load(open(name_file, encoding='utf-8'))
    analysed   = json.load(open(ANALYSED, encoding='utf-8')) if ANALYSED.exists() else {}
    discovered = json.load(open(DISCOVERED, encoding='utf-8')) if DISCOVERED.exists() else {}

    # Only process names not already cached with a non-ERROR verdict
    todo = [n for n in names
            if (n not in analysed)
            or analysed.get(n,{}).get('verdict') in ('ERROR','BLOCKED')
            or not analysed.get(n,{}).get('verdict')]
    print(f"Names in file:           {len(names)}")
    print(f"To process (new+retry):  {len(todo)}", flush=True)
    print(f"Already cached (skip):   {len(names)-len(todo)}", flush=True)

    lock = threading.Lock()
    counter = [0]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(process_one, n, discovered, analysed, lock, counter, len(todo))
                   for n in todo]
        for f in as_completed(futures):
            f.result()

    print(f"\nDone. Cached: {len(analysed)}", flush=True)

if __name__ == '__main__':
    main()
