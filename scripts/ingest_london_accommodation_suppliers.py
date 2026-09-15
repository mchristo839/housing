"""Ingest accommodation_suppliers_with_council_access.csv — the London update.

Every row is one (supplier, framework) award. The row's "Councils Named" column
is the authoritative list of authorities that can call off that award, so the
supplier becomes a provider for each of those councils and shows up in their
postcode, borough and county searches.

  * supplier already in providers.json -> attach the framework to it
  * supplier not yet known             -> create the provider, then attach

Councils attach under the spelling db.json already uses, so the new rows merge
into the existing council buckets instead of splitting them. Essex and
Hertfordshire are county-tier commissioners and additionally index into
db.county; the London boroughs and the two Northamptonshire unitaries are local.

Idempotent: re-running will not duplicate providers, contracts or titles.
Usage:  python3 scripts/ingest_london_accommodation_suppliers.py [path/to/csv]
"""
import csv, json, re, sys, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/accommodation_suppliers_with_council_access.csv"

# Council as the CSV writes it -> the db.json key, its tier and its geography.
# The db key is an existing spelling wherever one exists, so these awards land in
# the same bucket the council's current providers are in.
LOCAL = "Local"
COUNTY = "County"
COUNCILS = {
    "Barking and Dagenham":         ("London Borough of Barking and Dagenham", LOCAL, "London", ""),
    "Barnet":                       ("London Borough of Barnet Council", LOCAL, "London", ""),
    "Bexley":                       ("London Borough of Bexley", LOCAL, "London", ""),
    "Brent":                        ("London Borough of Brent", LOCAL, "London", ""),
    "Bromley":                      ("London Borough of Bromley", LOCAL, "London", ""),
    "Camden":                       ("London Borough of Camden", LOCAL, "London", ""),
    "City of London":               ("City of London Corporation", LOCAL, "London", ""),
    "Croydon":                      ("London Borough of Croydon", LOCAL, "London", ""),
    "Ealing":                       ("Ealing", LOCAL, "London", ""),
    "Enfield":                      ("London Borough of Enfield", LOCAL, "London", ""),
    "Greenwich":                    ("Royal Borough of Greenwich", LOCAL, "London", ""),
    "Hackney":                      ("London Borough of Hackney", LOCAL, "London", ""),
    "Hammersmith and Fulham":       ("London Borough of Hammersmith & Fulham", LOCAL, "London", ""),
    "Haringey":                     ("London Borough Of Haringey", LOCAL, "London", ""),
    "Harrow":                       ("London Borough of Harrow", LOCAL, "London", ""),
    "Havering":                     ("LONDON BOROUGH OF HAVERING", LOCAL, "London", ""),
    "Hillingdon":                   ("London Borough of Hillingdon", LOCAL, "London", ""),
    "Hounslow":                     ("London Borough of Hounslow", LOCAL, "London", ""),
    "Islington":                    ("Islington Council", LOCAL, "London", ""),
    "Kensington and Chelsea":       ("Royal Borough of Kensington and Chelsea", LOCAL, "London", ""),
    "Kingston upon Thames":         ("Royal Borough of Kingston Upon Thames", LOCAL, "London", ""),
    "Lambeth":                      ("London Borough of Lambeth", LOCAL, "London", ""),
    "Lewisham":                     ("London Borough of Lewisham", LOCAL, "London", ""),
    "Merton":                       ("London Borough of Merton", LOCAL, "London", ""),
    "Newham":                       ("London Borough of Newham", LOCAL, "London", ""),
    "Redbridge":                    ("London Borough of Redbridge", LOCAL, "London", ""),
    "Richmond upon Thames":         ("London Borough of Richmond upon Thames", LOCAL, "London", ""),
    "Southwark":                    ("Southwark", LOCAL, "London", ""),
    "Sutton":                       ("London Borough of Sutton", LOCAL, "London", ""),
    "Tower Hamlets":                ("London Borough of Tower Hamlets", LOCAL, "London", ""),
    "Waltham Forest":               ("London Borough of Waltham Forest", LOCAL, "London", ""),
    "Wandsworth":                   ("London Borough of Wandsworth", LOCAL, "London", ""),
    "Westminster":                  ("Westminster City Council", LOCAL, "London", ""),
    # County-tier commissioners: these also index into db.county.
    "Essex County Council":         ("Essex County Council", COUNTY, "East of England", "essex"),
    "Hertfordshire County Council": ("Hertfordshire County Council", COUNTY, "East of England", "hertfordshire"),
    # Northamptonshire Children's Trust buys for both unitaries; neither is a county council.
    "North Northamptonshire Council": ("North Northamptonshire Council", LOCAL, "East Midlands", ""),
    "West Northamptonshire Council":  ("West Northamptonshire Council", LOCAL, "East Midlands", ""),
}

