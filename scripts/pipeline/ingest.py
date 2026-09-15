"""Step 2 — fold a candidates CSV into the live dataset.

Reads the CSV that harvest.py writes (the same shape as the supplier updates we
receive by hand), attaches each award to every council named on it, and updates
the three files the search reads plus the first-seen ledger.

    python3 scripts/pipeline/ingest.py                       # newest candidates file
    python3 scripts/pipeline/ingest.py path/to/file.csv
    python3 scripts/pipeline/ingest.py --dry-run             # report, write nothing

Idempotent: re-running over the same CSV creates no providers and no contracts.
A council new to us is added to councilmap.json under the key the postcode
search derives from postcodes.io, so it is findable straight away.
"""
import argparse
import csv
import datetime
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.pipeline.common import (  # noqa: E402
    COUNCILMAP, DB, HARVEST_DIR, LEDGER, PROVIDERS, ProviderIndex,
    is_council, is_real_supplier, norm_council, read_json, write_json,
)

# Stamped on providers that predate the ledger, so they never read as "new".
BASELINE = "2000-01-01"

# Framework wording -> (client_groups, sectors, primary_cat). First match wins,
# mirroring how the borough export categorises the same text.
RULES = [
    (r"16\+|semi.?independent|young pe|care leaver|children|looked after",
     ["Young people & care leavers"],
     ["Supported accommodation", "Young people", "Care leavers", "Housing"], "Supported accommodation"),
    (r"domestic (violence|abuse)|vawg|women'?s refuge",
     ["Domestic abuse"], ["Supported accommodation", "Refuge", "Housing"], "Supported accommodation"),
    (r"rough sleep|housing first|homeless",
     ["Homelessness"], ["Supported accommodation", "Homelessness", "Housing"], "Supported accommodation"),
    (r"asylum|dispersal|nrpf|no recourse",
     ["Asylum & refugees"], ["Asylum housing", "Housing"], "Supported accommodation"),
    (r"temporary accommodation|nightly purchased|emergency",
     [], ["Emergency accommodation", "Housing"], "Emergency accommodation"),
    (r"mental health",
     ["Mental health"], ["Supported living", "Mental health", "Housing"], "Supported living"),
    (r"learning disab|autism",
     ["Learning disabilities"], ["Supported living", "Learning disability", "Housing"], "Supported living"),
    (r"extra care|older",
     ["Older people"], ["Supported living", "Housing"], "Supported living"),
    (r"supported living|independent living|floating support|housing related support",
     [], ["Supported living", "Housing"], "Supported living"),
]
DEFAULT = ([], ["Supported accommodation", "Housing"], "Supported accommodation")


def classify(text):
    t = str(text or "").lower()
    for pattern, groups, sectors, primary in RULES:
        if re.search(pattern, t):
            return groups, sectors, primary
    return DEFAULT


def build_region_hints(providers):
    """Region per council, learned from the contracts we already hold, so a new
    award lands in the right regional tier without a hardcoded table."""
    votes = {}
    for p in providers:
        for c in p.get("contracts_list") or []:
            council, region = c.get("council"), c.get("region")
            if not council or not region:
                continue
            key = norm_council(council)
            votes.setdefault(key, Counter())[region] += 1
    return {k: v.most_common(1)[0][0] for k, v in votes.items()}


def canonical_council(name, db, councilmap):
    """The spelling db.json already uses for this council, so new awards merge
    into the existing bucket instead of splitting it."""
    key = norm_council(name)
    for existing in councilmap.get(key) or []:
        if existing in db["c"]:
            return existing, key
    for db_key in db["c"]:
        if norm_council(db_key) == key:
            return db_key, key
    return str(name).strip(), key      # genuinely new council


def title_for(row):
    framework = str(row.get("Framework") or "").strip().rstrip("-").strip()
    bits = []
    if str(row.get("Awarded Date") or "").strip():
        bits.append("Awarded %s." % str(row["Awarded Date"]).strip())
    if str(row.get("Notice ID") or "").strip():
        bits.append("Notice %s." % str(row["Notice ID"]).strip())
    return ("%s — %s" % (framework, " ".join(bits))) if bits else framework


