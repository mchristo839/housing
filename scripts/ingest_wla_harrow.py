"""Ingest SL_providers_by_tender.xlsx — West London Alliance framework + LB Harrow awards.

For every (provider, tender) pair in the workbook:
  * provider already in providers.json  -> attach the tender to it
  * provider not yet known              -> create the provider, then attach

A tender attaches to the councils that commissioned it. The West London
Alliance framework is commissioned jointly by seven boroughs, so its providers
become local providers for all seven. The Harrow notices attach to Harrow only.

Providers the source flags as not being supported-living providers are skipped.

Idempotent: re-running will not duplicate providers, contracts or titles.
Usage:  python3 scripts/ingest_wla_harrow.py [path/to/workbook.xlsx]
"""
import json, re, sys, unicodedata
from pathlib import Path
import openpyxl

ROOT = Path(__file__).resolve().parent.parent
XLSX = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "SL_providers_by_tender.xlsx"

# Councils that commissioned each notice, written exactly as db.json already
# keys them so the new rows merge with what is there rather than splitting.
WLA = ["Ealing", "London Borough of Barnet Council", "London Borough of Brent",
       "London Borough of Harrow", "London Borough of Hounslow",
       "London Borough of Hillingdon", "London Borough of Hammersmith & Fulham"]
HARROW = ["London Borough of Harrow"]
NOTICE_COUNCILS = {
    "003698-2026": WLA, "078991-2026": WLA,
    "021470-2021": HARROW, "052790-2025": HARROW, "059125-2025": HARROW,
    "041651-2026": HARROW, "030822-2026": HARROW, "083523-2025": HARROW,
}
# Client group on the notice -> the site's own vocabulary.
GROUPS = {
    "young people": (["Young people & care leavers"],
                     ["Supported accommodation", "Young people", "Care leavers", "Housing"]),
    "care leavers": (["Young people & care leavers"],
                     ["Supported accommodation", "Care leavers", "Housing"]),
    "mental health": (["Mental health"], ["Supported accommodation", "Mental health", "Housing"]),
    "rough sleep": (["Homelessness"], ["Supported accommodation", "Homelessness", "Housing"]),
}

