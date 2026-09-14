"""Two cleanups over the provider dataset. Dry run by default; pass --apply to write.

1. Remove council schemes that were ingested as if they were providers.
   "Redbridge Supported Living Framework" is a framework, not an organisation a
   landlord can ring; its contact is the council's own social care inbox. Listing
   them inflates coverage and wastes a buyer's time.

2. Merge records that are the same organisation under different spellings
   ("Creative Support" and "Creative Support (CQC Registered ...)", three copies
   of The Cyrenians). Records are grouped by a normalised name and only merged
   when their web domains agree, so two different companies with similar names
   are never combined.

Usage:  python3 scripts/tidy_providers.py [--apply]
"""
import json, re, sys, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPLY = "--apply" in sys.argv

# Council-run schemes, frameworks and councils themselves. Checked by hand: each
# one's contact is a council inbox and the name describes a contract, not a body.
SCHEMES = [
    "Harrow Mental Health Supported Accommodation Block Contract",
    "London Borough of Bromley Extra Care Housing Re-Procurement",
    "Hackney AHI Supported Living Framework",
    "London Borough of Islington Mental Health Accommodation Pathway",
    "Newham PDPS Supported Accommodation Framework",
    "Redbridge Supported Living Framework",
    "Greenwich Living Options",
    "Greenwich Adults and Children Learning Disability Framework",
    "Greenwich Mental Health High Support Accommodation",
    "Homes for Wandsworth",
    "Hastings Borough Council",
]

# Hosts that are directories, job boards or portals rather than a provider's own
# site. Two records sharing one of these tell us nothing about being the same body.
SHARED_HOSTS = {"talents", "homeless", "nhs", "nwadcs", "procontract", "bidstats",
                "indeed", "edithjobs", "democracy", "gov", "ofsted", "cqc",
                "linkedin", "facebook", "google", "companieshouse", "charitycommission"}

