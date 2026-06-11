"""Evidence-backed bulk sweep: for each named national operator, search Bidstats
for AWARD notices where they appear, parse the awarding authority and award value
from each notice's Award Detail section, write candidate rows to a review pack.

Rule: a contract is only added when we have a SPECIFIC bidstats notice that names
the operator as a winner. No 'they say they operate there' guesses.

Output: data/scraped/OPERATOR_SWEEP_EVIDENCE.xlsx — one row per (operator × council)
that's actually backed by a Bidstats notice URL we can cite.
"""
import re, time, json, urllib.parse, urllib.request, sys, io, html
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Top national TA / supported-housing operators we want to evidence
OPERATORS = [
    "Bedspace",
    "Look Ahead Care",
    "Riverside Group",  # Riverside is huge - already partial
    "Stay Care",        # spelled often as 'Stay & Care'
    "Adullam Homes",
    "Salvation Army Homes", "SAH",
    "Hestia Housing",
    "St Mungo",
    "Thames Reach",
    "Centrepoint",
    "Depaul UK",
    "Single Homeless Project",
    "Stonewater",
    "Sanctuary Supported",
    "P3 Charity",
    "Turning Point",
    "Humankind",
    "Inclusion Housing",
    "YMCA",
    "Action for Children",
    "Nacro",
    "Catch22",
    "Bay 6",
    "DePaul",
    "Choices Housing",
    "Together Trust",
    "Sense",
    "Mears Group",
    "Serco Citizen",  # Serco asylum contractor
    "Clearsprings Ready Homes",
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

def fetch(url, retries=2, delay=1.5):
    for i in range(retries+1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode('utf-8', errors='ignore')
        except Exception as e:
            if i == retries: raise
            time.sleep(delay * (i+1))

def strip(t):
    return html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', t)))

def search_bidstats(operator, max_results=15):
    """Search bidstats for award notices naming the operator."""
    q = urllib.parse.quote(f'"{operator}"')
    url = f"https://bidstats.uk/search?q={q}&type=award"
    try:
        html_doc = fetch(url)
    except Exception as e:
        print(f"  ! search failed: {e}")
        return []
    # Extract tender URLs from search results page
    tenders = re.findall(r'/tenders/\d{4}/W\d+/\d+', html_doc)
    seen = []
    for t in tenders:
        if t not in seen: seen.append(t)
        if len(seen) >= max_results: break
    return seen

def parse_notice(path):
    """Extract: title, buyer, supplier list, value, dates."""
    url = f"https://bidstats.uk{path}"
    try:
        html_doc = fetch(url)
    except Exception as e:
        return None
    title_m = re.search(r'<title[^>]*>([^<]+)</title>', html_doc, re.I)
    title = (title_m.group(1).strip() if title_m else '').replace(' [Award]', '').replace(' [Notice]', '')
    text = strip(html_doc)
    buyer = ''
    bm = re.search(r'A Contract Award Notice by ([A-Z][A-Z\s&\.\-]+?)(?:\s+Source|\s+Type|$)', text)
    if bm: buyer = bm.group(1).strip().title()
    if not buyer:
        bm = re.search(r'1 buyer\s+([A-Z][\w\s&\.\-]+?)\s+(?:Liverpool|London|Manchester|Birmingham|Leeds|Description)', text)
        if bm: buyer = bm.group(1).strip()
    # Award detail block — list of suppliers
    suppliers = []
    ad = re.search(r'Award Detail (.+?)(?:CPV Codes|Indicators|Other Information)', text, re.S)
    if ad:
        block = ad.group(1)
        for sm in re.finditer(r'\d+\s+([A-Z][\w\s&\.\-\']+?)(?:\s*\([^)]+\))?\s+(?:Value:|Reference:|Num offers)', block):
            s = sm.group(1).strip()
            if 2 < len(s) < 80 and s not in suppliers: suppliers.append(s)
    # Value
    vm = re.search(r'Value\s+(£[\dKM\.\-]+)', text)
    value = vm.group(1) if vm else ''
    # Delivery dates
    dm = re.search(r'Delivery\s+(\d{2}\s\w{3}\s\d{4})\s+to\s+(\d{2}\s\w{3}\s\d{4})', text)
    duration = f"{dm.group(1)} → {dm.group(2)}" if dm else ''
    return {'url': url, 'title': title, 'buyer': buyer,
            'suppliers': suppliers, 'value': value, 'duration': duration}

def main():
    rows = []
    out = Path('data/scraped/OPERATOR_SWEEP_EVIDENCE.csv')
    out.parent.mkdir(parents=True, exist_ok=True)
    for op in OPERATORS:
        print(f"\n=== {op} ===")
        tenders = search_bidstats(op, max_results=10)
        print(f"  found {len(tenders)} candidate tender URLs")
        for tpath in tenders:
            notice = parse_notice(tpath)
            if not notice: continue
            # operator must appear in supplier list (substring match either way, case-insensitive)
            op_l = op.lower()
            matched = [s for s in notice['suppliers']
                       if op_l in s.lower() or s.lower() in op_l]
            if not matched: continue
            for sup in matched:
                rows.append({
                    'operator_query': op,
                    'matched_supplier_name': sup,
                    'commissioning_council': notice['buyer'],
                    'contract_title': notice['title'],
                    'value': notice['value'],
                    'duration': notice['duration'],
                    'bidstats_url': notice['url'],
                })
                print(f"    ✓ {sup} × {notice['buyer']}  →  {notice['title'][:60]}")
            time.sleep(0.4)
        time.sleep(0.8)

    # Write CSV
    import csv
    if rows:
        with open(out, 'w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print(f"\nWrote {len(rows)} evidence-backed (operator × council) rows → {out}")
    else:
        print("\nNo evidence-backed rows found (scrape may have been blocked).")

if __name__ == '__main__':
    main()
