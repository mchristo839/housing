"""Render what an unlocked subscriber sees for a postcode, as a standalone
HTML file. Mirrors the Results.jsx component output, using real live data."""
import json, re, sys, io, urllib.request, html as htmllib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

POSTCODE = sys.argv[1] if len(sys.argv) > 1 else 'TW77HD'
OUT = f'data/scraped/UNLOCKED_PREVIEW_{POSTCODE}.html'

# 1. Resolve postcode
with urllib.request.urlopen(f'https://api.postcodes.io/postcodes/{POSTCODE}', timeout=10) as r:
    res = json.loads(r.read())['result']

# 2. Mirror normCouncil/key from match.js + engine_maps.js
def normCouncil(name):
    n = (name or '').lower().strip().replace('&', ' and ')
    n = re.sub(r',\s*city of$', ' city', n)
    n = re.sub(r'^city of london corporation$', 'city of london', n)
    n = re.sub(r'^(?:the\s+)?(?:london borough of|royal borough of)\s+', '', n)
    n = re.sub(r'\b(council|metropolitan borough|borough|county|district|unitary authority|mbc|lbc|the )\b', ' ', n)
    if n != 'city of london' and not n.startswith('city of london '):
        n = re.sub(r'\bcity\b', ' ', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    return re.sub(r'\s+', ' ', n).strip()

DROP = {'council','borough','county','city','district','the','of','metropolitan',
        'unitary','authority','corporation','mbc','mdc','cc'}
def normCouncilKey(s):
    s = (s or '').lower().replace('&', ' and ')
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    return ' '.join(t for t in s.split() if t and t not in DROP)

REGION_NORM = {
    'london': 'London', 'east midlands': 'East Midlands',
    'east of england': 'East of England', 'north east': 'North East',
    'north west': 'North West', 'south east': 'South East',
    'south west': 'South West', 'west midlands': 'West Midlands',
    'yorkshire and the humber': 'Yorkshire & the Humber',
}

# 3. Load live data
db = json.load(open('api/_data/db.json', encoding='utf-8'))
prov = json.load(open('api/_data/providers.json', encoding='utf-8'))
cmap = json.load(open('api/_data/councilmap.json', encoding='utf-8'))
by_id = {p['id']: p for p in prov}

# 4. Resolve tiers (same as match.js)
adm = res.get('admin_district')
norm_d = normCouncil(adm)
region = REGION_NORM.get((res.get('region') or '').lower())
ck = normCouncilKey(adm)

local_ids, seen = [], set()
for k in cmap.get(norm_d, []):
    for pid in db['c'].get(k, []):
        if pid not in seen: seen.add(pid); local_ids.append(pid)
regional_ids = [pid for pid in db['r'].get(region or '', [])
                if pid not in seen and not seen.add(pid)]
national_ids = [pid for pid in db['n'] if pid not in seen and not seen.add(pid)]

# 5. Trim contracts list per provider
def relevant(p):
    out = []
    for c in (p.get('contracts_list') or []):
        gk = normCouncilKey(c.get('council',''))
        if (ck and (gk == ck or ck in gk or gk in ck)) or \
           (c.get('scope') == 'Regional' and c.get('region') == region) or \
           c.get('scope') == 'National':
            out.append(c)
    return out

def card(p, tier):
    contracts = relevant(p)
    name = htmllib.escape(p['name'])
    star = '⭐ ' if p.get('in_network') else ''
    web = (p.get('website') or '').strip()
    email = (p.get('email') or '').strip()
    phone = (p.get('phone') or '').strip()
    primary = htmllib.escape(p.get('primary_cat',''))
    sectors = (p.get('sector') or [])
    sector_tags = ''.join(f'<span class="tag">{htmllib.escape(s)}</span>' for s in sectors[:6])

    contact_bits = []
    if web:
        u = web if web.startswith('http') else 'https://' + web
        contact_bits.append(f'<a href="{htmllib.escape(u)}" target="_blank">🌐 Website</a>')
    if phone:
        contact_bits.append(f'<a href="tel:{htmllib.escape(phone)}">📞 {htmllib.escape(phone)}</a>')
    if email:
        contact_bits.append(f'<a href="mailto:{htmllib.escape(email)}">✉️ {htmllib.escape(email)}</a>')
    contact_html = ' · '.join(contact_bits) or '<i>Contact via commissioner</i>'

    contract_rows = []
    for c in contracts[:5]:
        commiss = htmllib.escape(c.get('council',''))
        title = c.get('titles') or []
        if isinstance(title, list): title = title[0] if title else '(no title)'
        title = htmllib.escape(str(title))[:140]
        scope = htmllib.escape(c.get('scope',''))
        contract_rows.append(
            f'<div class="contract">'
            f'<div class="contract-c">{commiss} <span class="scope">{scope}</span></div>'
            f'<div class="contract-t">{title}</div>'
            f'</div>'
        )
    contracts_html = '\n'.join(contract_rows) or '<div class="contract"><i>Contract details below subscription tier</i></div>'

    return (
        f'<div class="provider {tier}">'
        f'<div class="provider-h"><h3>{star}{name}</h3>'
        f'<span class="tier-pill {tier}">{tier.title()}</span></div>'
        f'<div class="primary">{primary}</div>'
        f'<div class="tags">{sector_tags}</div>'
        f'<div class="contact">{contact_html}</div>'
        f'<div class="contracts-h">Contracts ({len(contracts)})</div>'
        f'<div class="contracts">{contracts_html}</div>'
        f'</div>'
    )

# 6. Render
parts = ['<!doctype html><html><head><meta charset="utf-8">']
parts.append(f'<title>Unlocked preview — {POSTCODE}</title>')
parts.append('''<style>
body{font:14px -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f6f7f9;color:#1a1a1a}
.bar{background:#fff;border-bottom:1px solid #e5e7eb;padding:14px 0;position:sticky;top:0;z-index:5}
.bar .wrap{display:flex;justify-content:space-between;align-items:center;gap:16px}
.wrap{max-width:1100px;margin:0 auto;padding:0 24px}
h1{font-size:22px;margin:0 0 4px;letter-spacing:-0.01em}
.meta{color:#666;font-size:13px;margin:0}
.meta b{color:#1F4E79}
.btn{padding:9px 18px;border:1px solid #1F4E79;background:#1F4E79;color:#fff;border-radius:6px;font-weight:600;font-size:13px;cursor:pointer;text-decoration:none}
.btn.sec{background:#fff;color:#1F4E79}
.unlocked{background:#d4edda;color:#1e6033;padding:10px 16px;border-radius:6px;display:inline-block;font-size:13px;font-weight:600;margin:18px 0}
.tier-section{margin:24px 0}
.tier-section h2{font-size:16px;color:#1F4E79;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid #1F4E79}
.tier-section .desc{color:#666;font-size:12px;margin-bottom:14px;font-style:italic}
.providers{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}
.provider{background:#fff;border-radius:8px;padding:16px;border:1px solid #e5e7eb;box-shadow:0 1px 2px rgba(0,0,0,.03)}
.provider.local{border-left:4px solid #28a745}
.provider.county{border-left:4px solid #ffc107}
.provider.regional{border-left:4px solid #17a2b8}
.provider.national{border-left:4px solid #6c757d}
.provider-h{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px}
.provider h3{margin:0;font-size:15px;font-weight:700;color:#222}
.tier-pill{font-size:9px;font-weight:700;letter-spacing:.05em;padding:2px 7px;border-radius:11px;text-transform:uppercase}
.tier-pill.local{background:#d4edda;color:#1e6033}
.tier-pill.county{background:#fff3cd;color:#856404}
.tier-pill.regional{background:#d1ecf1;color:#0c5460}
.tier-pill.national{background:#e2e3e5;color:#383d41}
.primary{font-size:11px;color:#666;letter-spacing:.05em;text-transform:uppercase;margin-bottom:8px}
.tags{margin-bottom:10px}
.tag{display:inline-block;background:#eef2f7;color:#3c4858;padding:2px 7px;border-radius:11px;font-size:10px;margin-right:3px;margin-bottom:3px}
.contact{font-size:12px;margin-bottom:10px;padding-bottom:10px;border-bottom:1px dashed #e5e7eb}
.contact a{color:#0563C1;text-decoration:none;margin-right:8px;display:inline-block}
.contracts-h{font-size:11px;text-transform:uppercase;font-weight:700;color:#666;letter-spacing:.05em;margin-bottom:6px}
.contracts{font-size:12px}
.contract{background:#fafbfc;border-left:3px solid #1F4E79;padding:6px 10px;margin-bottom:4px;border-radius:0 4px 4px 0}
.contract-c{font-weight:600;color:#1F4E79;font-size:12px}
.contract-c .scope{font-size:9px;background:#1F4E79;color:#fff;padding:1px 6px;border-radius:8px;margin-left:5px;font-weight:700}
.contract-t{color:#555;font-size:11px;margin-top:2px;line-height:1.35}
.note{font-size:11px;color:#888;margin-top:14px;font-style:italic}
</style></head><body>''')

parts.append('<div class="bar"><div class="wrap">')
parts.append(f'<div><h1>Providers covering <span style="color:#1F4E79">{htmllib.escape(adm)}</span></h1>')
total = len(local_ids) + len(regional_ids) + len(national_ids)
parts.append(f'<p class="meta">{POSTCODE} · {region} · {total} providers'
             f' · <b>{len(local_ids)}</b> hold a contract with this council</p></div>')
parts.append('<div><a class="btn" href="#">↓ Download PDF report</a> <a class="btn sec" href="#">New search</a></div>')
parts.append('</div></div>')

parts.append('<div class="wrap">')
parts.append(f'<div class="unlocked">✓ UNLOCKED · Full subscriber view of {POSTCODE}</div>')

# Local tier
if local_ids:
    parts.append('<div class="tier-section">')
    parts.append(f'<h2>🏠 Local — providers commissioned by {htmllib.escape(adm)} ({len(local_ids)})</h2>')
    parts.append('<p class="desc">These hold live contracts with the council. Most landlord-relevant.</p>')
    parts.append('<div class="providers">')
    for pid in local_ids: parts.append(card(by_id[pid], 'local'))
    parts.append('</div></div>')

# Regional tier
if regional_ids:
    parts.append('<div class="tier-section">')
    parts.append(f'<h2>🌍 Regional — pan-{region} operators ({len(regional_ids)})</h2>')
    parts.append('<p class="desc">Operating across the whole region — pan-London frameworks, Home Office asylum contractors, etc.</p>')
    parts.append('<div class="providers">')
    for pid in regional_ids: parts.append(card(by_id[pid], 'regional'))
    parts.append('</div></div>')

# National tier
if national_ids:
    parts.append('<div class="tier-section">')
    parts.append(f'<h2>🇬🇧 National — UK-wide operators ({len(national_ids)})</h2>')
    parts.append('<p class="desc">Operating UK-wide — large national charities and Home Office prime contractors.</p>')
    parts.append('<div class="providers">')
    for pid in national_ids: parts.append(card(by_id[pid], 'national'))
    parts.append('</div></div>')

parts.append('<p class="note">This is exactly what a paid subscriber sees in their browser. ' \
             'The live results page also has filters (sector, SME/Large, exclude national), ' \
             'a "Generate outreach email" tool per provider, and a one-click PDF report for ' \
             'sharing with clients.</p>')
parts.append('</div></body></html>')

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(''.join(parts))

print(f"Wrote {OUT}")
print(f"  {total} providers shown ({len(local_ids)} Local, "
      f"{len(regional_ids)} Regional, {len(national_ids)} National)")
print(f"  Size: {len(open(OUT,'rb').read())//1024}KB")
