"""Firecrawl-verify a list of supplier names directly (no providers.json needed).

Used for the case where suppliers from a CSV ingest never reached providers.json
because they had no contacts in the Companies sheet (and got filtered out by
the 'unreachable' check).

For each name:
  1. Firecrawl /search to find the most likely UK URL
  2. Firecrawl /extract on that URL with the housing-services schema
  3. If KEEP → write website/email/phone/address to Companies sheet (so the
     next build will pass the unreachable filter and include them as Verified).
  4. Also writes verdict to firecrawl_analysed.json so apply_firecrawl picks them up.

USAGE:
  python scripts/firecrawl_lookup_names.py path/to/names.json [--workers N]

The names.json should be a JSON array of strings.
"""
import os, sys, json, time, threading, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests, openpyxl

API_KEY = os.environ.get('FIRECRAWL_API_KEY', '')
BASE    = 'https://api.firecrawl.dev/v1'
ANALYSED = Path('data/verification/firecrawl_analysed.json')
DISCOVERED = Path('data/verification/firecrawl_discovered_urls.json')
MANUAL_XL = Path('data/manual_contracts.xlsx')

sys.path.insert(0, str(Path('scripts').absolute()))
from firecrawl_verify import EXTRACT_SCHEMA, classify_extracted, poll_extract
from firecrawl_search_unverified import search_for_provider, extract_at_url, fc_post

def norm(name):
    n = (name or '').lower().strip()
    n = re.sub(r'\b(ltd|limited|llp|plc|company|co|cic|t\/a|trading as)\b', '', n)
    n = re.sub(r'[^a-z0-9 ]', ' ', n)
    return ' '.join(n.split())

def main():
    if not API_KEY:
        print("ERROR: FIRECRAWL_API_KEY not set"); sys.exit(1)
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(1)
    name_file = args[0]
    workers = 6
    for i, a in enumerate(args):
        if a == '--workers' and i+1 < len(args): workers = int(args[i+1])

    names = json.load(open(name_file, encoding='utf-8'))
    print(f"Names to look up: {len(names)}", flush=True)

    analysed = json.load(open(ANALYSED, encoding='utf-8')) if ANALYSED.exists() else {}
    discovered = json.load(open(DISCOVERED, encoding='utf-8')) if DISCOVERED.exists() else {}

    lock = threading.Lock()
    counter = [0]

    def process(name):
        try:
            # 1. search
            real = discovered.get(name) or search_for_provider(name)
            with lock:
                discovered[name] = real
            if not real or not real.get('url'):
                with lock:
                    analysed[name] = {'url':'','verdict':'NO_URL','mode':'extract',
                                      'checked_at': time.strftime('%Y-%m-%d')}
                    counter[0] += 1
                    json.dump(analysed, open(ANALYSED,'w', encoding='utf-8'), indent=2)
                    print(f"  [{counter[0]:>3d}/{len(names)}] NO_URL  {name[:48]}", flush=True)
                return

            # 2. extract
            raw = extract_at_url(real['url'], name)
            if raw.get('data'):
                extracted = raw['data'] if isinstance(raw['data'], dict) else raw['data'][0]
            elif raw.get('id'):
                extracted = poll_extract(raw['id'])
            else:
                extracted = {}
            res = classify_extracted(name, extracted)
            res['url'] = real['url']
            res['notes'] = f"search-found: {real.get('title','')[:60]}"
            with lock:
                analysed[name] = res
                counter[0] += 1
                json.dump(analysed, open(ANALYSED,'w', encoding='utf-8'), indent=2)
                print(f"  [{counter[0]:>3d}/{len(names)}] {res['verdict']:<14s}"
                      f"  {name[:42]}  -> {real['url'][:35]}", flush=True)
        except Exception as e:
            with lock:
                analysed[name] = {'url':'','verdict':'ERROR','error':str(e)[:120],
                                  'mode':'extract','checked_at': time.strftime('%Y-%m-%d')}
                counter[0] += 1
                json.dump(analysed, open(ANALYSED,'w', encoding='utf-8'), indent=2)
                print(f"  [{counter[0]:>3d}/{len(names)}] ERROR  {name}: {str(e)[:60]}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(process, n) for n in names]
        for f in as_completed(futures):
            f.result()

    json.dump(discovered, open(DISCOVERED,'w', encoding='utf-8'), indent=2)
    print(f"\nDone. Processed: {counter[0]}", flush=True)

    # === Write KEEPs to Companies sheet so build will keep them ===
    print("\nWriting verified contacts to Companies sheet...", flush=True)
    wb = openpyxl.load_workbook(MANUAL_XL)
    comp = wb['Companies']
    idx_by_norm = {}
    for r in range(2, comp.max_row+1):
        nm = (comp.cell(row=r, column=1).value or '').strip()
        if nm: idx_by_norm[norm(nm)] = r

    upd = added = 0
    for name in names:
        r = analysed.get(name, {})
        if r.get('verdict') != 'KEEP': continue
        nl = norm(name)
        row_idx = idx_by_norm.get(nl)
        if row_idx is None:
            row_idx = comp.max_row + 1
            comp.cell(row=row_idx, column=1).value = name
            comp.cell(row=row_idx, column=2).value = 0
            comp.cell(row=row_idx, column=5).value = 1
            comp.cell(row=row_idx, column=7).value = 'No'
            idx_by_norm[nl] = row_idx
            added += 1
        else:
            upd += 1
        # Cols: 12=address 13=website 14=phone 15=email 16=contact_page
        if r.get('address'):
            comp.cell(row=row_idx, column=12).value = r['address']
        if r.get('url'):
            comp.cell(row=row_idx, column=13).value = r['url']
        if r.get('phones'):
            comp.cell(row=row_idx, column=14).value = r['phones'][0]
        if r.get('emails'):
            comp.cell(row=row_idx, column=15).value = r['emails'][0]
        if r.get('contact_page') and not r.get('emails'):
            comp.cell(row=row_idx, column=16).value = r['contact_page']
    wb.save(MANUAL_XL)
    print(f"Companies sheet: {upd} updated, {added} added")

if __name__ == '__main__':
    main()
