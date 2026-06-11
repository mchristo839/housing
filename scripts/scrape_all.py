"""
Orchestrator: runs every portal scraper, writes one JSON file per portal
to data/scraped/raw/.

Usage:
    python scripts/scrape_all.py                 # all portals, 2020+
    python scripts/scrape_all.py --only fts      # just Find-a-Tender
    python scripts/scrape_all.py --from 2023-01-01

Output:
    data/scraped/raw/findatender_YYYY-MM-DD.json
    data/scraped/raw/contractsfinder_YYYY-MM-DD.json
    ...
"""
import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from scrapers.findatender import FindATenderScraper
from scrapers.contractsfinder import ContractsFinderScraper
from scrapers.sell2wales import Sell2WalesScraper
from scrapers.publiccontractsscotland import PublicContractsScotlandScraper
from scrapers.etendersni import ETendersNIScraper
from scrapers.atamis import AtamisScraper

ALL_SCRAPERS = {
    "fts": FindATenderScraper,
    "contractsfinder": ContractsFinderScraper,
    "sell2wales": Sell2WalesScraper,
    "publiccontractsscotland": PublicContractsScotlandScraper,
    "etendersni": ETendersNIScraper,
    "atamis": AtamisScraper,
}

OUT_DIR = os.path.join(ROOT, "data", "scraped", "raw")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="min_date", default="2020-01-01",
                   help="Earliest award date YYYY-MM-DD (default 2020-01-01)")
    p.add_argument("--to", dest="max_date", default=None)
    p.add_argument("--only", default=None,
                   help=f"Comma-separated list of portals to run. Choices: {','.join(ALL_SCRAPERS)}")
    p.add_argument("--limit", type=int, default=None,
                   help="Stop after N rows per portal (testing)")
    args = p.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    today = datetime.date.today().isoformat()

    portals = (args.only.split(",") if args.only else list(ALL_SCRAPERS))
    portals = [p.strip() for p in portals if p.strip()]

    for name in portals:
        if name not in ALL_SCRAPERS:
            print(f"unknown portal: {name!r} — skipping")
            continue
        cls = ALL_SCRAPERS[name]
        print(f"\n=== {name} ({cls.__name__}) — awards from {args.min_date} ===")
        scraper = cls(min_date=args.min_date, max_date=args.max_date)
        rows = []
        try:
            for row in scraper.scrape():
                rows.append(row)
                if len(rows) % 50 == 0:
                    print(f"  …{len(rows)} rows so far")
                if args.limit and len(rows) >= args.limit:
                    print(f"  reached --limit {args.limit}, stopping")
                    break
        except KeyboardInterrupt:
            print("  interrupted by user — saving what we have")
        out_file = os.path.join(OUT_DIR, f"{name}_{today}.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump({"portal": name, "scraped_at": today,
                       "min_date": args.min_date, "max_date": args.max_date,
                       "rows": rows}, f, indent=2, ensure_ascii=False)
        print(f"  wrote {len(rows)} rows → {out_file}")

    print("\nDone. Next: python scripts/normalise.py")


if __name__ == "__main__":
    main()