def norm_name(s):
    s = unicodedata.normalize("NFKD", str(s)).lower()
    s = re.sub(r"\bt/a\b.*", "", s)          # "Abiding Limited t/a Abiding Care"
    s = re.sub(r"\(.*?\)", " ", s)            # "People Potential Possibilities (P3)"
    s = re.sub(r"\b(ltd|limited|cic|c\.i\.c|plc|llp|group|the)\b", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    # "Pathfinders Care Services" and "Pathfinder Care Services" are one company.
    words = [w[:-1] if len(w) > 4 and w.endswith("s") else w for w in s.split()]
    return " ".join(words)

def domain_key(*urls):
    """First label of the host, so p3charity.org and www.p3charity.org/?utm=...
    and pathfinderscareservices.com all key the same as their .org twin."""
    for u in urls:
        u = str(u or "").strip().lower()
        if not u:
            continue
        host = re.sub(r"^\w+://", "", u).split("/")[0].split("@")[-1]
        host = re.sub(r"^www\.", "", host)
        label = host.split(".")[0]
        if label and label not in ("mail", "info", "gmail", "outlook", "hotmail", "yahoo"):
            return label
    return ""

def slug(s):
    s = unicodedata.normalize("NFKD", str(s)).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "provider"

def classify(client_group):
    cg = str(client_group or "").lower()
    for key, val in GROUPS.items():
        if key in cg:
            return val
    return (["Young people & care leavers"], ["Supported accommodation", "Housing"])

def main():
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb["Providers"]
    hdr = [c.value for c in ws[1]]
    rows = [dict(zip(hdr, r)) for r in ws.iter_rows(min_row=2, values_only=True) if r[0]]

    providers = json.loads((ROOT / "api/_data/providers.json").read_text())
    db = json.loads((ROOT / "api/_data/db.json").read_text())
    by_norm = {norm_name(p["name"]): p for p in providers}
    by_id = {p["id"]: p for p in providers}
    by_domain = {}
    for p in providers:
        d = domain_key(p.get("website"), p.get("email"))
        if d:
            by_domain.setdefault(d, p)

    added, attached, skipped, touched = [], [], [], set()

    for row in rows:
        name = str(row["Provider"]).strip()
        note = str(row.get("Flag / Note") or "")
        if "NOT a supported-living provider" in note:
            skipped.append((name, note.split(" - ", 1)[-1][:60]))
            continue
        notice = str(row["Notice ID"]).strip()
        councils = NOTICE_COUNCILS.get(notice)
        if not councils:
            skipped.append((name, "notice %s has no council mapping" % notice))
            continue
        title = str(row["Tender Title"]).strip()
        groups, sectors = classify(row.get("Client Group"))

        dom = domain_key(row.get("Website"), row.get("Contact Email"))
        p = by_norm.get(norm_name(name)) or (by_domain.get(dom) if dom else None)
        if p is None:
            pid = slug(name)
            while pid in by_id:
                pid += "-2"
            p = {
                "id": pid, "name": name,
                "website": str(row.get("Website") or "").strip(),
                "website_unverified": True,
                # Straight from a published award notice, not checked by us.
                "verification": {"tier": "Listed", "verified": False, "verified_at": "", "services": ""},
                "email": str(row.get("Contact Email") or "").strip(),
                "contact_page": "", "phone": "",
                "regions": ["London"], "councils": [], "council_count": 0, "scope": "Local",
                "employees": None, "employee_confidence": "",
                "sector": sectors, "primary_cat": "Supported accommodation",
                "client_groups": groups, "is_housing_association": False,
                "description": "", "notes": "Added from Find a Tender notice %s." % notice,
                "hq_address": "",
                "contracts": 0, "housing_contracts": 0, "total_contracts": 0,
                "contracts_list": [],
            }
            providers.append(p)
            by_norm[norm_name(name)] = p
            by_id[pid] = p
            if dom:
                by_domain.setdefault(dom, p)
            added.append(name)
        else:
            attached.append(name)
            # Fill blanks only; never overwrite a verified contact with notice data.
            if not p.get("email") and row.get("Contact Email"):
                p["email"] = str(row["Contact Email"]).strip()
            if not p.get("website") and row.get("Website"):
                p["website"] = str(row["Website"]).strip()

        for council in councils:
            entry = next((c for c in p["contracts_list"] if c["council"] == council), None)
            if entry is None:
                entry = {"council": council, "region": "London", "n": 0, "scope": "Local",
                         "county": "", "via": "West London Alliance" if councils is WLA else "",
                         "sectors": [], "titles": []}
                p["contracts_list"].append(entry)
            if title not in entry["titles"]:
                entry["titles"].append(title)
                entry["n"] = len(entry["titles"])
            for s in sectors:
                if s not in entry["sectors"]:
                    entry["sectors"].append(s)
            if council not in p["councils"]:
                p["councils"].append(council)
            ids = db["c"].setdefault(council, [])
            if p["id"] not in ids:
                ids.append(p["id"])
            touched.add(council)

        for g in groups:
            if g not in p["client_groups"]:
                p["client_groups"].append(g)
        for s in sectors:
            if s not in p["sector"]:
                p["sector"].append(s)
        if "London" not in p["regions"]:
            p["regions"].append("London")

    # Recompute the derived contract counters for everything we touched.
    for p in providers:
        if p["contracts_list"]:
            p["council_count"] = len(p["councils"])
            p["contracts"] = sum(c["n"] for c in p["contracts_list"])
            p["housing_contracts"] = p["contracts"]
            p["total_contracts"] = p["contracts"]

    (ROOT / "api/_data/providers.json").write_text(json.dumps(providers))
    (ROOT / "api/_data/db.json").write_text(json.dumps(db))

    print("providers created : %d" % len(added))
    print("tenders attached  : %d rows onto existing providers" % len(attached))
    print("rows skipped      : %d" % len(skipped))
    for n, why in skipped:
        print("   - %s (%s)" % (n, why))
    print("councils touched  : %s" % ", ".join(sorted(touched)))
    print("providers.json    : %d records" % len(providers))

if __name__ == "__main__":
    main()
