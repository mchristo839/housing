"""
CarePlace (careplace.org.uk) scraper.

CarePlace is the Commissioning Alliance's public-facing provider directory,
covering 27 London + neighbouring LAs and 1,000+ care providers.

Strategy:
  1. Crawl Categories/2 (Care homes & housing options) — all listings.
  2. Also crawl /Categories/3 (Community & activities — youth/family stuff)
     and /Categories/8 (Conditions & disabilities — sometimes housing-adjacent).
  3. For each listing follow through to extract provider name, address,
     postcode, phone, website, description.
  4. Output to data/scraped/raw/careplace_YYYY-MM-DD.json.

This is a public-facing site so no auth needed. We're polite — 2s between
requests, single concurrency.
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "scraped", "raw")
os.makedirs(RAW_DIR, exist_ok=True)

BASE = "https://www.careplace.org.uk"
HEADERS = {
    "User-Agent": "findahousingprovider-data-ingest/1.0 (paul@pioneerdrinks.com)",
    "Accept": "text/html,*/*",
}

# Polite rate-limit
SLEEP_SEC = 2.0
_last = 0.0
def get(url):
    global _last
    delta = time.monotonic() - _last
    if delta < SLEEP_SEC:
        time.sleep(SLEEP_SEC - delta)
    _last = time.monotonic()
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} on {url}")
        return None
    except Exception as e:
        print(f"  error on {url}: {e}")
        return None

# Crude HTML extractors — careplace is a Razor/.NET ASP page so structure
# should be consistent across listings.
RE_CARD = re.compile(
    r'<a[^>]+href="(/Services/Details/\d+[^"]*)"[^>]*>\s*<[^>]+>([^<]+)</', re.I)
RE_SERVICE_TITLE = re.compile(r'<h1[^>]*>(.*?)</h1>', re.S)
RE_PHONE = re.compile(r'(?:tel:|telephone|phone)[^<>]*?(\+?\d[\d\s\-\(\)]{6,})', re.I)
RE_EMAIL = re.compile(r'([\w.+-]+@[\w-]+\.[\w.-]+)')
RE_POSTCODE = re.compile(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b', re.I)
RE_WEBSITE = re.compile(r'href="(https?://[^"]+)"[^>]*>(?:[^<]*website|visit|home)', re.I)


def parse_listing_page(category_id, page_num):
    url = f"{BASE}/Categories/{category_id}?page={page_num}"
    html_doc = get(url)
    if not html_doc:
        return [], False
    cards = []
    seen_urls = set()
    # extract service detail links
    for m in re.finditer(r'href="(/Services/Details/[^"]+)"', html_doc, re.I):
        path = m.group(1)
        if path in seen_urls: continue
        seen_urls.add(path)
        cards.append(BASE + path)
    has_next = ("page=" + str(page_num + 1)) in html_doc or "Next" in html_doc[-3000:]
    return cards, has_next and len(cards) > 0


def parse_service_page(url):
    html_doc = get(url)
    if not html_doc:
        return None
    # strip tags helper
    def strip(s):
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html.unescape(s))).strip()
    title_m = RE_SERVICE_TITLE.search(html_doc)
    title = strip(title_m.group(1)) if title_m else ""
    phone_m = RE_PHONE.search(html_doc)
    phone = strip(phone_m.group(1)) if phone_m else ""
    email_m = RE_EMAIL.search(html_doc)
    email = email_m.group(1) if email_m else ""
    postcode_m = RE_POSTCODE.search(html_doc)
    postcode = postcode_m.group(0) if postcode_m else ""
    website_m = RE_WEBSITE.search(html_doc)
    website = website_m.group(1) if website_m else ""
    return {
        "url": url,
        "name": title,
        "phone": phone,
        "email": email,
        "postcode": postcode,
        "website": website,
        "scraped_at": datetime.datetime.now().isoformat(),
    }


def main():
    all_records = []
    seen_urls = set()
    # Focus on Category 2 (Care homes & housing options) first
    for category_id in [2]:
        print(f"\n=== Category {category_id} ===")
        for page in range(1, 100):
            print(f"  page {page}...")
            urls, has_next = parse_listing_page(category_id, page)
            if not urls:
                print(f"  no urls on page {page}, stopping")
                break
            print(f"    found {len(urls)} listings")
            for u in urls:
                if u in seen_urls: continue
                seen_urls.add(u)
                rec = parse_service_page(u)
                if rec:
                    all_records.append(rec)
            if not has_next:
                break
            if page > 50:
                print(f"  safety cap at 50 pages"); break

    today = datetime.date.today().isoformat()
    out = os.path.join(RAW_DIR, f"careplace_{today}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"portal": "careplace",
                   "scraped_at": today,
                   "category": "Care homes & housing options (id=2)",
                   "rows": all_records}, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(all_records)} records → {out}")


if __name__ == "__main__":
    main()
