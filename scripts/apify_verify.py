"""Apify bulk website verification.

Runs an Apify Cheerio Scraper against every provider's stored website,
extracts page text + contact info, and saves results for offline analysis.

This is the scalable verification path — Apify scrapes all 1,792 sites in
parallel in one job (~5-10 minutes, ~$1-2 total).

SETUP:
  1. Sign up at https://apify.com (free tier covers ~1,000 page loads/month)
  2. Create an API token under Settings → Integrations
  3. Set environment variable:  $env:APIFY_TOKEN = "your-token"

USAGE:
  python scripts/apify_verify.py submit       # submit a new bulk job
  python scripts/apify_verify.py status <id>  # check job status
  python scripts/apify_verify.py fetch  <id>  # download results when finished
  python scripts/apify_verify.py analyse      # classify each scraped page

OUTPUT:
  data/verification/apify_run_<runId>.json    # raw scrape output
  data/verification/apify_analysed.json       # classification per provider
"""
import os, sys, json, time
from pathlib import Path
import requests

APIFY_TOKEN = os.environ.get('APIFY_TOKEN', '')
APIFY_BASE  = 'https://api.apify.com/v2'
ACTOR_ID    = 'apify~cheerio-scraper'   # generic Cheerio scraper
OUT_DIR     = Path('data/verification')

# ---------------------------------------------------------------------------
# Page-text classification — what counts as a housing/care provider?
# ---------------------------------------------------------------------------
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
    'pizza', 'takeaway', 'restaurant',
    'veterinary practice', 'animal hospital', 'pet clinic',
    'plumbing services', 'heating engineer',
    'plastics manufacturing', 'packaging supplier',
    'department store', 'retail outlet',
    'recruitment agency', 'staffing solutions', 'temp agency',
    'training courses', 'training academy', 'school of nursing',
    'software development', 'web design agency', 'digital marketing',
]

def check_token():
    if not APIFY_TOKEN:
        print("ERROR: APIFY_TOKEN not set. See setup instructions in script docstring.")
        sys.exit(1)