def norm_name(s):
    s = unicodedata.normalize("NFKD", str(s)).lower()
    s = re.sub(r"\bt/a.*", "", s)          # "t/a Voyage Care", and glued: "T/AP3"
    s = re.sub(r"\btrading as\b.*", "", s)
    s = re.sub(r"\(.*?\)", " ", s)          # closed parenthetical
    s = re.sub(r"\(.*$", " ", s)            # truncated one, e.g. "(Lot 3 - Progress Serv"
    s = re.sub(r"\blot \d+.*", " ", s)
    s = re.sub(r"\b(ltd|limited|cic|plc|llp|group|the|uk)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(w[:-1] if len(w) > 4 and w.endswith("s") else w for w in s.split())

def domain(p):
    for u in (p.get("website"), p.get("email")):
        u = str(u or "").strip().lower()
        if not u:
            continue
        host = re.sub(r"^\w+://", "", u).split("/")[0].split("@")[-1]
        host = re.sub(r"^www\.", "", host)
        label = host.split(".")[0]
        if label and label not in SHARED_HOSTS and label not in ("mail", "gmail", "outlook", "hotmail", "yahoo", "info"):
            return label
    return ""

def domains_agree(doms):
    """One domain, or spellings of one domain: accomplishgroup / accomplish-group,
    depaul / depauluk. Requires a real shared stem, so metropolitan and mtvh, or
    three unrelated Cyrenians charities, stay apart."""
    flat = {d.replace("-", "") for d in doms}
    if len(flat) <= 1:
        return True
    ordered = sorted(flat, key=len)
    base = ordered[0]
    return len(base) >= 5 and all(d.startswith(base) for d in ordered)

def richness(p):
    return (len(p.get("councils") or []), bool(p.get("verification", {}).get("verified")),
            bool(p.get("phone")), bool(p.get("email")), len(p.get("contracts_list") or []),
            len(str(p.get("description") or "")))

def merge_into(keep, drop):
    for c in drop.get("contracts_list") or []:
        same = next((x for x in keep["contracts_list"] if x["council"] == c["council"]), None)
        if same is None:
            keep["contracts_list"].append(json.loads(json.dumps(c)))
            continue
        for t in c.get("titles") or []:
            if t not in same["titles"]:
                same["titles"].append(t)
        for s in c.get("sectors") or []:
            if s not in same["sectors"]:
                same["sectors"].append(s)
        same["n"] = max(len(same["titles"]), 1)
    for field in ("councils", "regions", "sector", "client_groups"):
        for v in drop.get(field) or []:
            if v not in keep.setdefault(field, []):
                keep[field].append(v)
    for field in ("email", "phone", "website", "contact_page", "hq_address", "description"):
        if not keep.get(field) and drop.get(field):
            keep[field] = drop[field]
    if drop.get("verification", {}).get("verified") and not keep.get("verification", {}).get("verified"):
        keep["verification"] = drop["verification"]
        keep["website_unverified"] = drop.get("website_unverified", False)
    if drop.get("is_housing_association"):
        keep["is_housing_association"] = True

def main():
    providers = json.loads((ROOT / "api/_data/providers.json").read_text())
    db = json.loads((ROOT / "api/_data/db.json").read_text())

    # ---- 1. drop council schemes ------------------------------------------
    drop_ids = {p["id"] for p in providers if p["name"] in SCHEMES}
    missing = [n for n in SCHEMES if not any(p["name"] == n for p in providers)]
    providers = [p for p in providers if p["id"] not in drop_ids]
    print("schemes removed          : %d%s" % (len(drop_ids), "  (not found: %s)" % missing if missing else ""))

    # ---- 2. merge duplicate records ---------------------------------------
    groups = {}
    for p in providers:
        groups.setdefault(norm_name(p["name"]), []).append(p)

    remap, merged, skipped = {}, 0, []
    for key, members in groups.items():
        if len(members) < 2 or not key:
            continue
        doms = {domain(p) for p in members} - {""}
        if not domains_agree(doms):
            skipped.append((key, [(p["name"], domain(p)) for p in members]))
            continue
        members.sort(key=richness, reverse=True)
        keep = members[0]
        for other in members[1:]:
            merge_into(keep, other)
            remap[other["id"]] = keep["id"]
            merged += 1
    kept_ids = {p["id"] for p in providers if p["id"] not in remap}
    providers = [p for p in providers if p["id"] in kept_ids]
    print("duplicates merged        : %d records folded into %d survivors"
          % (merged, len({v for v in remap.values()})))
    print("groups left alone        : %d (same name, different web domain)" % len(skipped))
    for key, m in skipped[:8]:
        print("     - %s" % " | ".join("%s [%s]" % (n, d or "no domain") for n, d in m))

    # ---- 3. repoint every id list -----------------------------------------
    def fix(ids):
        out = []
        for i in ids:
            i = remap.get(i, i)
            if i in kept_ids and i not in out:
                out.append(i)
        return out
    for k in list(db["c"]):
        # Keep a council whose only entries were schemes, as an empty list. The
        # area still resolves and shows its regional and UK-wide operators
        # instead of erroring; it simply has no local contract data yet.
        db["c"][k] = fix(db["c"][k])
    for k in list(db["county"]):
        db["county"][k] = fix(db["county"][k])
    for k in list(db["r"]):
        db["r"][k] = fix(db["r"][k])
    db["n"] = fix(db["n"])

    for p in providers:
        if p.get("contracts_list"):
            p["council_count"] = len(p.get("councils") or [])
            p["contracts"] = sum(c.get("n", 0) for c in p["contracts_list"])
            p["housing_contracts"] = p["contracts"]
            p["total_contracts"] = p["contracts"]

    print("providers                : %d" % len(providers))
    if APPLY:
        (ROOT / "api/_data/providers.json").write_text(json.dumps(providers))
        (ROOT / "api/_data/db.json").write_text(json.dumps(db))
        print("WRITTEN")
    else:
        print("dry run — nothing written (pass --apply)")

if __name__ == "__main__":
    main()
