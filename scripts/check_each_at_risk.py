"""Per-provider verdict for the 94 'consortium-only' at-risk providers.

Cross-references each against:
  1. NWADCS official TC160 FPS supplier list
  2. Domain heuristics (waste/plastics/engineering/retail etc.)
  3. Manual website-check results from this session
"""
import json, re

# 1. Authoritative NWADCS TC160 FPS provider list (fetched from nwadcs.org.uk/list-providers-supported-accommodation-fps)
NWADCS_OFFICIAL = [
    "123 Supported Accommodation", "Abicare Health Solutions Ltd T/A ChivMor Living",
    "Active 8 Support Services Limited", "Adullam Homes Housing Association Limited",
    "Advance Social Care limited", "Alternative Approach ltd", "Altus Social Ltd",
    "AMJ Support Services LTD", "Avensis Support Ltd", "Bear Care Services Ltd",
    "Bedspace Ltd", "Believe and Achieve Support Ltd", "Bramhall Care Ltd",
    "Calderstones Support Group", "Calmliving Healthcare Limited", "Care & Community Ltd",
    "Care Matters Ltd", "Cathmor Limited", "CFS Care Ltd",
    "Cheery Blossom Supported Living Ltd", "Coastal Key Housing",
    "Continuum Support Care Services Ltd", "Cottongrass Homes Limited",
    "Creative Living", "Croft Healthcare Ltd", "Crystal Care Solutions",
    "Dream Big Independent Living Ltd", "Dynamis Enterprises Ltd", "Educla",
    "Elite Education and Social Care Services", "Fairview Care and Support",
    "Firbanks Supported Living", "Freya Group Ltd T/A Forever Care", "Fusion Care",
    "High Rise Support Services", "Hillgate Health Group Limited", "Hillside Care Ltd",
    "Hope Care Group Ltd", "Horizon Care and Education", "Horizons Plus",
    "Identity Care Housing", "Independent Futures (UK) Ltd", "Independent Together Ltd",
    "Indie 16 Ltd", "Inicio Group LTD", "Insight (fylde)", "Inspira Care",
    "Inspire Community Services", "ISW CSC Ltd", "Kempshire Ltd", "Key 4 Moving On Ltd",
    "Key Steps Supported Accommodation", "Keys PCE Limited", "Kilter Care Ltd",
    "Local Solutions", "Manchester Settlement", "Moving Up Care", "My3 Ltd",
    "National Family Support Service (Rebuild)", "New Pathway Ltd",
    "Next Stage A Way Forward Youth Development", "Next Steps Support Services Ltd",
    "Nook Residential Limited", "North West Leaving Care Services Limited",
    "North West Social Care and Support Ltd", "Northern Community Pathways Limited GM",
    "Northern Community Pathways Limited Lancs", "Northwest Support Ltd",
    "Omega Care Group Ltd", "Orion Care Solutions Limited",
    "Phoenix Housing Support Cumbria Ltd", "Progressive Independence Limited",
    "Raisso house ltd", "REACH-IN FOR CARE LTD", "Revive Social Care",
    "Revolve Therapy and Training", "Right Step Limited RSL",
    "Safehands Ltd Liverpool", "Sageville Healthcare Limited", "Salaam Care",
    "Salvation Army Housing Association", "Salvus Support Ltd",
    "Shield Support Hub Ltd", "Signature Aftercare Ltd",
    "Social Care Services Group", "Solis Care Ltd", "Step Ahead Resource Services",
    "Step up supported living limited", "Taylor Made Prospects Ltd",
    "The Flame Lily Healthcare UK Limited", "The Intact Project",
    "The Stepping Stone Project", "Thrive Leaving Care Ltd",
    "TPR Care Services Ltd", "Transition 360 Limited", "Triangle Support Services Ltd",
    "Upwards Care Solutions", "Vibrant Group Ltd 1st Choice Housing Solutions",
    "Vista Living Limited", "Young people first", "Your Path Leaving Care",
    "Youth Haven Ltd",
]

def norm(s):
    s = (s or '').lower()
    s = re.sub(r'\bt\s*/\s*a\b.*$', '', s)
    s = re.sub(r'\b(ltd|limited|cic|llp|plc|co)\b', '', s)
    s = re.sub(r'\(.*?\)', '', s)
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    return ' '.join(s.split())

nwadcs_index = {norm(n): n for n in NWADCS_OFFICIAL}