# Framework wording -> (client_groups, sectors, primary_cat), first match wins.
# Ordered most specific first: a "16+ semi-independent mental health" framework is
# a young people's service, not an adult mental health one.
RULES = [
    (r"16\+|semi.?independent|young pe|young pers|care leaver|children|looked after|child",
     ["Young people & care leavers"], ["Supported accommodation", "Young people", "Care leavers", "Housing"], "Supported accommodation"),
    (r"domestic (violence|abuse)|vawg|refuge|women",
     ["Domestic abuse"], ["Supported accommodation", "Refuge", "Housing"], "Supported accommodation"),
    (r"rough sleep|housing first|homeless|single homeless",
     ["Homelessness"], ["Supported accommodation", "Homelessness", "Housing"], "Supported accommodation"),
    (r"cas3|probation|bail",
     ["Homelessness"], ["Supported accommodation", "Probation accommodation", "Housing"], "Supported accommodation"),
    (r"temporary accommodation|nightly purchased|nrpf|emergency",
     [], ["Emergency accommodation", "Housing"], "Emergency accommodation"),
    (r"mental health",
     ["Mental health"], ["Supported living", "Mental health", "Housing"], "Supported living"),
    (r"learning disab|learing disab|autism",
     ["Learning disabilities"], ["Supported living", "Learning disability", "Housing"], "Supported living"),
    (r"extra care|older",
     ["Older people"], ["Supported living", "Housing"], "Supported living"),
    (r"supported living|independent living|tenancy sustainment|housing related support|floating support",
     [], ["Supported living", "Housing"], "Supported living"),
]
DEFAULT = ([], ["Supported accommodation", "Housing"], "Supported accommodation")


def classify(framework):
    text = str(framework or "").lower()
    for pattern, groups, sectors, primary in RULES:
        if re.search(pattern, text):
            return groups, sectors, primary
    return DEFAULT


