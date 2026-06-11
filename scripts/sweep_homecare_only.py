"""Post-build sweep — demote any Verified provider whose website shows
ONLY homecare/domiciliary services (no housing-type services anywhere).

Rule:
  Site mentions ANY housing/supported-living/asylum/refuge/etc. keyword anywhere
    → KEEP Verified
  Site mentions ONLY homecare / domiciliary / in-the-client's-home
    → REMOVE from Verified, add to MANUAL_DROP_LIST

This catches providers who slipped through the LLM extraction by saying
"supported living" in passing (e.g. they don't actually offer it).

USAGE:
  python scripts/sweep_homecare_only.py preview     # show what would change
  python scripts/sweep_homecare_only.py             # apply + rebuild
"""
import json, re, sys, subprocess
from pathlib import Path

FC_FILE       = Path('data/verification/firecrawl_analysed.json')
VERIFIED_FILE = Path('data/verification/VERIFIED.json')
DROPS_FILE    = Path('data/MANUAL_DROP_LIST.json')

# Housing-type service keywords — any of these = KEEP Verified.
# Includes the full set we've been working with across the pipeline.
HOUSING_TERMS = [
    'supported living', 'assisted living', 'supported accommodation',
    'supported housing', 'extra care', 'residential care', 'care home',
    'nursing home', 'asylum', 'homelessness', 'homeless',
    'refuge', 'hostel', 'sheltered housing', 'sheltered accommodation',
    'care leaver', 'leaving care', '16+', "children's home",
    'children home', 'looked after', 'mental health accommodation',
    'transitional', 'semi-independent', 'rough sleep',
    'temporary accommodation', 'crisis accommodation',
    'housing first', 'domestic abuse', 'modern slavery',
    'family accommodation', 'tenancy support', 'tenancy sustainment',
    'shared lives', 'accommodation',  # broad fallback
    'residential', 'housing support', 'housing-related',
    'floating support', 'placements', 'day service', 'day opportunit',
]

# Homecare-only signal patterns — if these appear AND no housing term, demote.
HOMECARE_TERMS = [
    'homecare', 'home care', 'home-care', 'domiciliary',
    'in your own home', 'in the comfort of your home',
    'live-in care', 'live in care', 'in-home',
    'visiting care', 'personal care at home',
]

def classify_services(services_list):
    """Returns ('housing'|'homecare-only'|'unknown', matched_terms)."""
    if not services_list: return ('unknown', [])
    text = ' '.join(services_list).lower()
    housing_hits = [t for t in HOUSING_TERMS if t in text]
    homecare_hits = [t for t in HOMECARE_TERMS if t in text]
    if housing_hits:
        return ('housing', housing_hits)
    if homecare_hits:
        return ('homecare-only', homecare_hits)
    return ('unknown', [])

def main():
    preview = (len(sys.argv) > 1 and sys.argv[1] == 'preview')

    fc       = json.load(open(FC_FILE, encoding='utf-8'))
    verified = json.load(open(VERIFIED_FILE, encoding='utf-8'))
    drops    = json.load(open(DROPS_FILE, encoding='utf-8'))
    drops_lc = {n.lower().strip() for n in drops}

    to_demote = []
    safe      = housing_kept = unknown = 0
    for name, info in verified.items():
        # Look up this name in Firecrawl cache
        r = fc.get(name)
        if not r:
            unknown += 1; continue
        if r.get('verdict') not in ('KEEP', 'UPDATE'):
            continue
        services = r.get('housing_terms') or []
        cls, terms = classify_services(services)
        if cls == 'housing':
            housing_kept += 1
        elif cls == 'homecare-only':
            to_demote.append((name, terms))
        else:
            unknown += 1

    print(f"Of {len(verified)} entries in VERIFIED.json:")
    print(f"  Housing services confirmed: {housing_kept}")
    print(f"  TO DEMOTE (homecare-only):  {len(to_demote)}")
    print(f"  Unknown / no services data: {unknown}")
    print()
    if to_demote[:15]:
        print("Sample to demote:")
        for n, t in to_demote[:15]:
            print(f"  - {n[:48]:<50s}  (only: {', '.join(t[:3])})")

    if preview:
        print("\n[PREVIEW] No changes made. Drop --preview to apply.")
        return

    # Apply: remove from VERIFIED.json + add to MANUAL_DROP_LIST
    for name, _ in to_demote:
        verified.pop(name, None)
        if name.lower().strip() not in drops_lc:
            drops.append(name)
            drops_lc.add(name.lower().strip())
    json.dump(verified, open(VERIFIED_FILE, 'w', encoding='utf-8'), indent=2)
    json.dump(drops,    open(DROPS_FILE, 'w', encoding='utf-8'), indent=2)
    print(f"\nDemoted: {len(to_demote)} from Verified → drop list")

    # Rebuild + deploy
    print("\nRebuilding + deploying...", flush=True)
    subprocess.run(['python', 'build_data.py'], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['npm', 'run', 'build'], check=False,
                   stdout=subprocess.DEVNULL, shell=True)
    subprocess.run(['vercel', 'deploy', '--prod', '--yes'], check=False, shell=True)

    # Final state
    prov = json.load(open('api/_data/providers.json', encoding='utf-8'))
    v = sum(1 for p in prov if p.get('verification',{}).get('verified'))
    print(f"\n=== Final state ===")
    print(f"  Total providers: {len(prov)}")
    print(f"  ✓ Verified:      {v}  ({v*100//len(prov)}%)")
    print(f"  📋 Listed:        {len(prov)-v}")
    print(f"  Drop list:       {len(drops)}")

if __name__ == '__main__':
    main()
