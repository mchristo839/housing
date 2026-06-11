"""
Comprehensive UK supported-housing contracts backfill 2020 → today.

Strategy:
  - Process MONTH BUCKETS: 2020-01, 2020-02, ..., today.
  - For each month, paginate Contracts Finder OCDS Search bulk (no keyword
    filter; we filter client-side with the 3-stage logic).
  - Fresh cursor per month → no depth cap.
  - Save raw per-month JSON + a filtered/normalised view.
  - Checkpoint per portal per month — resumable across runs.

Filter (per user spec):
  Group A: title contains housing OR accommodation
  AND
  Group B: title contains one of supported living | assisted living |
           homelessness | young people | supported accommodation |
           child(ren)'s services | CAS | temporary accommodation |
           asylum | social housing | (+ related)

Output structure:
  data/scraped/backfill/raw/{portal}/{YYYY-MM}.json   ← all award notices that month
  data/scraped/backfill/filtered/{portal}/{YYYY-MM}.json  ← only housing matches
  data/scraped/backfill/checkpoint.json                 ← which months are done
  data/scraped/backfill/log.txt                         ← progress / errors

Usage:
    python -u scripts/backfill_contracts.py                  # all portals, 2020→today
    python -u scripts/backfill_contracts.py --only cf        # CF only
    python -u scripts/backfill_contracts.py --only fts       # FTS only
    python -u scripts/backfill_contracts.py --resume         # skip months already done
"""
import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BACKFILL_DIR = os.path.join(ROOT, "data", "scraped", "backfill")
RAW_DIR = os.path.join(BACKFILL_DIR, "raw")
FILTERED_DIR = os.path.join(BACKFILL_DIR, "filtered")
CHECKPOINT = os.path.join(BACKFILL_DIR, "checkpoint.json")
LOG = os.path.join(BACKFILL_DIR, "log.txt")

# Portals
CF_URL = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"
FTS_URL = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"

USER_AGENT = "findahousingprovider-aggregator/1.0 (paul@pioneerdrinks.com)"
POLITE_SEC = 6.0
LOCKOUT_RETRY_SEC = 305

# ── 3-stage filter ──────────────────────────────────────────────────────────
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
    r"social housing|affordable housing|"
    r"extra care|sheltered|hostel|refuge|move[- ]?on|tenancy|"
    r"floating support|housing related support|"
    r"approved premises|bail accommodation|"
    r"section 117|s117|"
    r"complex needs"
    r")\b", re.I)

def title_passes(text):
    return bool(GROUP_A.search(text or "")) and bool(GROUP_B.search(text or ""))


# ── London focus: buyer/title must look London-related ──────────────────────
# A row passes if the BUYER NAME OR TITLE mentions London / a London borough /
# a London consortium / a pan-London body / NHS London ICB.
LONDON_BUYER = re.compile(
    r"\b("
    # Pan-London bodies
    r"london councils?|greater london authority|\bgla\b|mayor of london|"
    r"mayor.s office for policing|\bmopac\b|"
    # London consortia
    r"capital letters|west london alliance|\bwla\b|"
    r"commissioning alliance|liia|london innovation and improvement|"
    r"achieving for children|pan[- ]?london|"
    r"london procurement|capital esourcing|"
    # NHS London ICBs
    r"nhs north (west|central|east) london|nhs north[- ]?(west|central|east) london|"
    r"nhs south (east|west) london|nhs south[- ]?(east|west) london|"
    r"\bn(w|c|e)l\b icb|\bs(e|w)l\b icb|"
    # London borough names (every borough + variants)
    r"barking (and|&) dagenham|\bbarnet\b|\bbexley\b|\bbrent\b|\bbromley\b|"
    r"\bcamden\b|\bcroydon\b|\bealing\b|\benfield\b|\bgreenwich\b|"
    r"\bhackney\b|hammersmith (and|&) fulham|\bharingey\b|\bharrow\b|"
    r"\bhavering\b|\bhillingdon\b|\bhounslow\b|\bislington\b|"
    r"kensington (and|&) chelsea|kingston upon thames|\blambeth\b|"
    r"\blewisham\b|\bmerton\b|\bnewham\b|\bredbridge\b|"
    r"richmond upon thames|\bsouthwark\b|\bsutton\b|tower hamlets|"
    r"waltham forest|\bwandsworth\b|\bwestminster\b|city of london|"
    r"\brbkc\b|\blbth\b|\blbhf\b|\blbbd\b|\blbwf\b"
    r")\b", re.I)