def norm_name(s):
    s = unicodedata.normalize("NFKD", str(s)).lower()
    s = re.sub(r"\bt/a\b.*", "", s)            # "Abiding Limited t/a Abiding Care"
    s = re.sub(r"\(.*?\)", " ", s)              # "People Potential Possibilities (P3)"
    s = re.sub(r"\b(ltd|limited|cic|c\.i\.c|plc|llp|group|the)\b", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    words = [w[:-1] if len(w) > 4 and w.endswith("s") else w for w in s.split()]
    return " ".join(words)


def domain_key(*urls):
    """First label of the host, so exodushousing.co.uk and www.exodushousing.co.uk
    and info@exodushousing.co.uk all key the same."""
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


def norm_council(name):
    """Port of normCouncil() in src/engine_maps.js — councilmap.json keys have to
    match what the postcode search derives from a postcodes.io admin_district."""
    if not name:
        return ""
    n = str(name).lower().strip().replace("&", " and ")
    n = re.sub(r",\s*city of$", " city", n)
    n = re.sub(r"^city of london corporation$", "city of london", n)
    n = re.sub(r"^(?:the\s+)?(?:london borough of|royal borough of)\s+", "", n)
    n = re.sub(r"\b(council|metropolitan borough|borough|county|district|unitary authority|mbc|lbc|the )\b", " ", n)
    if n != "city of london" and not n.startswith("city of london "):
        n = re.sub(r"\bcity\b", " ", n)
    n = re.sub(r"[^\w\s]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def title_for(row):
    """Framework name plus the award's provenance, matching how existing
    contract titles carry their notice reference."""
    framework = str(row["Framework"]).strip().rstrip("-").strip()
    notice = str(row["Notice ID"]).strip()
    awarded = str(row["Awarded Date"]).strip()
    bits = []
    if awarded:
        bits.append("Awarded %s." % awarded)
    if notice:
        bits.append("Notice %s." % notice)
    return "%s — %s" % (framework, " ".join(bits)) if bits else framework


def main():
    with open(CSV_PATH, encoding="utf-8-sig") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("Supplier") or "").strip()]

    providers = json.loads((ROOT / "api/_data/providers.json").read_text())
    db = json.loads((ROOT / "api/_data/db.json").read_text())
    councilmap = json.loads((ROOT / "api/_data/councilmap.json").read_text())

    by_norm = {norm_name(p["name"]): p for p in providers}
    by_id = {p["id"]: p for p in providers}
    by_domain = {}
    for p in providers:
        d = domain_key(p.get("website"), p.get("email"))
        if d:
            by_domain.setdefault(d, p)

    added, attached, unmapped = [], set(), {}
    touched, links_made = set(), 0

    for row in rows:
        name = str(row["Supplier"]).strip()
        framework = str(row["Framework"]).strip()
        groups, sectors, primary = classify(framework)
        title = title_for(row)

        named = [c.strip() for c in str(row["Councils Named"]).split(";") if c.strip()]
        targets = []
        for c in named:
            if c in COUNCILS:
                targets.append(COUNCILS[c])
            else:
                unmapped[c] = unmapped.get(c, 0) + 1
        if not targets:
            continue

        website = str(row.get("Website") or "").strip()
        email = str(row.get("Email") or "").strip()
        dom = domain_key(website, email)

        p = by_norm.get(norm_name(name)) or (by_domain.get(dom) if dom else None)
        if p is None:
            pid = slug(name)
            while pid in by_id:
                pid += "-2"
            p = {
                "id": pid, "name": name,
                "website": website,
                # Straight from a published award notice, not checked by us.
                "website_unverified": True,
                "verification": {"tier": "Listed", "verified": False, "verified_at": "", "services": ""},
                "email": email,
                "contact_page": "", "phone": "",
                "regions": [], "councils": [], "council_count": 0, "scope": LOCAL,
                "employees": None, "employee_confidence": "",
                "sector": list(sectors), "primary_cat": primary,
                "client_groups": list(groups), "is_housing_association": False,
                "description": "",
                "notes": "Added from the %s award notice %s." % (framework, str(row["Notice ID"]).strip()),
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
            attached.add(name)
            # Fill blanks only; never overwrite a verified contact with notice data.
            if not p.get("email") and email:
                p["email"] = email
            if not p.get("website") and website:
                p["website"] = website

        for council, scope, region, county in targets:
            # Attach to whatever spelling this provider already uses for the
            # council ("London Borough of Havering" vs "LONDON BOROUGH OF
            # HAVERING"), so the award does not render as a second, near-identical
            # row next to the one already there. The db.c index below still goes
            # under the canonical key regardless of how the entry is spelled.
            entry = next((c for c in p["contracts_list"]
                          if norm_council(c["council"]) == norm_council(council)), None)
            if entry is None:
                entry = {"council": council, "region": region, "n": 0, "scope": scope,
                         "county": county, "via": "", "sectors": [], "titles": []}
                p["contracts_list"].append(entry)
            if title not in entry["titles"]:
                entry["titles"].append(title)
                entry["n"] = len(entry["titles"])
                links_made += 1
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
            if scope == COUNTY and county:
                cids = db["county"].setdefault(county, [])
                if p["id"] not in cids:
                    cids.append(p["id"])
            touched.add(council)

            # Make the council findable by name if it is new to the index.
            key = norm_council(council)
            if key and key not in councilmap:
                councilmap[key] = [council]
            elif key and council not in councilmap[key]:
                councilmap[key].append(council)

        for g in groups:
            if g not in p["client_groups"]:
                p["client_groups"].append(g)
        for s in sectors:
            if s not in p["sector"]:
                p["sector"].append(s)

    # Recompute the derived counters for every provider that carries contracts.
    for p in providers:
        if p["contracts_list"]:
            p["council_count"] = len(p["councils"])
            p["contracts"] = sum(c["n"] for c in p["contracts_list"])
            p["housing_contracts"] = p["contracts"]
            p["total_contracts"] = p["contracts"]

    (ROOT / "api/_data/providers.json").write_text(json.dumps(providers))
    (ROOT / "api/_data/db.json").write_text(json.dumps(db))
    (ROOT / "api/_data/councilmap.json").write_text(json.dumps(councilmap, separators=(",", ":")))

    print("rows read          : %d" % len(rows))
    print("providers created  : %d" % len(added))
    print("providers attached : %d existing" % len(attached))
    print("contract links made: %d" % links_made)
    print("providers.json     : %d records" % len(providers))
    print("councils touched   : %d" % len(touched))
    for c in sorted(touched):
        print("   %-45s %d providers" % (c, len(db["c"][c])))
    if unmapped:
        print("UNMAPPED councils  : %s" % unmapped)


if __name__ == "__main__":
    main()
