"""
Bidstats London scraper — comprehensive supported-housing contracts since 2020.

Bidstats (bidstats.uk) aggregates UK procurement notices and reliably returns
HTML with browser headers. From our manual test of 5 notices, we saw it
includes:
  - Buyer (London Borough X)
  - Title + status (Tender / Award)
  - Value + duration + dates
  - Award Detail section with named suppliers
  - CPV codes
  - Source link to Find-a-Tender / Contracts Finder

Strategy:
  1. Use Bidstats' search URL: /tenders/?q=<query>&buyer=<borough>
  2. For each (borough, housing_keyword) pair, paginate the search results
  3. For each result link, fetch the notice page
  4. Apply the 3-stage filter:
       buyer matches London/borough AND title contains housing/accommodation
       AND title contains a service-type term
  5. Extract supplier names from Award Detail section
  6. Write to data/scraped/raw/bidstats_london_YYYY-MM-DD.json

Polite rate-limit: 1 req / sec, 5min lockout on 429.
"""
import datetime
import json
import os
import re
import sys
import time
import html
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "scraped", "raw")
os.makedirs(RAW_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.5",
}

POLITE_SEC = 1.5

# London boroughs to search
LONDON_BOROUGHS = [
    "Barking and Dagenham", "Barnet", "Bexley", "Brent", "Bromley", "Camden",
    "Croydon", "Ealing", "Enfield", "Greenwich", "Hackney",
    "Hammersmith and Fulham", "Haringey", "Harrow", "Havering", "Hillingdon",
    "Hounslow", "Islington", "Kensington and Chelsea", "Kingston upon Thames",
    "Lambeth", "Lewisham", "Merton", "Newham", "Redbridge",
    "Richmond upon Thames", "Southwark", "Sutton", "Tower Hamlets",
    "Waltham Forest", "Wandsworth", "Westminster", "City of London",
    # Plus pan-London bodies
    "London Councils", "Greater London Authority", "MOPAC",
    "Capital Letters", "West London Alliance", "Commissioning Alliance", "LIIA",
]

# 3-stage filter (mirrors user spec)
GROUP_A = re.compile(r"\b(housing|accommodation)\b", re.I)
GROUP_B = re.compile(
    r"\b("
    r"supported living|assisted living|"
    r"homelessness|homeless|"
    r"young people|young person|youth (services|support|housing|accommodation)|"
    r"care leaver|supported accommodation|"
    r"child(ren)?s? services|"
    r"cas[- ]?[123]?|community accommodation service|"
    r"temporary accommodation|emergency accommodation|"
    r"asylum|refugee|social housing|affordable housing|"
    r"extra care|sheltered|hostel|refuge|move[- ]?on|tenancy|"
    r"approved premises|bail accommodation|"
    r"floating support|housing related support|"
    r"mental health (supported|community)|learning disability"
    r")\b", re.I)

def passes_filter(title):
    return bool(GROUP_A.search(title or "")) and bool(GROUP_B.search(title or ""))

# Polite HTTP
_last = 0.0
def fetch(url, timeout=20):
    global _last
    gap = time.monotonic() - _last
    if gap < POLITE_SEC:
        time.sleep(POLITE_SEC - gap)
    _last = time.monotonic()
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        return data.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f"  429 lockout — sleeping 300s")
            time.sleep(300)
            return fetch(url, timeout)
        return None
    except Exception:
        return None

