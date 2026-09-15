"""Shared helpers for the fortnightly data refresh.

The pipeline is four steps, each its own script so a failing step can be re-run
on its own:

    harvest.py    portals  -> data/harvest/candidates_<date>.csv
    ingest.py     that CSV -> api/_data/{providers,db,councilmap}.json + ledger
    whats_new.py  ledger   -> data/updates/<date>/ (per-area report)
    draft.py      report   -> data/updates/<date>/emails/ (one draft per customer)

Everything in here is pure and offline so it can be unit-checked without
touching a portal or the live site.
"""
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

PROVIDERS = ROOT / "api/_data/providers.json"
DB = ROOT / "api/_data/db.json"
COUNCILMAP = ROOT / "api/_data/councilmap.json"
# id -> the date we first saw the provider. Drives "what's new since ...".
# Kept beside the data rather than inside providers.json so the file the API
# serves does not grow a field customers never see.
LEDGER = ROOT / "data/provider_ledger.json"
HARVEST_DIR = ROOT / "data/harvest"
UPDATES_DIR = ROOT / "data/updates"


def read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path, obj, compact=True):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        p.write_text(json.dumps(obj), encoding="utf-8")
    else:
        p.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


# ── council naming ──────────────────────────────────────────────────────────
# Port of normCouncil() in src/engine_maps.js. councilmap.json keys have to
# match what the postcode search derives from a postcodes.io admin_district,
# so a council added here is findable by postcode, borough and county search.
def norm_council(name):
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


_COUNCIL_DROP = {"council", "borough", "county", "city", "district", "the", "of",
                 "metropolitan", "unitary", "authority", "corporation", "mbc", "mdc", "cc"}


def council_key(s):
    """The looser key match.js uses for county and contract-relevance checks."""
    s = str(s or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(t for t in s.split() if t and t not in _COUNCIL_DROP)


# Awarding bodies that are not places a customer can search. Harvested awards
# from these still exist, but they must not create a new "council".
NOT_A_COUNCIL = [
    r"nhs|integrated care board|\bicb\b|foundation trust|teaching hospital|\bccg\b",
    r"ministry|home office|police|probation service|fire (and rescue|service)|ambulance",
    r"housing group|housing trust|housing society|housing association|homes england",
    r"\bhousing\b$|\bliving\b$|\bhomes\b$|\bgroup\b$",   # Amplius Living, Places for People Homes
    r"\blimited\b|\bltd\b|\bllp\b|\bplc\b|\bcic\b",
    r"procurement|commissioning support|shared (business )?service|shared services",
    r"esourcing|in-tend|eu supply|due north|atamis|lgss|supply hertfordshire",
    r"regional framework|university|college|academy|\bschool\b",
    r"combined authority|greater london authority|\bgla\b|transport for",
]


def is_council(name):
    n = str(name or "").lower()
    if not n.strip():
        return False
    return not any(re.search(p, n) for p in NOT_A_COUNCIL)


# ── provider identity ───────────────────────────────────────────────────────
def norm_name(s):
    s = unicodedata.normalize("NFKD", str(s)).lower()
    s = re.sub(r"\bt/a\b.*", "", s)
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\b(ltd|limited|cic|c\.i\.c|plc|llp|group|the)\b", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    words = [w[:-1] if len(w) > 4 and w.endswith("s") else w for w in s.split()]
    return " ".join(words)


def domain_key(*urls):
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


# Obvious non-supplier rows the portals emit.
JUNK_NAME = re.compile(
    r"^(see |please see|tbc\b|n/?a$|none$|various$|\d+$|.*attachment|.*breakdown|.*weblink|.*supplier$)",
    re.I)


def is_real_supplier(name):
    n = str(name or "").strip()
    return bool(n) and len(n) > 2 and not JUNK_NAME.match(n)


class ProviderIndex:
    """Match a harvested supplier against the providers we already hold."""

    def __init__(self, providers):
        self.providers = providers
        self.by_id = {p["id"]: p for p in providers}
        self.by_norm = {norm_name(p["name"]): p for p in providers}
        self.by_domain = {}
        for p in providers:
            d = domain_key(p.get("website"), p.get("email"))
            if d:
                self.by_domain.setdefault(d, p)

    def find(self, name, website="", email=""):
        hit = self.by_norm.get(norm_name(name))
        if hit:
            return hit
        d = domain_key(website, email)
        return self.by_domain.get(d) if d else None

    def add(self, provider):
        self.providers.append(provider)
        self.by_id[provider["id"]] = provider
        self.by_norm[norm_name(provider["name"])] = provider
        d = domain_key(provider.get("website"), provider.get("email"))
        if d:
            self.by_domain.setdefault(d, provider)

    def new_id(self, name):
        pid = slug(name)
        while pid in self.by_id:
            pid += "-2"
        return pid