# Manual verdicts from website checks done this session
DOMAIN_BAD = {
    'biobagworld.com': 'compostable bags',
    'bspolythene.co.uk': 'plastic film',
    'contenur.co.uk': 'wheelie bins',
    'craemer.com': 'warehouse storage',
    'cromwellpolythene.co.uk': 'plastic bags',
    'duluxdecoratorcentre.co.uk': 'paint',
    'jameshargreaves.com': 'plumbing supplies',
    'kbextruders.co.uk': 'extrusion machinery',
    'rs-online.com': 'electronic components',
    'peterridley.co.uk': 'recycling',
    'stearn.co.uk': 'electrical wholesaler',
    'stormenviro.co.uk': 'environmental services',
    'iplglobal.com': 'manufacturing',
    'travisperkins.co.uk': 'builders merchant',
    'unicorn-group.com': 'containers',
    'wolseley.co.uk': 'plumbing/heating supplies',
    'ese.com': 'waste management',
    'egberttaylor.com': 'waste bin manufacturer',
    'jacksons-fencing.co.uk': 'fencing',
    'sackmaker.com': 'sacks',
    'fairportcontainers.co.uk': 'containers',
    'ukcontainers.co.uk': 'containers',
    'lestapackaging.co.uk': 'packaging',
    'premierekitchens.co.uk': 'kitchens',
    'thebeckcompanyltd.com': 'plumbing supplies',
    'protectechnical.co.uk': 'engineering',
    'alancowardandson.co.uk': 'waste containers',
    'windrushvalleyhouseclearance.co.uk': 'house clearance',
    'smithbrosuk.com': 'wholesale',
    'mccarthyandstoneresales.co.uk': 'retirement property resales (wrong domain)',
    'altussearch.co.uk': 'recruitment co (wrong domain — provider IS on NWADCS list)',
    'brightavenue.co': 'web design agency',
    'midcareservices.com': 'homecare-only',
    'revolve-leadership.com': 'training (wrong domain — provider IS on NWADCS list)',
    'rightsteps.co.uk': 'workplace mental health (wrong domain — provider IS on NWADCS list)',
    'project-insights.co.uk': 'market research',
    'dynamiseducation.co.uk': 'training (wrong domain — provider IS on NWADCS list)',
    'avensishospitality.co.uk': 'hospitality (wrong domain — provider IS on NWADCS list)',
    'jhillandsons.co.uk': 'funeral directors',
    'transform-lives.org': 'employment/wellbeing',
    'capitalletters.org.uk': 'procurement vehicle, not a provider',
    'zaubacorp.com': 'Indian company directory listing',
}

# Domains we verified ARE legitimate housing/care
DOMAIN_GOOD = {
    'i2gether.org.uk': 'supported housing GM 16-25',
    'edenfutures.org': 'supported living for disabilities',
    'manchestersettlement.org.uk': 'multi-service charity with youth supported housing',
    'my3ltd.co.uk': 'supported accom for children with autism/LD',
    'step-a-head.co.uk': 'supported housing 16+',
    'intactprojects.co.uk': 'supported accom 16-18',
    'cathmor.co.uk': 'support/training/accommodation for young people',
    'safehandsliveincare.co.uk': 'supported live-in care',
    'safehandshealthcare.co.uk': 'homecare-only (but on NWADCS list as Safehands Ltd Liverpool)',
}

WRONG_DOMAIN_NWADCS = {
    'altussearch.co.uk', 'revolve-leadership.com', 'rightsteps.co.uk',
    'dynamiseducation.co.uk', 'avensishospitality.co.uk', 'mccarthyandstoneresales.co.uk',
}

prov = json.load(open('api/_data/providers.json', encoding='utf-8'))

keep, drop, recheck = [], [], []
for p in prov:
    contracts = p.get('contracts_list') or []
    direct = [c for c in contracts if not c.get('via')]
    via    = [c for c in contracts if c.get('via')]
    if direct or not via: continue
    name = p['name']
    website = (p.get('website','') or '').lower()
    domain = re.sub(r'^https?://(www\.)?', '', website).split('/')[0] if website else ''
    fw = via[0].get('via','')

    # Match against NWADCS official list
    n = norm(name)
    nwadcs_match = nwadcs_index.get(n)
    if not nwadcs_match and len(n) >= 8:
        for k, official in nwadcs_index.items():
            if n in k or k in n:
                nwadcs_match = official; break

    rec = {'name': name, 'website': website, 'domain': domain, 'fw': fw,
           'nwadcs_match': nwadcs_match}

    # Decision tree
    if nwadcs_match:
        if domain in WRONG_DOMAIN_NWADCS:
            rec['verdict'] = 'KEEP'
            rec['reason'] = f'On official NWADCS list as "{nwadcs_match}" — but {domain} is the wrong domain (needs fix)'
        else:
            rec['verdict'] = 'KEEP'
            rec['reason'] = f'On official NWADCS TC160 list as "{nwadcs_match}"'
        keep.append(rec)
        continue

    if domain in DOMAIN_BAD:
        rec['verdict'] = 'DROP'
        rec['reason'] = f'Domain is unrelated business: {DOMAIN_BAD[domain]}'
        drop.append(rec)
        continue

    if domain in DOMAIN_GOOD:
        rec['verdict'] = 'KEEP'
        rec['reason'] = f'Verified housing/care provider: {DOMAIN_GOOD[domain]}'
        keep.append(rec)
        continue

    if fw == 'NWADCS FPS':
        rec['verdict'] = 'DROP'
        rec['reason'] = f'Tagged NWADCS in our data but NOT on official NWADCS list — false tag'
        drop.append(rec)
        continue

    rec['verdict'] = 'RECHECK'
    rec['reason'] = 'Not yet verified — need website read'
    recheck.append(rec)

# Save the verdict pack
import csv
with open('data/scraped/AT_RISK_94_VERDICT.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['Verdict', 'Provider Name', 'Framework', 'Website', 'Reason', 'NWADCS Match'])
    for r in keep + drop + recheck:
        w.writerow([r['verdict'], r['name'], r['fw'], r['website'], r['reason'], r.get('nwadcs_match','')])

print(f"=== KEEP ({len(keep)}) — evidence-backed ===")
for r in keep:
    print(f"  · {r['name'][:42]:<44s}  {r['reason'][:80]}")

print(f"\n=== DROP ({len(drop)}) — no evidence / wrong attribution ===")
for r in drop:
    print(f"  · {r['name'][:42]:<44s}  {r['reason'][:80]}")

print(f"\n=== RECHECK ({len(recheck)}) — needs manual verification ===")
for r in recheck:
    print(f"  · {r['name'][:42]:<44s}  {r['website'][:48]}")

print(f"\nTOTALS  keep={len(keep)}  drop={len(drop)}  recheck={len(recheck)}")
print(f"Saved verdict pack: data/scraped/AT_RISK_94_VERDICT.csv")
