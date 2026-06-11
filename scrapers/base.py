"""
Base classes + shared filter logic for portal scrapers.

Every scraper inherits from PortalScraper and returns awards in a uniform
dict shape (CONTRACT_FIELDS below). The orchestrator (scripts/scrape_all.py)
writes the raw JSON per portal, and scripts/normalise.py turns them into
the column schema the main pipeline expects.
"""
import re
import time
import json
import urllib.request
import urllib.parse
import urllib.error

# ── Normalised contract-award schema ────────────────────────────────────────
# Every scraper yields a dict with these keys. Missing fields → empty string.
# The first 17 are the same columns as data/care_housing_database_v2_ENRICHED.xlsx's
# "Company × Council × Sector" sheet. The last 5 are audit-trail extras that
# normalise.py writes into data/scraped/normalised.xlsx but are NOT carried
# into the main pipeline.
CONTRACT_FIELDS = [
    # main schema (matches the source workbook exactly)
    "Company", "Sector", "Council", "Contracts (this council, this sector)",
    "Company Total (all sectors)", "Company Total — Homecare", "Company Total — Housing",
    "Companies House", "Is SME", "Is VCSE", "Categories", "Most Recent Award",
    "Contract Titles", "ONS Region", "Commissioner Type", "Geographic Scope",
    "Asylum Contractor",
    # audit-trail extras (scraped-only)
    "source_portal", "source_url", "source_id", "scraped_at",
    "cpv_codes", "contract_value_gbp", "status",
]

ONS_REGIONS = {
    "East Midlands", "East of England", "London", "North East", "North West",
    "South East", "South West", "West Midlands", "Yorkshire & The Humber",
    "Wales", "Scotland", "Northern Ireland", "National",
}

# ── Housing-title filter ───────────────────────────────────────────────────
# A contract title MUST match one of these to count as housing-related.
# Comprehensive set per user definition (Jun 2026):
#   housing | accommodation | supported living | assisted living
#   | homelessness | young people | supported accommodation
#   | child services | CAS | temporary accommodation | asylum | social housing
# Plus all the previously-included specialist terms (extra care, sheltered,
# hostel, refuge, CAS-2/3 specifics, NHS S117/CHC etc.).
HOUSING_TITLE = re.compile(
    r"\b("
    # CORE user-defined terms
    r"housing|accommodation|"
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
    # OTHER housing terms we previously included
    r"extra care|sheltered (housing|accommodation)|hostel|refuge|"
    r"move[- ]?on|tenanc|"
    r"approved premises|bail accommodation|probation accommodation|"
    r"continuing healthcare|chc|section 117|s117|"
    r"transforming care|building the right support|btrs|"
    r"step[- ]?down|forensic|complex needs|"
    r"floating support|semi[- ]?independent|"
    r"dispersal accommodation|housing related support|housing-related support"
    r")\b",
    re.I,
)

# Strip false positives — title MUST NOT be one of these (unless it ALSO matches
# the positive list above and isn't pure-homecare).
EXCLUDE_TITLE = re.compile(
    r"\bdomiciliary\b|home ?care service|\bhomecare\b|reablement|"
    r"\brespite\b|day care|short breaks|sitting service|"
    r"facilities management|street lighting|highways|repairs and maintenance|"
    r"painting and decorating|grounds maintenance|window cleaning|"
    r"catering services|meals on wheels|kitchen replacement|food supply|"
    r"laundry service|linen service|"
    r"gp surgery|clinic\b|pharmacy|dental|optical|audiology|"
    r"medicines|prescribing|dispensing|pathology|diagnostics|"
    r"imaging|outpatient|theatre|surgery|"
    r"\bppe\b|personal protective|"
    r"\bcovid.*wave\b|covid emergency|"
    r"research services|consultancy|evaluation|impact assessment|"
    r"interpretation|translation|patient transport|"
    r"\bit services?\b|digital transformation|epr\b|"
    r"furniture|furnishings|carpet",
    re.I,
)

# Housing CPV codes (Common Procurement Vocabulary) — strong positive signal.
HOUSING_CPV = {
    "85311000",  # Social work services with accommodation
    "85311100",  # Welfare services for the elderly
    "85311200",  # Welfare services for the disabled
    "85311300",  # Welfare services for children and young people
    "85312500",  # Rehabilitation services
    "85320000",  # Social services
    "85144000",  # Residential health facilities services
    "85144100",  # Residential nursing care services
    "98341000",  # Accommodation services
    "98341110",  # Hostel services
    "70110000",  # Real estate dev / sale / lease services
    "70210000",  # Residential property leasing
}

