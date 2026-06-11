"""
Targeted Contracts Finder scrape: each consortium × housing/accommodation keyword.

Much smaller than the bulk scrape — five consortium names × handful of pages each.
Each search is a fresh cursor (so no depth cap problem).

Output: data/scraped/raw/consortia_YYYY-MM-DD.json — one file with all hits.
"""
import datetime
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from scrapers.findatender import FindATenderScraper
from scrapers.base import is_housing_title, is_housing_cpv

CF_SEARCH = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"
RATE_LIMIT_SEC = 6.0
LOCKOUT_RETRY_SEC = 305  # 5-minute lockout window

# Each (label, query). Query is what we send as searchCriteria.keyword.
# We do per-consortium search * housing-keyword combinations. Title-level
# filtering happens client-side after we get the rows back.
CONSORTIUM_QUERIES = [
    ("Capital Letters", "Capital Letters"),
    ("West London Alliance", "West London Alliance"),
    ("Commissioning Alliance", "Commissioning Alliance"),
    ("LIIA", "London Innovation and Improvement Alliance"),
    ("LIIA — Pan-London SCH", "Pan-London Secure Children"),
    ("LIIA — Accommodation Pathfinder", "London Accommodation Pathfinder"),
    ("Achieving for Children", "Achieving for Children"),
    ("London Councils", "London Councils"),
    # Plus generic London supported-housing terms that should now catch things
    ("London supported living", "London supported living"),
    ("Pan-London accommodation", "Pan-London accommodation"),
]

import re
# THREE-STAGE filter (per user spec):
#   1. Consortium name → already sent to CF as searchCriteria.keyword (server-side)
#   2. Title MUST contain housing OR accommodation (Group A)
#   3. Title MUST contain at least one of the "what kind of housing/who is it for"
#      terms (Group B) — to weed out e.g. "Capital Letters Legal Services on
#      Housing Policy" which would pass Group A alone.
# A row is kept only when ALL THREE are satisfied.

GROUP_A = re.compile(r"\b(housing|accommodation)\b", re.I)
GROUP_B = re.compile(
    r"\b("
    r"supported living|assisted living|"
    r"homelessness|homeless|"
    r"young people|young person|youth (services|support|housing|accommodation)|"
    r"care leaver|"
    r"supported accommodation|"
    r"child(ren)?s? services|"
    r"cas[- ]?[123]?|community accommodation service|"
    r"temporary accommodation|emergency accommodation|"
    r"asylum|refugee|"
    r"social housing|affordable housing"
    r")\b", re.I)

def title_passes(title):
    """True if title matches BOTH Group A and Group B."""
    return bool(GROUP_A.search(title or "")) and bool(GROUP_B.search(title or ""))

# Legacy alias for any code still referencing the old name — same semantics now
HOUSING_OR_ACCOMMODATION = GROUP_A

def fetch_with_retry(url, max_retries=3):
    last = time.monotonic()
    for attempt in range(max_retries):
        # rate-limit pacing
        gap = time.monotonic() - last
        if gap < RATE_LIMIT_SEC:
            time.sleep(RATE_LIMIT_SEC - gap)
        last = time.monotonic()
        req = urllib.request.Request(url, headers={
            "User-Agent": "findahousingprovider-targeted/1.0 (paul@pioneerdrinks.com)",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                print(f"    ({e.code} rate-limit; sleeping {LOCKOUT_RETRY_SEC}s)")
                time.sleep(LOCKOUT_RETRY_SEC)
                continue
            raise
    return None

def search_consortium(label, query):
    """Run a Contracts Finder OCDS Search for `query`, filter results
    client-side to housing/accommodation/supported-living titles, yield rows."""
    builder = FindATenderScraper("2018-01-01", None)
    cursor = None
    pages_seen = 0
    rows_kept = 0
    while True:
        params = {
            "publishedFrom": "2018-01-01T00:00:00",
            "publishedTo": f"{datetime.date.today().isoformat()}T23:59:59",
            "stages": "award",
            "limit": 100,
            "keyword": query,
        }
        if cursor: params["cursor"] = cursor
        url = CF_SEARCH + "?" + urllib.parse.urlencode(params)
        resp = fetch_with_retry(url)
        if not resp or not resp.get("releases"):
            return
        pages_seen += 1
        for release in resp["releases"]:
            title = ((release.get("tender") or {}).get("title") or "")
            buyer = ((release.get("buyer") or {}).get("name") or "")
            # Three-stage filter:
            #   1. The CF API has already matched the consortium keyword (server-side).
            #   2. Title must contain "housing" OR "accommodation" (Group A).
            #   3. Title must also contain a service-type term (Group B).
            # A row is kept only when both client-side groups match.
            if not title_passes(title):
                continue
            for row in builder._releases_to_rows(release):
                row["source_portal"] = "contractsfinder"
                row["consortium_query"] = label
                row["search_query"] = query
                rows_kept += 1
                yield row
        cursor = ((resp.get("links") or {}).get("next") or "")
        if cursor:
            # cursor is a full URL; extract cursor param
            qs = urllib.parse.parse_qs(urllib.parse.urlsplit(cursor).query)
            cursor = qs.get("cursor", [None])[0]
        if not cursor: break
    print(f"  [{label}] {pages_seen} pages scanned, {rows_kept} housing rows kept")

def main():
    all_rows = []
    for label, query in CONSORTIUM_QUERIES:
        print(f"\n=== {label!r}  query={query!r} ===")
        try:
            for row in search_consortium(label, query):
                all_rows.append(row)
        except Exception as e:
            print(f"  error: {e}")

    today = datetime.date.today().isoformat()
    out = os.path.join(ROOT, "data", "scraped", "raw", f"consortia_{today}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"portal": "contractsfinder-targeted",
                   "scraped_at": today,
                   "queries": [q for _,q in CONSORTIUM_QUERIES],
                   "rows": all_rows}, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(all_rows)} rows → {out}")

if __name__ == "__main__":
    main()