# ---------------------------------------------------------------------------
def cmd_submit():
    """Submit a new run that scrapes every provider's homepage + key sub-pages.

    For each provider we crawl up to 5 pages:
      1. The homepage
      2. /services / /what-we-do / similar
      3. /supported-living, /accommodation, /supported-housing
      4. /about / /about-us
      5. /contact / /contact-us

    Keyword detection runs across the combined text of all crawled pages —
    so even if 'supported living' is buried on /services/supported-living/
    we'll catch it.
    """
    check_token()
    prov = json.load(open('api/_data/providers.json', encoding='utf-8'))
    urls = [{'url': p['website']} for p in prov if p.get('website')]
    print(f"Submitting Apify job for {len(urls)} start URLs (5 pages each)...")

    # Cheerio Scraper input: pageFunction returns text + extracted contacts.
    # Also ENQUEUES links matching key sub-page patterns from the homepage.
    page_fn = r"""
async function pageFunction(context) {
  const { request, $, enqueueRequest, log } = context;
  const isStartPage = (request.userData?.depth || 0) === 0;

  // From the homepage, enqueue up to 4 promising sub-pages (services,
  // supported living, about, contact). Subsequent pages don't enqueue further.
  if (isStartPage) {
    const SUB_KEYWORDS = [
      'service','what-we-do','supported-living','supported-housing',
      'supported-accommodation','accommodation','what-we-offer',
      'about','about-us','who-we-are','contact','contact-us'
    ];
    const seen = new Set();
    let added = 0;
    $('a[href]').each((_, el) => {
      if (added >= 4) return false;
      const href = ($(el).attr('href') || '').trim();
      if (!href || href.startsWith('#') || href.startsWith('mailto:')) return;
      let abs;
      try { abs = new URL(href, request.url).href; } catch { return; }
      // Same host only
      try {
        if (new URL(abs).host !== new URL(request.url).host) return;
      } catch { return; }
      const path = (new URL(abs).pathname || '').toLowerCase();
      const matched = SUB_KEYWORDS.find(k => path.includes(k));
      if (!matched) return;
      if (seen.has(abs)) return;
      seen.add(abs);
      enqueueRequest({ url: abs, userData: { depth: 1, parent: request.url, kind: matched }});
      added++;
    });
  }

  const txt = $('body').text().replace(/\s+/g, ' ').slice(0, 8000);
  const emails = ($('body').html().match(/[\w.+-]+@[\w.-]+\.\w+/g) || [])
                  .filter(e => !e.includes('example.com') && !e.includes('@2x'))
                  .slice(0, 5);
  const phones = (txt.match(/(?:\+?44|0)\s?\d{2,4}[\s-]?\d{3,4}[\s-]?\d{3,4}/g) || []).slice(0,3);
  const contactLink = $('a[href*="contact"]').attr('href') || '';
  const companyName = $('title').text() || $('h1').first().text() || '';

  return {
    url:        request.url,
    parent:     request.userData?.parent || request.url,  // groups sub-pages
    depth:      request.userData?.depth || 0,
    page_kind:  request.userData?.kind || 'home',
    title:      companyName.trim().slice(0, 120),
    text:       txt,
    emails, phones,
    contact_url: contactLink,
  };
}
"""
    body = {
        'startUrls':   urls,
        'pageFunction': page_fn,
        'maxConcurrency': 25,
        # Cap total pages to bound cost: 5 pages per start URL.
        'maxRequestsPerCrawl': len(urls) * 5 + 20,
        'preNavigationHooks': '[]',
        'postNavigationHooks': '[]',
        'maxRequestRetries': 1,
        # Crawl extra pages enqueued by pageFunction, depth-capped to 1.
        'maxPagesPerCrawl': len(urls) * 5,
    }
    url = f'{APIFY_BASE}/acts/{ACTOR_ID}/runs?token={APIFY_TOKEN}'
    r = requests.post(url, json=body, timeout=30)
    r.raise_for_status()
    run = r.json()['data']
    print(f"\n✓ Submitted.")
    print(f"  Run ID:  {run['id']}")
    print(f"  Status:  {run['status']}")
    print(f"  Watch:   https://console.apify.com/runs/{run['id']}")
    print(f"\nWhen finished, run:")
    print(f"  python scripts/apify_verify.py fetch {run['id']}")
    return run['id']

def cmd_status(run_id):
    check_token()
    r = requests.get(f'{APIFY_BASE}/actor-runs/{run_id}?token={APIFY_TOKEN}', timeout=15)
    r.raise_for_status()
    d = r.json()['data']
    print(f"Run {run_id}")
    print(f"  Status:       {d['status']}")
    print(f"  Started:      {d.get('startedAt','-')}")
    print(f"  Finished:     {d.get('finishedAt','-')}")
    print(f"  Pages scraped:{d.get('stats',{}).get('requestsFinished','-')}")