# CPV codes to actively EXCLUDE even if the title matches (clinical / supply).
CLINICAL_CPV_PREFIX = ("33", "60", "72")  # drugs, transport, IT

# ── ONS-region resolver (NUTS code → ONS region) ────────────────────────────
# UK NUTS / ITL region codes mapped to our ONS region names.
NUTS_TO_ONS = {
    "UKC": "North East", "UKD": "North West",
    "UKE": "Yorkshire & The Humber",
    "UKF": "East Midlands", "UKG": "West Midlands",
    "UKH": "East of England", "UKI": "London",
    "UKJ": "South East", "UKK": "South West",
    "UKL": "Wales", "UKM": "Scotland", "UKN": "Northern Ireland",
}

def nuts_to_ons(nuts_code):
    if not nuts_code:
        return ""
    # take the first 3 chars (e.g. "UKI3" → "UKI")
    prefix = str(nuts_code)[:3].upper()
    return NUTS_TO_ONS.get(prefix, "")

# ── Helpers ─────────────────────────────────────────────────────────────────
def is_housing_title(title):
    """Return True iff title looks like a housing/supported-accommodation contract."""
    t = str(title or "").strip()
    if not t:
        return False
    if EXCLUDE_TITLE.search(t):
        # allowed if it ALSO matches housing AND isn't a pure-homecare/respite phrase
        # in practice the resolver in build_data.py handles the final decision;
        # we're permissive here so the scraper captures, and the normaliser
        # / dedup step filters.
        return bool(HOUSING_TITLE.search(t))
    return bool(HOUSING_TITLE.search(t))

def is_housing_cpv(cpv_codes):
    """Return True iff any housing CPV is present and no clinical CPV dominates."""
    if not cpv_codes:
        return False
    codes = [str(c).strip() for c in cpv_codes if c]
    if any(c in HOUSING_CPV for c in codes):
        return True
    if any(c.startswith(CLINICAL_CPV_PREFIX) for c in codes):
        # majority-clinical → reject
        return False
    return False

def empty_row():
    return {k: "" for k in CONTRACT_FIELDS}

# ── Base scraper class ──────────────────────────────────────────────────────
class PortalScraper:
    """One subclass per portal. Override `scrape()` to yield normalised dicts.

    The base class provides polite HTTP (User-Agent, rate-limit, retry) and a
    raw-output writer.
    """

    PORTAL_NAME = "abstract"  # override
    USER_AGENT = "findahousingprovider-scraper/1.0 (+contact: paul@pioneerdrinks.com)"
    RATE_LIMIT_SEC = 6.0  # both FTS and CF limit ~12 req/min → 5+ sec between calls
    LOCKOUT_RETRY_SEC = 130  # 429 says "retry after 120s"; wait a hair longer

    def __init__(self, min_date="2020-01-01", max_date=None):
        self.min_date = min_date
        self.max_date = max_date
        self._last_req_at = 0.0

    # subclass hook
    def scrape(self):
        """Yield normalised contract-award dicts (one per supplier-region-lot)."""
        raise NotImplementedError

    # ── HTTP helpers ────────────────────────────────────────────────────────
    def _sleep_if_needed(self):
        gap = time.monotonic() - self._last_req_at
        if gap < self.RATE_LIMIT_SEC:
            time.sleep(self.RATE_LIMIT_SEC - gap)
        self._last_req_at = time.monotonic()

    def get_json(self, url, params=None, max_retries=3):
        """GET a URL, return parsed JSON. Polite rate-limiting + retry.
        On 429 we wait the full lockout (~120s) before retrying, since both
        FTS and Contracts Finder return that specific window."""
        if params:
            url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        last_err = None
        for attempt in range(max_retries):
            self._sleep_if_needed()
            req = urllib.request.Request(url, headers={
                "User-Agent": self.USER_AGENT,
                "Accept": "application/json",
            })
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as e:
                if e.code in (429, 403):
                    # Contracts Finder uses 403 for rate-limit; Find-a-Tender uses 429.
                    # Both want a multi-minute wait before retry.
                    wait = self.LOCKOUT_RETRY_SEC
                    print(f"    ({e.code} rate-limit hit; sleeping {wait}s and retrying)")
                    time.sleep(wait)
                    last_err = e
                    continue
                if e.code == 503:
                    time.sleep(2 ** attempt * 2)
                    last_err = e
                    continue
                raise
            except Exception as e:
                last_err = e
                time.sleep(2 ** attempt)
        raise last_err
