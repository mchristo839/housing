"""Dump every supplier + their domain to CSV for Clay enrichment.

Clay needs: company name + root domain. We also include the full URL,
primary category and a few extra columns to help downstream filtering.
"""
import json, csv, sys, io, re
from urllib.parse import urlparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

OUT = 'data/scraped/SUPPLIERS_FOR_CLAY.csv'

def extract_domain(url):
    """Pull the root domain from any URL."""
    if not url: return ''
    url = url.strip()
    if not re.match(r'^https?://', url):
        url = 'https://' + url
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ''
    # strip www. / m.
    host = re.sub(r'^(www\.|m\.)', '', host)
    return host

prov = json.load(open('api/_data/providers.json', encoding='utf-8'))
print(f"Loaded {len(prov)} providers")

# Build rows
rows = []
seen_domains = set()    # for dedupe stats only
no_url = 0
with_url = 0
for p in prov:
    name = p.get('name','').strip()
    website = (p.get('website') or '').strip()
    domain = extract_domain(website)

    if domain and domain not in seen_domains:
        seen_domains.add(domain)
    if not website:
        no_url += 1
    else:
        with_url += 1

    # Sector aggregation
    sectors = p.get('sector') or []
    if isinstance(sectors, str): sectors = [sectors]

    # Council list
    councils = []
    regions = set()
    for c in (p.get('contracts_list') or []):
        cn = c.get('council','')
        if cn and cn not in councils: councils.append(cn)
        if c.get('region'): regions.add(c['region'])

    rows.append({
        'company_name': name,
        'domain': domain,
        'website_url': website,
        'email': (p.get('email') or '').strip(),
        'phone': (p.get('phone') or '').strip(),
        'primary_category': p.get('primary_cat',''),
        'sectors': ' | '.join(sectors[:8]),
        'in_network': 'yes' if p.get('in_network') else '',
        'total_contracts': p.get('contracts') or 0,
        'councils_count': len(councils),
        'councils_top': ' | '.join(councils[:5]),
        'regions': ' | '.join(sorted(regions)),
        'tier_hint': p.get('scope') or '',
    })

# Sort by has-domain first (so Clay-ready rows are at the top), then by name
rows.sort(key=lambda r: (0 if r['domain'] else 1, r['company_name'].lower()))

# Write CSV (utf-8 with BOM so Excel opens it cleanly)
with open(OUT, 'w', newline='', encoding='utf-8-sig') as f:
    fieldnames = ['company_name','domain','website_url','email','phone',
                  'primary_category','sectors','in_network','total_contracts',
                  'councils_count','councils_top','regions','tier_hint']
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for r in rows:
        w.writerow(r)

print(f"\nWrote {OUT}")
print(f"  Total suppliers      : {len(rows)}")
print(f"  With domain          : {with_url}")
print(f"  Without domain       : {no_url}")
print(f"  Unique root domains  : {len(seen_domains)}")
print(f"  Size                 : {len(open(OUT,'rb').read())//1024}KB")

# Show top 5 rows
print(f"\nFirst 5 rows:")
for r in rows[:5]:
    print(f"  {r['company_name'][:35]:35s}  {r['domain']:35s}  {r['primary_category']}")
