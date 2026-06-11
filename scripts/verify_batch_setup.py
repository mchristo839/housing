"""Generate the prioritised verification batch list.

Risk scoring (higher = more uncertain, verify first):
  +3 if name contains generic 'care'/'health'/'support' without 'supported'/'housing'/'accommodation'
  +2 if single contract only
  +1 if Local scope only
  -1 if National scope
  -2 if name contains strong housing terms (housing/supported living/refuge/etc.)
  -2 if has 5+ contracts (multi-procurement validation)
"""
import json, re, csv
from pathlib import Path

prov = json.load(open('api/_data/providers.json', encoding='utf-8'))

STRONG = re.compile(
    r'\b(housing\s+(?:association|trust|group|society|partnership)|'
    r'supported\s+(?:living|housing|accommodation)|extra\s*care|mencap|'
    r'sense\b|leonard\s+cheshire|abbeyfield|almshouse|salvation\s+army|'
    r'st\s+mungo|refuge|domestic\s+abuse|youth\s+(?:housing|support)|'
    r'leaving\s+care|autism\s+trust|homeless|rough\s+sleep|asylum|'
    r'alms\s+house|sheltered\s+housing|hostel|housing\s+first)\b', re.I)
WEAK = re.compile(r'\b(care\s+(?:ltd|limited|services|group|solutions|company)|'
                  r'healthcare|health\s+care|domiciliary)\b', re.I)

def risk_score(p):
    name = p['name']
    n = len(p.get('contracts_list') or [])
    sc = p.get('scope','')
    score = 0
    if WEAK.search(name) and not STRONG.search(name): score += 3
    if n <= 1: score += 2
    if sc == 'Local': score += 1
    elif sc == 'National': score -= 1
    if STRONG.search(name): score -= 2
    if n >= 5: score -= 2
    return score

scored = []
for p in prov:
    if not p.get('website'): continue
    if p.get('scope') == 'National' and len(p.get('contracts_list') or []) >= 20: continue
    if STRONG.search(p['name']): continue
    s = risk_score(p)
    scored.append({'name': p['name'], 'website': p.get('website',''),
                   'score': s, 'contracts': len(p.get('contracts_list') or []),
                   'scope': p.get('scope','')})

scored.sort(key=lambda x: -x['score'])

# Save full prioritised list
out_full = Path('data/scraped/VERIFICATION_QUEUE.csv')
with open(out_full, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['priority','name','scope','contracts','website','status','verdict','reason'])
    for i, p in enumerate(scored, 1):
        w.writerow([i, p['name'], p['scope'], p['contracts'], p['website'], 'pending', '', ''])
print(f"Wrote prioritised queue: {out_full}  ({len(scored)} providers)")

# Print batch 1 = top 50
print(f"\n=== BATCH 1 (top 50 highest-risk) ===\n")
for i, p in enumerate(scored[:50], 1):
    print(f"  {i:>2d}. (risk={p['score']:+d}, {p['contracts']} contracts) {p['name'][:36]:<38s}  {p['website'][:55]}")