def is_london(buyer_name, title):
    return bool(LONDON_BUYER.search(buyer_name or "")) or bool(LONDON_BUYER.search(title or ""))


# ── HTTP with rate-limit retry ──────────────────────────────────────────────
_last_req_at = 0.0
def _sleep_if_needed():
    global _last_req_at
    gap = time.monotonic() - _last_req_at
    if gap < POLITE_SEC:
        time.sleep(POLITE_SEC - gap)
    _last_req_at = time.monotonic()

def get_json(url, params=None, max_retries=4):
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    last = None
    for attempt in range(max_retries):
        _sleep_if_needed()
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (429, 403):
                log(f"  ({e.code} lockout — sleeping {LOCKOUT_RETRY_SEC}s)")
                time.sleep(LOCKOUT_RETRY_SEC)
                last = e
                continue
            if e.code == 503:
                time.sleep(60); last = e; continue
            raise
        except Exception as e:
            last = e
            time.sleep(2 ** attempt)
    raise last

# ── Checkpoint helpers ──────────────────────────────────────────────────────
def load_checkpoint():
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT, encoding="utf-8") as f:
            return json.load(f)
    return {"cf": {}, "fts": {}}

def save_checkpoint(cp):
    os.makedirs(os.path.dirname(CHECKPOINT), exist_ok=True)
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(cp, f, indent=2)

# ── Logging ────────────────────────────────────────────────────────────────
def log(msg):
    line = f"{datetime.datetime.now().strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ── Month iteration ─────────────────────────────────────────────────────────
def iter_months(start="2020-01", end=None):
    """Yield (year, month) tuples between start and end inclusive."""
    if end is None:
        today = datetime.date.today()
        end = f"{today.year}-{today.month:02d}"
    sy, sm = (int(x) for x in start.split("-"))
    ey, em = (int(x) for x in end.split("-"))
    y, m = sy, sm
    while (y, m) <= (ey, em):
        yield y, m
        m += 1
        if m == 13: m = 1; y += 1

# ── Contracts Finder ───────────────────────────────────────────────────────
def scrape_cf_month(year, month):
    pf = f"{year:04d}-{month:02d}-01T00:00:00"
    last_day = (datetime.date(year+(month==12), 1 if month==12 else month+1, 1)
                - datetime.timedelta(days=1)).day
    pt = f"{year:04d}-{month:02d}-{last_day}T23:59:59"
    cursor = None
    page = 0
    all_releases = []
    filtered = []
    while True:
        page += 1
        params = {"publishedFrom": pf, "publishedTo": pt,
                  "stages": "award", "limit": 100}
        if cursor: params["cursor"] = cursor
        try:
            resp = get_json(CF_URL, params=params)
        except Exception as e:
            log(f"  cf {year}-{month:02d} page {page} failed: {e}")
            return None
        releases = resp.get("releases") or []
        if not releases: break
        all_releases.extend(releases)
        # filter: London-related AND housing-titled (3-stage Group A + Group B)
        for r in releases:
            title = (r.get("tender") or {}).get("title") or ""
            buyer = (r.get("buyer") or {}).get("name") or ""
            if not is_london(buyer, title): continue
            if not title_passes(title): continue
            filtered.append(r)
        # next cursor
        next_url = (resp.get("links") or {}).get("next")
        if not next_url: break
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(next_url).query)
        cursor = qs.get("cursor", [None])[0]
        if not cursor: break
    return {"raw_count": len(all_releases), "filtered_count": len(filtered),
            "pages": page, "filtered_releases": filtered}