def cmd_fetch(run_id):
    """Download dataset items from a finished run."""
    check_token()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    r = requests.get(f'{APIFY_BASE}/actor-runs/{run_id}?token={APIFY_TOKEN}', timeout=15)
    r.raise_for_status()
    dataset_id = r.json()['data']['defaultDatasetId']
    items = []
    offset = 0
    while True:
        u = f'{APIFY_BASE}/datasets/{dataset_id}/items?token={APIFY_TOKEN}&offset={offset}&limit=1000&clean=1'
        r = requests.get(u, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch: break
        items.extend(batch)
        offset += len(batch)
        if len(batch) < 1000: break
    out = OUT_DIR / f'apify_run_{run_id}.json'
    json.dump(items, open(out, 'w', encoding='utf-8'), indent=2)
    print(f"✓ Saved {len(items)} pages -> {out}")

def classify_page(item, expected_name):
    """Score one scraped page against the expected company name."""
    text = (item.get('text', '') + ' ' + item.get('title', '')).lower()
    nl = (expected_name or '').lower()

    # Step 1 — does the page mention the company name?
    name_match = nl and (nl in text or nl.replace(' limited', '').replace(' ltd', '').strip() in text)

    # Step 3 — does it offer housing services?
    matched_housing = [k for k in HOUSING_KEYWORDS if k in text]
    matched_negative = [k for k in NON_HOUSING_TERMS if k in text]

    # Verdict logic
    if matched_negative and not matched_housing:
        verdict = 'DROP'  # clearly an unrelated business
    elif matched_housing:
        verdict = 'KEEP'  # offers at least one housing service
    elif name_match:
        verdict = 'UNCLEAR'  # right business but services unclear
    else:
        verdict = 'NEEDS_SEARCH'  # name doesn't match this site at all

    return {
        'name_match': bool(name_match),
        'housing_terms': matched_housing,
        'non_housing_terms': matched_negative,
        'emails': item.get('emails', []),
        'phones': item.get('phones', []),
        'contact_url': item.get('contact_url', ''),
        'verdict': verdict,
    }

def cmd_analyse():
    """Read every apify_run_*.json and classify each provider.

    Each provider has 1-5 pages crawled (home + sub-pages). We aggregate the
    text across all of them before running keyword detection. This catches
    providers whose homepage emphasises homecare but who advertise supported
    living on /services/supported-living/.
    """
    runs = sorted(OUT_DIR.glob('apify_run_*.json'))
    if not runs:
        print("No Apify runs found. Submit one first."); return

    # Group items by parent (start URL of the homepage that triggered them)
    by_parent = {}
    for f in runs:
        for item in json.load(open(f, encoding='utf-8')):
            parent = item.get('parent') or item.get('url', '')
            for variant in {parent, parent.rstrip('/'), parent + '/'}:
                by_parent.setdefault(variant, []).append(item)

    def aggregate(items):
        """Merge text + contacts across pages."""
        sorted_items = sorted(items, key=lambda x: x.get('depth', 0))
        return {
            'url':          items[0].get('parent') or items[0].get('url',''),
            'title':        sorted_items[0].get('title',''),
            'text':         ' \n '.join(i.get('text','') for i in items)[:30000],
            'emails':       list({e for i in items for e in (i.get('emails') or [])})[:5],
            'phones':       list({p for i in items for p in (i.get('phones') or [])})[:3],
            'contact_url':  next((i.get('contact_url','') for i in items if i.get('contact_url')), ''),
            'pages_crawled':[{'kind': i.get('page_kind','home'), 'url': i.get('url','')} for i in items],
        }

    prov = json.load(open('api/_data/providers.json', encoding='utf-8'))
    out = {}
    for p in prov:
        u = p.get('website', '')
        if not u: continue
        items = (by_parent.get(u) or by_parent.get(u.rstrip('/'))
                 or by_parent.get(u + '/'))
        if not items: continue
        agg = aggregate(items)
        result = classify_page(agg, p['name'])
        result['pages_crawled'] = agg['pages_crawled']  # show what we looked at
        out[p['name']] = result

    json.dump(out, open(OUT_DIR / 'apify_analysed.json', 'w', encoding='utf-8'), indent=2)
    from collections import Counter
    c = Counter(v['verdict'] for v in out.values())
    print(f"Classified {len(out)} providers:")
    for v, n in c.most_common():
        print(f"  {v}: {n}")
    avg_pages = sum(len(v.get('pages_crawled',[])) for v in out.values()) / max(1, len(out))
    print(f"Avg pages crawled per provider: {avg_pages:.1f}")

if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else 'submit'
    if   arg == 'submit':   cmd_submit()
    elif arg == 'status':   cmd_status(sys.argv[2])
    elif arg == 'fetch':    cmd_fetch(sys.argv[2])
    elif arg == 'analyse':  cmd_analyse()
    else:                   print(__doc__)
