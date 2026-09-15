"""Step 1 — pull the portals and work out which suppliers are new to us.

Runs the existing portal scrapers, keeps the housing-relevant awards made by
real local authorities, drops anything whose supplier we already hold, and
writes what is left as a candidates CSV for step 2 to ingest.

    python3 scripts/pipeline/harvest.py                 # last 60 days, all portals
    python3 scripts/pipeline/harvest.py --days 30
    python3 scripts/pipeline/harvest.py --only contractsfinder --limit 50
    python3 scripts/pipeline/harvest.py --reuse          # skip scraping, use the
                                                        # newest raw files on disk

Writes data/harvest/candidates_<date>.csv and prints a summary. Scraping only
ever appends to data/scraped/raw/, so a failed run costs nothing.
"""
import argparse
import csv
import datetime
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.pipeline.common import (  # noqa: E402
    HARVEST_DIR, PROVIDERS, ProviderIndex, is_council, is_real_supplier, read_json,
)

RAW_DIR = Path(__file__).resolve().parent.parent.parent / "data/scraped/raw"

# A harvested award only interests us if someone is being housed and supported
# under it. The portals tag anything touching housing as Sector "Housing", which
# sweeps in solicitors, flooring contractors and bin suppliers, so the title has
# to name a placement service explicitly — there is no permissive fallback.
HOUSING_TITLE = (
    r"supported living|supported accommodation|supported housing|"
    r"semi.?independent|\b16\+|care leaver|looked after child|children'?s home|"
    r"temporary accommodation|nightly purchased|emergency accommodation|"
    r"housing related support|extra care (housing|scheme)|"
    r"residential (care|placement)|care and support|accommodation and support|"
    r"accommodation (and|&) support|rough sleep|homelessness|housing first|"
    r"women'?s refuge|domestic abuse (accommodation|refuge|service)|"
    r"asylum (accommodation|support)|dispersal accommodation|nrpf|no recourse|"
    r"move.?on accommodation|supported placement|placement framework|"
    r"independent living (service|support)|floating support|outreach support"
)
# Professional and facilities work that names housing but houses nobody. Checked
# first, so "Supported Housing Strategy" (a consultancy piece) never qualifies.
NOT_HOUSING = (
    r"legal|solicitor|counsel\b|insurance|audit|valuation|"
    r"consultanc|advis(or|ory)|strategy|review of|feasibility|"
    r"architect|survey|design team|construction|build contract|refurbish|"
    r"repairs|maintenance|installation|supply (and|&) install|flooring|vinyl|"
    r"kitchen|bathroom|window|roofing|heating|boiler|electrical|fire (door|alarm|safety)|"
    r"waste|\bbin\b|removal|decant|cleaning|catering|grounds|landscap|"
    r"training|recruitment|agency staff|temporary staff|software|system|licence|licens|"
    r"vehicle|fleet|security (monitoring|guard)|cctv|telecare|"
    r"financial|banking|loan|investment|development (loan|grant|partner)|"
    r"managing agent|letting agent fee|estate agen|"
    r"multidisciplinary|academy|school building|project management"
)


def wanted(row):
    """Is this award a housing placement we would list a provider for?"""
    import re
    title = str(row.get("Contract Titles") or "").lower()
    if not title.strip():
        return False
    if re.search(NOT_HOUSING, title):
        return False
    return bool(re.search(HOUSING_TITLE, title))


def newest_raw_files():
    """The most recent file per portal already on disk."""
    latest = {}
    for f in sorted(RAW_DIR.glob("*.json")):
        portal = f.stem.rsplit("_", 1)[0]
        latest[portal] = f            # sorted, so the last wins
    return list(latest.values())


def run_scrapers(days, only, limit):
    import subprocess
    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    cmd = [sys.executable, "scripts/scrape_all.py", "--from", since]
    if only:
        cmd += ["--only", only]
    if limit:
        cmd += ["--limit", str(limit)]
    print("running: %s" % " ".join(cmd), flush=True)
    # A portal being down must not lose the portals that did work — scrape_all
    # writes each portal's file as it finishes.
    subprocess.run(cmd, cwd=str(Path(__file__).resolve().parent.parent.parent), check=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60, help="how far back to ask the portals")
    ap.add_argument("--only", default=None, help="comma-separated portal list")
    ap.add_argument("--limit", type=int, default=None, help="rows per portal (testing)")
    ap.add_argument("--reuse", action="store_true", help="skip scraping, use files on disk")
    args = ap.parse_args()

    if not args.reuse:
        run_scrapers(args.days, args.only, args.limit)

    files = newest_raw_files()
    if not files:
        print("no raw portal files found — nothing to do")
        return 0

    rows = []
    for f in files:
        blob = read_json(f, {})
        for r in blob.get("rows") or []:
            r.setdefault("source_portal", blob.get("portal", ""))
            rows.append(r)
    print("read %d award rows from %d portal files" % (len(rows), len(files)))

    providers = read_json(PROVIDERS, [])
    index = ProviderIndex(providers)

    stats = Counter()
    seen = set()
    candidates = []
    for r in rows:
        name = str(r.get("Company") or "").strip()
        council = str(r.get("Council") or "").strip()
        if not is_real_supplier(name):
            stats["dropped: not a supplier name"] += 1
            continue
        if not is_council(council):
            stats["dropped: awarding body is not a council"] += 1
            continue
        if not wanted(r):
            stats["dropped: not a housing award"] += 1
            continue
        if index.find(name, r.get("source_url", "")):
            stats["already held"] += 1
            continue
        key = (name.lower(), council.lower())
        if key in seen:
            stats["duplicate row"] += 1
            continue
        seen.add(key)
        candidates.append({
            "Supplier": name,
            "Website": "",
            "Email": "",
            "Framework": str(r.get("Contract Titles") or "").strip(),
            "Borough": council,
            "Councils Named": council,
            "Council Access Basis": "commissioning council only",
            "Companies House No": str(r.get("Companies House") or "").strip(),
            "Notice ID": str(r.get("source_id") or "").strip(),
            "Awarded Date": str(r.get("Most Recent Award") or "").strip(),
            "Contact Status": "unenriched (from %s)" % r.get("source_portal", "portal"),
            "Notes": str(r.get("source_url") or "").strip(),
            "Check": "",
        })
        stats["candidate"] += 1

    HARVEST_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    out = HARVEST_DIR / ("candidates_%s.csv" % today)
    cols = list(candidates[0].keys()) if candidates else [
        "Supplier", "Website", "Email", "Framework", "Borough", "Councils Named",
        "Council Access Basis", "Companies House No", "Notice ID", "Awarded Date",
        "Contact Status", "Notes", "Check"]
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(candidates)

    summary = {
        "date": today,
        "portal_files": [f.name for f in files],
        "award_rows_read": len(rows),
        "candidates": len(candidates),
        "distinct_suppliers": len({c["Supplier"].lower() for c in candidates}),
        "councils": len({c["Borough"].lower() for c in candidates}),
        "breakdown": dict(stats),
    }
    (HARVEST_DIR / ("summary_%s.json" % today)).write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\ncandidates written: %s" % out)
    for k, v in stats.most_common():
        print("  %-38s %d" % (k, v))
    print("\n%d candidate rows, %d distinct suppliers, %d councils"
          % (len(candidates), summary["distinct_suppliers"], summary["councils"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