# ── Find-a-Tender ──────────────────────────────────────────────────────────
def scrape_fts_month(year, month):
    """FTS bulk: cursor is a release-id, not a date. We use the OCDS feed and
    advance cursor; stop when releaseDate exits the month bucket."""
    pf_dt = datetime.date(year, month, 1)
    nm_y, nm_m = (year+(month==12), 1 if month==12 else month+1)
    pt_dt = datetime.date(nm_y, nm_m, 1) - datetime.timedelta(days=1)
    cursor = f"{pf_dt.isoformat()}T00:00:00"
    page = 0
    all_releases = []
    filtered = []
    while True:
        page += 1
        params = {"cursor": cursor, "limit": 100}
        try:
            resp = get_json(FTS_URL, params=params)
        except Exception as e:
            log(f"  fts {year}-{month:02d} page {page} failed: {e}")
            return None
        releases = resp.get("releases") or []
        if not releases: break
        # check date — stop once we leave the month
        leaving_month = False
        for r in releases:
            d = (r.get("date") or "")[:10]
            try:
                rd = datetime.date.fromisoformat(d) if d else None
            except Exception:
                rd = None
            if rd and rd > pt_dt:
                leaving_month = True
                continue
            if rd and rd < pf_dt:
                continue
            # only award stage
            if not (r.get("awards") or []):
                continue
            all_releases.append(r)
            title = (r.get("tender") or {}).get("title") or ""
            buyer = (r.get("buyer") or {}).get("name") or ""
            if is_london(buyer, title) and title_passes(title):
                filtered.append(r)
        if leaving_month: break
        # advance cursor
        next_url = (resp.get("links") or {}).get("next")
        if not next_url:
            # advance manually using max date in this page
            latest = max((r.get("date","") for r in releases if r.get("date")),
                         default="")
            if not latest or latest <= cursor: break
            cursor = latest
        else:
            qs = urllib.parse.parse_qs(urllib.parse.urlsplit(next_url).query)
            cursor = qs.get("cursor", [cursor])[0]
        if page > 200:
            log(f"  fts {year}-{month:02d} safety cap at 200 pages"); break
    return {"raw_count": len(all_releases), "filtered_count": len(filtered),
            "pages": page, "filtered_releases": filtered}

# ── Save per-month outputs ──────────────────────────────────────────────────
def save_month(portal, year, month, result):
    if result is None: return
    os.makedirs(os.path.join(FILTERED_DIR, portal), exist_ok=True)
    fname = f"{year:04d}-{month:02d}.json"
    out = os.path.join(FILTERED_DIR, portal, fname)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"portal": portal, "year": year, "month": month,
                   "raw_count": result["raw_count"],
                   "filtered_count": result["filtered_count"],
                   "pages": result["pages"],
                   "releases": result["filtered_releases"]},
                  f, indent=2, ensure_ascii=False)

# ── Main ────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--only", default=None, choices=["cf", "fts"])
    p.add_argument("--start", default="2020-01")
    p.add_argument("--end", default=None)
    p.add_argument("--resume", action="store_true", help="skip months already in checkpoint")
    args = p.parse_args()

    portals_to_run = [args.only] if args.only else ["cf", "fts"]
    cp = load_checkpoint()
    months = list(iter_months(args.start, args.end))
    log(f"Starting backfill — {len(months)} months × {len(portals_to_run)} portals")

    total_raw, total_filtered = 0, 0
    for portal in portals_to_run:
        log(f"\n=== Portal: {portal} ===")
        for year, month in months:
            key = f"{year:04d}-{month:02d}"
            if args.resume and cp.get(portal, {}).get(key):
                log(f"  {portal} {key}: already done, skipping")
                continue
            log(f"  {portal} {key}: scraping...")
            if portal == "cf":
                result = scrape_cf_month(year, month)
            else:
                result = scrape_fts_month(year, month)
            if result is None:
                log(f"  {portal} {key}: FAILED")
                continue
            save_month(portal, year, month, result)
            cp.setdefault(portal, {})[key] = {
                "raw": result["raw_count"],
                "filtered": result["filtered_count"],
                "pages": result["pages"],
                "scraped_at": datetime.datetime.now().isoformat(),
            }
            save_checkpoint(cp)
            total_raw += result["raw_count"]
            total_filtered += result["filtered_count"]
            log(f"  {portal} {key}: {result['raw_count']} raw → {result['filtered_count']} housing ({result['pages']} pages)")

    log(f"\nDONE. Total scraped: {total_raw}, filtered to housing: {total_filtered}")

if __name__ == "__main__":
    main()
