"""Final parse + write to review DB. All bidstats London notices."""
import re, sys, io, glob, html, json, os, openpyxl, datetime
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def parse(h, source_url, nid):
    text = re.sub(r'<script.*?</script>', '', h, flags=re.S)
    text = re.sub(r'<style.*?</style>', '', text, flags=re.S)
    text = html.unescape(re.sub(r'<[^>]+>', '\n', text))
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n+', '\n', text)
    tm = re.search(r'\n\s*([A-Z][^\n]{15,200}?)\s*\[(Tender|Award|Notice|Modification|PIN|Pipeline|Addendum)\]', text)
    title = tm.group(1).strip() if tm else ""
    status = tm.group(2) if tm else "Notice"
    boroughs = []
    BR = re.compile(r"(London Borough of [A-Z][a-z]+(?:[ -][A-Z][a-z]+)*|Royal Borough of [A-Za-z &]+|(?:Hackney|Camden|Islington|Lambeth|Southwark|Lewisham|Greenwich|Tower Hamlets|Newham|Waltham Forest|Redbridge|Havering|Bromley|Bexley|Hounslow|Ealing|Brent|Harrow|Hillingdon|Barnet|Enfield|Haringey|Hammersmith and Fulham|Kensington and Chelsea|Westminster|Wandsworth|Sutton|Kingston upon Thames|Richmond upon Thames|Croydon|Merton|Barking and Dagenham|City of London))")
    for m in BR.finditer(text):
        if m.group(1) not in boroughs:
            boroughs.append(m.group(1).strip())
    if re.search(r"\bwestminster city council\b|\bwcc\b", text, re.I) and 'Westminster' not in boroughs:
        boroughs.append('Westminster')
    value = ""
    for m in re.finditer(r"Value\s*\n?\s*[££?](?P<v>[0-9.,KMmk\-\s]+)", text):
        value = m.group('v').strip()[:30]
        break
    published = ""
    for m in re.finditer(r"Published\s*\n\s*([0-9]{1,2}\s+\w+\s+\d{4})", text):
        published = m.group(1).strip()
        break
    suppliers = []
    ai = text.lower().find('award detail')
    if ai > 0:
        section = text[ai:ai+15000]
        for m in re.finditer(r"\n\s*([A-Z][A-Za-z0-9 &'\.\,/-]{4,80}?)\s*\n\s*\(([A-Za-z ,]+?)\)", section):
            name = m.group(1).strip()
            loc = m.group(2).strip()
            if name.lower() in {'award detail','awards','contractors','supplier analysis','quality','price','award criteria','reference','status','history','categories','domains','indicators','social value'}:
                continue
            if name not in {s['name'] for s in suppliers}:
                suppliers.append({"name": name, "location": loc})
    return {"source_url": source_url, "notice_id": nid, "status": status,
            "title": title, "boroughs": boroughs, "value": value,
            "published": published, "suppliers": suppliers}

results = []
for path in sorted(glob.glob('.scratch/bidstats/*.html')):
    nid = os.path.basename(path).replace('.html', '')
    url = f"https://bidstats.uk/notice/{nid}"
    with open(path, encoding='utf-8', errors='replace') as f:
        results.append(parse(f.read(), url, nid))

NOT_H = re.compile(r"home care\b|home support service|home (domiciliary|based) care|aids and adaptations|booking system|community equipment|talking therapies|business support|cleaning services|catering|street lighting|repairs only|grass cutting|reablement only|home care service|access to work|sheltered housing cleaning|lift modernisation|viability assessments|respiratory services|small sites|maintenance only", re.I)
H_OK = re.compile(r"supported (living|accommodation|housing)|emergency accommodation|temporary accommodation|hostel|refuge|housing related support|extra care|step down|step-down accommodation|housing care|housing support|sheltered (housing|accommodation)|supported housing|young people.{0,40}(housing|accommodation|pathway|home)|care leavers|homeless|asylum|nightly paid|social housing|supported vulnerable adults|residential.{0,15}framework|crisis prevention.{0,30}accommodation|housing pathway|practice flats|pathway partnership|adult pathway|safe accommodation|learning disabilit.{0,40}(accommodation|housing|supported|residential|placement)|mental health.{0,40}(accommodation|housing|supported|step|crisis)|semi[- ]?independent|supported lodgings|floating support|approved provider list|positive behaviour support|complex needs.{0,30}(accommodation|housing)|domestic abuse|rough sleeper|housing first|respite rooms", re.I)

XLSX = 'data/scraped/curated_scraped.xlsx'
wb = openpyxl.load_workbook(XLSX)
ws = wb['Company × Council × Sector']

existing_keys = set()
for r in ws.iter_rows(min_row=2, values_only=True):
    if r[0] and r[2]:
        existing_keys.add((str(r[0]).strip().lower(), str(r[2]).strip().lower(), str(r[19] or '').strip().lower()))

LDN = ['london','hackney','camden','islington','lambeth','southwark','lewisham','greenwich','tower hamlets','newham','waltham','redbridge','havering','bromley','bexley','hounslow','ealing','brent','harrow','hillingdon','barnet','enfield','haringey','hammersmith','kensington','westminster','wandsworth','sutton','kingston','richmond','croydon','merton','barking','city of london','rbkc','wcc']

now = datetime.datetime.now().isoformat()
added = 0
new_contracts = []

for r in results:
    title = r['title']
    if not r['suppliers']:
        continue
    if NOT_H.search(title):
        continue
    if not H_OK.search(title):
        continue
    lb = None
    for b in r['boroughs']:
        if any(k in b.lower() for k in LDN):
            lb = b
            break
    if not lb:
        continue
    n_new = 0
    for sup in r['suppliers']:
        key = (sup['name'].strip().lower(), lb.strip().lower(), r['notice_id'].lower())
        if key in existing_keys:
            continue
        existing_keys.add(key)
        loc_suffix = f" · supplier @ {sup['location']}" if sup['location'] else ""
        row = [
            sup['name'], "Housing", lb, 1, "", "", "", "", "", "",
            "Supported accommodation | Supported living",
            r.get('published', '')[:10],
            f"{title} (Bidstats {r['notice_id']}; {r.get('status', '')}{loc_suffix})",
            "London", "Local Council", "Local", ""
        ] + ["bidstats", r['source_url'], r['notice_id'], now, "",
             r.get('value', '').replace(',', '').replace(' ', ''), ""]
        ws.append(row)
        added += 1
        n_new += 1
    if n_new:
        new_contracts.append((r['notice_id'], title[:65], lb, n_new, len(r['suppliers']), r.get('value', '')))

wb.save(XLSX)

rows = list(ws.iter_rows(min_row=2, values_only=True))
print(f"Review DB total: {len(rows)} rows (+{added} from this run)")
print(f"Distinct suppliers : {len(set(r[0] for r in rows if r[0]))}")
print(f"Distinct councils  : {len(set(r[2] for r in rows if r[2]))}")
print(f"Distinct contracts : {len(set(r[19] for r in rows if r[19]))}\n")

print("New contracts captured:")
for nid, t, b, new, all_n, v in new_contracts:
    print(f"  +{new:3d}/{all_n:3d}  £{v[:8]:8s}  {b[:30]:30s}  {t}")

print("\nROWS PER LONDON COUNCIL:")
for c, n in sorted(Counter(r[2] for r in rows if r[2]).items(), key=lambda x: -x[1])[:30]:
    print(f"  {n:4d}  {c}")
