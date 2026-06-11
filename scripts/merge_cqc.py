"""
Merge CQC supported-housing providers into the existing provider universe.

Strategy:
  - CQC is the BASE — every CQC-registered supported living/housing provider
    is in the merged output, regardless of whether we have contract data for them.
  - Existing contract data ENRICHES the matched providers (council contracts,
    contracts_list, in-network status, etc.).
  - Match by normalised company name.

Output (kept separate from live data until promoted):
  data/v2/providers.json    — CQC base + contract enrichment
  data/v2/db.json           — index built from BOTH location-LAs (CQC) and
                              contract councils (existing)
  data/v2/merge_report.md   — what matched, what's net-new, before/after
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CQC = os.path.join(ROOT, 'data', 'cqc', 'cqc_supported_providers.json')
EXISTING_PROVIDERS = os.path.join(ROOT, 'api', '_data', 'providers.json')
OUT_DIR = os.path.join(ROOT, 'data', 'v2')

DROP_TOKENS = {"limited","ltd","plc","cic","llp","group","the","uk","t","a",
               "trust","services","service","association","ha","society"}

def norm_name(s):
    s = re.sub(r"[^a-z0-9 ]", " ", str(s or "").lower().replace("&", " and "))
    return " ".join(t for t in s.split() if t and t not in DROP_TOKENS)

COUNCIL_DROP = {"council","borough","metropolitan","district","unitary","authority",
                "the","of","city","mbc","lbc","mdc","cc"}
def norm_council(s):
    s = re.sub(r"[^a-z0-9 ]", " ", str(s or "").lower().replace("&", " and "))
    return " ".join(t for t in s.split() if t and t not in COUNCIL_DROP)

# CQC "Region" values don't perfectly match our ONS region naming.
CQC_REGION_MAP = {
    "North East": "North East",
    "North West": "North West",
    "Yorkshire & Humberside": "Yorkshire & The Humber",
    "East Midlands": "East Midlands",
    "West Midlands": "West Midlands",
    "East": "East of England",
    "London": "London",
    "South East": "South East",
    "South West": "South West",
}

def slugify(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", str(s or "").lower())).strip("-")

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    cqc = json.load(open(CQC, encoding='utf-8'))['providers']
    existing = json.load(open(EXISTING_PROVIDERS, encoding='utf-8'))

    print(f"CQC providers loaded     : {len(cqc)}")
    print(f"Existing providers loaded: {len(existing)}")

    # index existing by norm-name
    by_norm = {}
    for p in existing:
        k = norm_name(p['name'])
        if k: by_norm.setdefault(k, []).append(p)

    # Build merged providers — CQC is the base
    merged = []
    seen_slugs = {}
    matched_to_existing = 0
    cqc_only = 0
    contract_count = 0
    for cqc_p in cqc:
        cqc_name = cqc_p['name']
        nk = norm_name(cqc_name)
        existing_match = by_norm.get(nk, [None])[0]

        # name: prefer the longer/more complete one
        if existing_match and len(existing_match['name']) > len(cqc_name):
            display_name = existing_match['name']
        else:
            display_name = cqc_name

        slug = slugify(display_name)
        # de-dup slugs
        base_slug = slug; n = 2
        while slug in seen_slugs:
            slug = f"{base_slug}-{n}"; n += 1
        seen_slugs[slug] = True

        # Aggregate location → councils + regions
        cqc_councils = sorted(set(cqc_p.get('all_local_authorities') or []))
        cqc_regions_raw = cqc_p.get('all_regions') or []
        cqc_regions = sorted(set(filter(None, (CQC_REGION_MAP.get(r) for r in cqc_regions_raw))))

        # Pick the first location for primary address / contact
        first_loc = (cqc_p['locations'] or [{}])[0]
        phone = (cqc_p.get('all_phones') or [''])[0] if cqc_p.get('all_phones') else ''
        website = (cqc_p.get('all_websites') or [''])[0] if cqc_p.get('all_websites') else ''

        # Carry forward existing data where present (email, in_network, contracts, etc.)
        if existing_match:
            matched_to_existing += 1
            email = existing_match.get('email') or ''
            contact_page = existing_match.get('contact_page') or ''
            in_network = existing_match.get('in_network', False)
            description = existing_match.get('description') or ''
            charity = existing_match.get('charity') or None
            employees = existing_match.get('employees')
            employee_confidence = existing_match.get('employee_confidence', '')
            existing_contracts = existing_match.get('contracts_list') or []
            existing_councils = set(existing_match.get('councils') or [])
            existing_regions = set(existing_match.get('regions') or [])
            existing_scope = existing_match.get('scope', 'Local')
            sectors = existing_match.get('sector') or []
            primary_cat = existing_match.get('primary_cat') or ''
            client_groups = existing_match.get('client_groups') or []
            is_ha = existing_match.get('is_housing_association', False)
            is_sme = existing_match.get('is_sme')
            address = existing_match.get('hq_address') or first_loc.get('address','')
            contracts = existing_match.get('contracts', 0) or 0
            total_contracts = existing_match.get('total_contracts', 0) or 0
            housing_contracts = existing_match.get('housing_contracts', 0) or 0
            contract_count += 1 if existing_contracts else 0
            # phone/website: prefer existing if present, else CQC
            if existing_match.get('phone'): phone = existing_match['phone']
            if existing_match.get('website'): website = existing_match['website']
        else:
            cqc_only += 1
            email = ''
            contact_page = ''
            in_network = False
            description = f"CQC-registered supported {'/'.join(s.lower() for s in cqc_p.get('service_types', ['living']))} provider with {len(cqc_p['locations'])} location(s) in England."
            charity = None
            employees = None
            employee_confidence = ''
            existing_contracts = []
            existing_councils = set()
            existing_regions = set()
            existing_scope = 'Local'
            sectors = ['Housing']
            primary_cat = 'Supported living'
            client_groups = []
            is_ha = False
            is_sme = None
            address = first_loc.get('address', '')
            contracts = 0; total_contracts = 0; housing_contracts = 0

        # UNION of councils: existing-contract councils ∪ CQC location councils
        all_councils = sorted(existing_councils | set(cqc_councils))
        all_regions = sorted(existing_regions | set(cqc_regions))

        merged.append({
            'id': slug,
            'name': display_name,
            'cqc_provider_id': cqc_p['provider_id'],
            'cqc_locations': len(cqc_p['locations']),
            'cqc_local_authorities': cqc_councils,
            'cqc_regions': cqc_regions,
            'website': website,
            'website_unverified': existing_match.get('website_unverified', False) if existing_match else (not website),
            'email': email,
            'contact_page': contact_page,
            'phone': phone,
            'regions': all_regions,
            'councils': all_councils,
            'scope': existing_scope,
            'employees': employees,
            'employee_confidence': employee_confidence,
            'sector': sectors,
            'primary_cat': primary_cat,
            'client_groups': client_groups,
            'is_housing_association': is_ha,
            'description': description,
            'hq_address': address,
            'contracts': contracts,
            'housing_contracts': housing_contracts,
            'total_contracts': total_contracts,
            'contracts_list': existing_contracts,
            'is_sme': is_sme,
            'in_network': in_network,
            'charity': charity,
            'contact_name': existing_match.get('contact_name', '') if existing_match else '',
            'contact_title': existing_match.get('contact_title', '') if existing_match else '',
            # Provenance: where this provider came from
            'source': 'cqc+contracts' if existing_match else 'cqc-only',
        })

    # Add existing providers that DIDN'T appear in CQC (e.g. CAS-2 Nacro overlay, AASC contractors, etc.)
    cqc_norm = {norm_name(p['name']) for p in cqc}
    contract_only = 0
    for p in existing:
        if norm_name(p['name']) in cqc_norm: continue
        # keep as-is but tag source
        ec = dict(p)
        ec['source'] = 'contract-only'
        ec.setdefault('cqc_provider_id', '')
        ec.setdefault('cqc_locations', 0)
        ec.setdefault('cqc_local_authorities', [])
        ec.setdefault('cqc_regions', [])
        merged.append(ec)
        contract_only += 1

    # Build db.json — UNION of CQC location-LAs and contract-councils
    by_id = {p['id']: p for p in merged}
    db = {'c': {}, 'county': {}, 'r': {}, 'n': []}
    seen_nat = set()
    for p in merged:
        # Local: any council from contracts OR any CQC location LA
        for c in set(p.get('councils', [])) | set(p.get('cqc_local_authorities', [])):
            if c: db['c'].setdefault(c, []).append(p['id'])
        clist = p.get('contracts_list', []) or []
        counties = {e.get('county') for e in clist if e.get('scope') == 'County' and e.get('county')}
        for cty in counties:
            db['county'].setdefault(cty, []).append(p['id'])
        # Regional: existing-contract regions only (CQC doesn't tell us regional contracts)
        for reg in {e.get('region') for e in clist if e.get('scope') == 'Regional' and e.get('region')}:
            db['r'].setdefault(reg, []).append(p['id'])
        if any(e.get('scope') == 'National' for e in clist) and p['id'] not in seen_nat:
            db['n'].append(p['id']); seen_nat.add(p['id'])

    # Save
    with open(os.path.join(OUT_DIR, 'providers.json'), 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    with open(os.path.join(OUT_DIR, 'db.json'), 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    # Report
    print()
    print(f"=== MERGE COMPLETE ===")
    print(f"Merged providers total            : {len(merged)}")
    print(f"  • CQC + existing contracts match: {matched_to_existing}")
    print(f"  • CQC only (no contract data)   : {cqc_only}")
    print(f"  • Contract-only (not in CQC)    : {contract_only}")
    print()
    print(f"db.c council index — councils with providers: {len(db['c'])}")
    print(f"  (was 218 in current live db; +{len(db['c']) - 218})")

    md_path = os.path.join(OUT_DIR, 'merge_report.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("# CQC merge — v2 outputs\n\n")
        f.write(f"- Merged provider count: **{len(merged)}** (was 1,969)\n")
        f.write(f"- CQC providers matched to existing contracts: **{matched_to_existing}**\n")
        f.write(f"- CQC-only providers (no contract data): **{cqc_only}** ← these are net-new\n")
        f.write(f"- Contract-only providers (not in CQC, kept as-is): **{contract_only}**\n")
        f.write(f"- Council index size: **{len(db['c'])}** councils with providers (was 218)\n")
        f.write("\n## Sample searches expected to improve\n\n")
        f.write("| Borough | Was | Should now be |\n|---|---:|---:|\n")
        for la, was in [('Hounslow', 0), ('Ealing', 0), ('Newham', 0), ('Southwark', 0),
                        ('Croydon', 0), ('Greenwich', 0), ('Harrow', 0), ('Lambeth', 0),
                        ('Waltham Forest', 0)]:
            n = len(db['c'].get(la, []))
            f.write(f"| {la} | {was} | **{n}** |\n")
    print(f"Wrote {md_path}")

if __name__ == "__main__":
    main()
