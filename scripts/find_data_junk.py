"""Scan the live provider universe for data junk:
   - Names that are clearly tender-document text fragments
   - Websites whose domain doesn't credibly belong to the supplier
     (hotel booking sites, tourism, directories, e-commerce, etc.)

Prints the candidate-for-removal list. No changes applied — that's a separate
build-side filter.
"""
import json, re, sys, io
from urllib.parse import urlparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

prov = json.load(open('api/_data/providers.json', encoding='utf-8'))

# 1. Names that look like tender-document text rather than a real supplier
JUNK_NAME_TEXT = re.compile(
    r"^(?:None awarded|Not awarded|Please Note|Lot \d+ ?[-–]?|"
    r"Sai-?pac \(on behalf|None\b|N/?A\b|TBC|TBD|Tender (?:closed|withdrawn)|"
    r"Not selected|Discontin|Award (?:withdrawn|cancelled))",
    re.I
)

# 2. Domain blacklist — sites that shouldn't be a supplier homepage
BLACKLIST_DOMAINS = {
    # hotel/travel booking
    'bluepillow.com', 'booking.com', 'expedia.com', 'tripadvisor.com',
    'visitwestwardho.co.uk',
    # e-commerce / generic directories
    'amazon.co.uk', 'amazon.com', 'ebay.co.uk', 'mapquest.com',
    'tracxn.com', 'tinytax.co.uk', 'companywall.co.uk', 'company-check.co.uk',
    'okredo.lt', 'wikipedia.org',
    # dictionaries / typography
    'merriam-webster.com', 'piliapp.com',
    # other unrelated commercial sites
    'gcw.co.uk',                # commercial property news
    'weirbags.co.uk',           # luggage
    'sseenergysolutions.co.uk', # energy
    'paypoint.com',             # payments
    'graftonmerchantinggb.co.uk', # builders merchant
    'ssi-schaefer.com',         # warehouse logistics
    'btinternet.com',           # ISP fallback
    'roosacademyofperformingarts.co.uk',  # performing arts academy
    'inspirations-oadby.co.uk', # Indian restaurant
    'canleyclassics.com',       # car parts
    'cms.law',                  # law firm
    'bajajconsumercare.com',    # consumer care brand
    'newleatherheadliving.wordpress.com',
    'caseboard.io',             # legal case mgmt
    'd3tenders.com',            # tender portal not provider
    'collab365.com',
    'fan',                      # weird TLD
    'elder.org',                # different organisation
    'careschoices.co.uk',       # directory
    'consolidate.org.uk',       # generic registry
    'londonconsultancy4you.co.uk', # one-person consultancy
    'iwm.org.uk',               # Imperial War Museum
    'shop.fsip.biz',            # generic shop
    'br.bluepillow.com',
    'immi.homeaffairs.gov.au',
    'executivecompass.co.uk',   # bid-writing service
}

# Also flag domains that look directory-like or country-mismatched
DIRECTORY_PATTERN = re.compile(
    r'\b(?:carechoices|carehome|192\.com|companyhouse|companiesintheuk|'
    r'patient\.info|nhs\.uk/services|cqc\.org\.uk|ofsted\.gov\.uk|'
    r'find-and-update\.company-information|rocketreach|zoominfo)\b', re.I)

def domain_of(url):
    if not url: return ''
    try:
        h = urlparse(url if url.startswith('http') else 'https://' + url).netloc.lower()
        return re.sub(r'^www\.', '', h)
    except Exception:
        return ''

candidates = []
for p in prov:
    name = (p.get('name') or '').strip()
    website = (p.get('website') or '').strip()
    domain = domain_of(website)
    reasons = []

    if JUNK_NAME_TEXT.match(name):
        reasons.append('tender-text name')

    if domain in BLACKLIST_DOMAINS:
        reasons.append(f'unrelated domain ({domain})')

    if domain and DIRECTORY_PATTERN.search(domain):
        reasons.append(f'directory listing ({domain})')

    # Generic placeholder names
    if name.lower() in {'none', 'na', 'n/a', 'tbc', 'tbd', 'placeholder', 'squared', 'fazz ltd', 'fazz'}:
        reasons.append('placeholder / single-word non-name')

    # Australia / overseas in the URL
    if domain.endswith('.com.au'):
        reasons.append('Australian domain')

    # NOTE about "Lot 1 / Lot 2"
    if re.match(r'^Lot\s*\d+\b', name, re.I):
        reasons.append('tender lot label, not a supplier')

    if reasons:
        candidates.append((name, domain, ' / '.join(reasons)))

print(f"{len(candidates)} candidate data-junk rows:\n")
print(f"{'#':>3s}  {'NAME':50s}  {'DOMAIN':30s}  REASON")
print('='*130)
for i, (n, d, r) in enumerate(sorted(candidates, key=lambda x: x[0].lower()), 1):
    print(f"  {i:>3d}  {n[:48]:50s}  {d[:28]:30s}  {r}")