def newest_candidates():
    files = sorted(HARVEST_DIR.glob("candidates_*.csv"))
    return files[-1] if files else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", nargs="?", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = Path(args.csv_path) if args.csv_path else newest_candidates()
    if not path or not path.exists():
        print("no candidates CSV found — nothing to ingest")
        return 0

    with open(path, encoding="utf-8-sig") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("Supplier") or "").strip()]

    providers = read_json(PROVIDERS, [])
    db = read_json(DB, {"c": {}, "county": {}, "r": {}, "n": []})
    councilmap = read_json(COUNCILMAP, {})
    ledger = read_json(LEDGER, {})
    index = ProviderIndex(providers)
    regions = build_region_hints(providers)

    today = datetime.date.today().isoformat()
    created, attached, links, touched = [], set(), 0, set()
    skipped = Counter()

    for row in rows:
        name = str(row["Supplier"]).strip()
        if not is_real_supplier(name):
            skipped["not a supplier name"] += 1
            continue
        framework = str(row.get("Framework") or "").strip()
        groups, sectors, primary = classify(framework)
        title = title_for(row)

        named = [c.strip() for c in str(row.get("Councils Named") or "").split(";") if c.strip()]
        named = [c for c in named if is_council(c)]
        if not named:
            skipped["no usable council"] += 1
            continue

        website = str(row.get("Website") or "").strip()
        email = str(row.get("Email") or "").strip()

        p = index.find(name, website, email)
        if p is None:
            pid = index.new_id(name)
            p = {
                "id": pid, "name": name,
                "website": website, "website_unverified": True,
                # Straight from a published award notice, not checked by us.
                "verification": {"tier": "Listed", "verified": False, "verified_at": "", "services": ""},
                "email": email, "contact_page": "", "phone": "",
                "regions": [], "councils": [], "council_count": 0, "scope": "Local",
                "employees": None, "employee_confidence": "",
                "sector": list(sectors), "primary_cat": primary,
                "client_groups": list(groups), "is_housing_association": False,
                "description": "",
                "notes": "Added from award notice %s." % (str(row.get("Notice ID") or "").strip() or "(no id)"),
                "hq_address": "",
                "contracts": 0, "housing_contracts": 0, "total_contracts": 0,
                "contracts_list": [],
            }
            index.add(p)
            created.append(name)
            ledger.setdefault(p["id"], today)
        else:
            attached.add(name)
            if not p.get("email") and email:
                p["email"] = email
            if not p.get("website") and website:
                p["website"] = website

        for raw_council in named:
            council, key = canonical_council(raw_council, db, councilmap)
            region = regions.get(key, "")

            entry = next((c for c in p["contracts_list"]
                          if norm_council(c["council"]) == key), None)
            if entry is None:
                entry = {"council": council, "region": region, "n": 0, "scope": "Local",
                         "county": "", "via": "", "sectors": [], "titles": []}
                p["contracts_list"].append(entry)
            if title and title not in entry["titles"]:
                entry["titles"].append(title)
                entry["n"] = len(entry["titles"])
                links += 1
            for s in sectors:
                if s not in entry["sectors"]:
                    entry["sectors"].append(s)
            if council not in p["councils"]:
                p["councils"].append(council)
            if region and region not in p["regions"]:
                p["regions"].append(region)

            ids = db["c"].setdefault(council, [])
            if p["id"] not in ids:
                ids.append(p["id"])
            if key and key not in councilmap:
                councilmap[key] = [council]
            elif key and council not in councilmap[key]:
                councilmap[key].append(council)
            touched.add(council)

        for g in groups:
            if g not in p["client_groups"]:
                p["client_groups"].append(g)
        for s in sectors:
            if s not in p["sector"]:
                p["sector"].append(s)

    for p in providers:
        if p["contracts_list"]:
            p["council_count"] = len(p["councils"])
            p["contracts"] = sum(c["n"] for c in p["contracts_list"])
            p["housing_contracts"] = p["contracts"]
            p["total_contracts"] = p["contracts"]

    # Everything that predates the ledger is stamped with a baseline date, not
    # today's, so the first diff reports only what this run actually added
    # rather than announcing the whole database as new to every customer.
    for p in providers:
        ledger.setdefault(p["id"], BASELINE)

    print("source            : %s" % path.name)
    print("rows read         : %d" % len(rows))
    print("providers created : %d" % len(created))
    print("providers attached: %d existing" % len(attached))
    print("contract links    : %d" % links)
    print("councils touched  : %d" % len(touched))
    print("providers total   : %d" % len(providers))
    for k, v in skipped.most_common():
        print("  skipped: %-28s %d" % (k, v))

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0

    write_json(PROVIDERS, providers)
    write_json(DB, db)
    write_json(COUNCILMAP, councilmap)
    write_json(LEDGER, ledger, compact=False)
    print("\nwritten: providers.json, db.json, councilmap.json, provider_ledger.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