# Parse one notice page
def parse_notice(html_text, source_url):
    if not html_text: return None
    text = re.sub(r'<script.*?</script>', '', html_text, flags=re.S)
    text = re.sub(r'<style.*?</style>', '', text, flags=re.S)
    text = html.unescape(re.sub(r'<[^>]+>', '\n', text))
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n+', '\n', text)

    # Title (first h1 / opening line)
    title_m = re.search(r'\n([A-Z][^\n]{15,200}?)\s*\[(Tender|Award|Notice|Modification|PIN)\]', text)
    title = title_m.group(1).strip() if title_m else ""
    status = title_m.group(2) if title_m else "Notice"
    if not passes_filter(title): return None

    # buyer / borough
    boroughs = []
    for m in re.finditer(
        r'(London Borough of [A-Z][a-z]+(?:[ -][A-Z][a-z]+)*|'
        r'Royal Borough of [A-Za-z &]+|'
        r'[A-Z][a-z]+ Borough Council|'
        r'[A-Z][a-z]+ Council|'
        r'Tower Hamlets|City of London|'
        r'Greater London Authority|London Councils?)', text):
        b = m.group(1).strip()
        if b not in boroughs and not b.startswith("The Council"):
            boroughs.append(b)

    # value
    value = ""
    for m in re.finditer(r'Value\s*\n?\s*£([0-9.,KMmk\-\s]+)', text):
        value = m.group(1).strip(); break

    # duration
    duration = ""
    for m in re.finditer(r'Duration\s*\n\s*([^\n]{2,40})', text):
        duration = m.group(1).strip(); break

    # delivery dates
    dates = ""
    for m in re.finditer(r'Delivery\s*\n\s*([^\n]{2,60})', text):
        dates = m.group(1).strip(); break

    # published
    published = ""
    for m in re.finditer(r'Published\s*\n\s*([0-9]{1,2}\s+\w+\s+\d{4})', text):
        published = m.group(1).strip(); break

    # CPV codes (just the numbers)
    cpvs = sorted(set(re.findall(r'\b(\d{8})\b\s*[-–—]?\s*[A-Za-z]', text)))[:6]

    # Suppliers from Award Detail
    suppliers = []
    ai = text.lower().find('award detail')
    if ai > 0:
        section = text[ai:ai+3000]
        # Each award block is usually: number\nCompany Name\n(Location)\n
        for m in re.finditer(
            r'\n([A-Z][A-Za-z0-9 &\'\-\.,/]{4,80})\s*\n\s*\(([A-Za-z ,]+?)\)', section):
            name = m.group(1).strip()
            loc = m.group(2).strip()
            # filter out section headings
            if name.lower() in {'award detail', 'awards', 'contractors', 'supplier analysis'}: continue
            if len(name) > 80: continue
            suppliers.append({"name": name, "location": loc})

    return {
        "source_url": source_url,
        "status": status,
        "title": title,
        "boroughs": boroughs,
        "value_raw": value,
        "duration": duration,
        "delivery_dates": dates,
        "published": published,
        "cpv_codes": cpvs,
        "suppliers": suppliers,
    }

# Search by borough
def search_borough(borough, max_pages=5):
    q = urllib.parse.quote(f'"{borough}" housing accommodation')
    notices_found = []
    for page in range(1, max_pages+1):
        url = f"https://bidstats.uk/tenders/?q={q}&page={page}"
        html_text = fetch(url)
        if not html_text: break
        # Find all notice URLs
        urls = sorted(set(re.findall(
            r'href="(/tenders/\d{4}/[Ww]\d+/\d+)"', html_text)))
        if not urls: break
        for u in urls:
            full = "https://bidstats.uk" + u
            if full not in notices_found:
                notices_found.append(full)
        if len(urls) < 10: break  # last page
    return notices_found

def main():
    print(f"Starting Bidstats London scrape at {datetime.datetime.now()}")
    print(f"  Targets: {len(LONDON_BOROUGHS)} boroughs/bodies")
    all_records = []
    seen = set()

    for i, borough in enumerate(LONDON_BOROUGHS):
        print(f"\n[{i+1}/{len(LONDON_BOROUGHS)}] Searching: {borough}")
        notice_urls = search_borough(borough)
        print(f"   {len(notice_urls)} candidate notices")
        for url in notice_urls:
            if url in seen: continue
            seen.add(url)
            page = fetch(url)
            rec = parse_notice(page, url)
            if rec:
                rec["search_borough"] = borough
                all_records.append(rec)
                # show supplier names if any
                sup = ', '.join(s['name'][:30] for s in rec['suppliers'][:3])
                print(f"     KEEP [{rec['status']}] {rec['title'][:65]} | suppliers: {sup or '(TBD/framework)'}")
        # checkpoint after each borough
        today = datetime.date.today().isoformat()
        out = os.path.join(RAW_DIR, f"bidstats_london_{today}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"portal": "bidstats", "scraped_at": today,
                       "boroughs_done": LONDON_BOROUGHS[:i+1],
                       "records": all_records}, f, indent=2, ensure_ascii=False)

    print(f"\nDONE — {len(all_records)} London supported-housing notices captured")
    print(f"Output: data/scraped/raw/bidstats_london_{datetime.date.today().isoformat()}.json")

if __name__ == "__main__":
    main()
