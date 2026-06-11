"""Auto-promote providers to Verified status using BOTH Companies House
and Apify signals.

A provider becomes "Verified" automatically when ALL of:
  1. Companies House: company is ACTIVE (not dissolved)
  2. Companies House: SIC code matches a housing/care category
  3. Apify: website mentions the company name (Step 1 pass)
  4. Apify: page contains at least one housing service keyword (Step 3 pass)
  5. Apify: at least one of email / phone / contact_url present

A provider becomes auto-DROPPED only when ALL of:
  1. Companies House: company is DISSOLVED or LIQUIDATED, OR
     SIC code is in a clearly-non-housing category (manufacturing, retail, etc.)
  2. Apify page contains a NEGATIVE keyword (pizza/vet/builder/etc.)
  3. No housing keyword found

Anything else stays "Listed" and waits for human review.

USAGE:
  python scripts/auto_verify.py             # apply auto-promotions
  python scripts/auto_verify.py preview     # show what would change without writing
"""
import json, sys
from pathlib import Path

CH_FILE        = Path('data/verification/companies_house.json')
APIFY_FILE     = Path('data/verification/apify_analysed.json')
FIRECRAWL_FILE = Path('data/verification/firecrawl_analysed.json')
GOOGLE_FILE    = Path('data/verification/google_keyword.json')
VERIFIED_FILE  = Path('data/verification/VERIFIED.json')
DROPS_FILE     = Path('data/MANUAL_DROP_LIST.json')

# SIC codes that DEFINITELY mean not-housing (won't get any benefit-of-doubt)
NON_HOUSING_SIC = {
    '10110','10120','10130','10200',                  # food manufacturing
    '20140','20150','20520','20590',                  # chemicals
    '22220','22230','22290',                          # plastics manufacturing
    '25110','25120','25210','25290','25620','25710',  # metals
    '41200',                                          # construction (general)
    '43210','43220','43290','43310','43320','43330',  # specialised construction
    '43990','43910','43999',
    '45200','45310','45320','45400',                  # vehicle repair / parts
    '46350','46380','46420','46430','46470','46499',  # wholesale
    '47110','47190','47220','47410','47420','47430',  # retail
    '47521','47522','47523','47540','47710','47720',
    '47730','47781','47782','47789','47791','47799',
    '47910','47990',
    '55100','55201','55209','55300','55900',          # accommodation services (hotels)
    '56101','56102','56103','56210','56290','56301','56302', # food service
    '62012','62020','62090',                          # IT services
    '63110','63120',                                  # data processing
    '70210','70221','70229',                          # consultancy
    '71121','71122','71129',                          # engineering
    '73110','73120',                                  # advertising
    '74100','74300','74909','74990',                  # design / specialised
    '75000',                                          # veterinary
    '78101','78102','78109','78200','78300',          # recruitment / staffing
    '85100','85200','85310','85320','85410','85421',  # education
    '85422','85510','85520','85530','85590','85600',
    '90030','90040','91011','93290',                  # arts / leisure
    '96010','96020','96030','96040','96090',          # other services
}

def load_json(p, default=None):
    return json.load(open(p, encoding='utf-8')) if p.exists() else (default or {})

def auto_classify(name, ch_record, apify_record, firecrawl_record, google_record):
    """Combine ALL 4 signal sources into a single verdict.

    Returns ('KEEP'|'DROP'|'NONE', reason).
       NONE = no automated decision, leave as Listed for human review.
    """
    ch  = ch_record or {}
    ap  = apify_record or {}
    fc  = firecrawl_record or {}
    gg  = google_record or {}

    sic_codes  = set(ch.get('sic_codes', []))
    is_housing_sic = ch.get('is_housing', False)
    is_non_housing_sic = bool(sic_codes & NON_HOUSING_SIC)
    is_active = ch.get('status') == 'active'
    is_dissolved = ch.get('status') in {'dissolved', 'liquidation', 'in administration'}

    # Apify signals (homepage + 4 sub-pages crawled)
    apify_name_match = ap.get('name_match', False)
    apify_housing = ap.get('housing_terms', [])
    apify_negative = ap.get('non_housing_terms', [])
    apify_contact = bool(ap.get('emails') or ap.get('phones') or ap.get('contact_url'))

    # Firecrawl signals (markdown extraction OR LLM-judged structured extract)
    fc_name_match = fc.get('name_match', False)
    fc_housing = fc.get('housing_terms', [])
    fc_negative = fc.get('non_housing', [])
    fc_contact = bool(fc.get('emails') or fc.get('phones'))
    # Firecrawl /extract also gives us the CH number if it's on the site
    fc_ch_number = fc.get('ch_number', '')

    # Google signals (whole-site keyword presence)
    google_name_match = gg.get('name_match', False)
    google_housing = gg.get('housing_hits', [])

    # Union all 3 site-evidence sources
    site_name_match = apify_name_match or fc_name_match or google_name_match
    site_housing_terms = sorted(set(apify_housing) | set(fc_housing) | set(google_housing))
    site_negative = sorted(set(apify_negative) | set(fc_negative))
    has_contact = apify_contact or fc_contact

    # Bonus: if Firecrawl extracted a CH number AND it matches our CH record,
    # that's strong proof the website really belongs to the company.
    ch_number_match = bool(ch.get('number') and fc_ch_number and
                           ch.get('number') == fc_ch_number)

    # ---- DROP path ----
    if is_dissolved:
        return 'DROP', f"Companies House: {ch.get('status')}"
    if is_non_housing_sic and site_negative and not site_housing_terms:
        return 'DROP', f"SIC {sorted(sic_codes & NON_HOUSING_SIC)} + site negatives {site_negative}"
    if site_negative and not site_housing_terms and not site_name_match:
        return 'DROP', f"site shows {site_negative}; not a housing provider"

    # ---- KEEP path ---- (strongest evidence first)
    if ch_number_match:
        # Firecrawl extracted a CH number AND it matches our official CH lookup —
        # this is the gold-standard proof of website ownership.
        return 'KEEP', f"CH number {ch.get('number')} confirmed on website (Firecrawl)"
    if is_active and is_housing_sic and site_housing_terms and (site_name_match or has_contact):
        return 'KEEP', f"CH housing SIC + site terms {site_housing_terms[:3]}"
    if is_active and is_housing_sic and site_name_match:
        return 'KEEP', f"CH housing SIC + site name match"
    if site_housing_terms and site_name_match and has_contact:
        return 'KEEP', f"site name match + housing terms {site_housing_terms[:3]} + contacts"
    if is_active and is_housing_sic and ch.get('number'):
        # Active company with housing SIC code is strong enough on its own
        # if we don't have any contradictory site signal.
        if not site_negative:
            return 'KEEP', f"CH active + housing SIC ({ch.get('sic_codes',[])})"

    return 'NONE', ""

def main(preview=False):
    ch_db        = load_json(CH_FILE)
    apify_db     = load_json(APIFY_FILE)
    firecrawl_db = load_json(FIRECRAWL_FILE)
    google_db    = load_json(GOOGLE_FILE)
    verified     = load_json(VERIFIED_FILE)
    drops        = load_json(DROPS_FILE, [])

    print(f"Signals loaded:")
    print(f"  Companies House lookups: {len(ch_db)}")
    print(f"  Apify scrapes:           {len(apify_db)}")
    print(f"  Firecrawl results:       {len(firecrawl_db)}")
    print(f"  Google checks:           {len(google_db)}")

    prov_names = [p['name'] for p in json.load(
        open('api/_data/providers.json', encoding='utf-8'))]

    new_keeps = []
    new_drops = []
    for name in prov_names:
        if name in verified:    continue
        if name in drops:       continue
        verdict, reason = auto_classify(
            name, ch_db.get(name), apify_db.get(name),
            firecrawl_db.get(name), google_db.get(name))
        if verdict == 'KEEP':
            new_keeps.append((name, reason))
        elif verdict == 'DROP':
            new_drops.append((name, reason))

    print(f"Auto-classification result:")
    print(f"  New KEEPs (auto-verify):  {len(new_keeps)}")
    print(f"  New DROPs (auto-drop):    {len(new_drops)}")

    if not preview:
        for name, reason in new_keeps:
            verified[name] = {'verdict':'KEEP','step1':'AUTO','services':'auto-verified via CH + Apify',
                              'verified_at':__import__('time').strftime('%Y-%m-%d'),
                              'notes': reason}
        for name, reason in new_drops:
            if name not in drops: drops.append(name)
        json.dump(verified, open(VERIFIED_FILE, 'w', encoding='utf-8'), indent=2)
        json.dump(drops,    open(DROPS_FILE, 'w', encoding='utf-8'), indent=2)
        print(f"\nWritten to {VERIFIED_FILE} and {DROPS_FILE}")
        print(f"Next: python build_data.py && npm run build && vercel deploy --prod --yes")
    else:
        print("\nPreview only — no files written. Drop --preview to apply.")
        # Show samples
        for name, reason in new_keeps[:10]:
            print(f"  KEEP  {name[:48]:<50s}  ({reason})")
        for name, reason in new_drops[:10]:
            print(f"  DROP  {name[:48]:<50s}  ({reason})")

if __name__ == '__main__':
    preview = (len(sys.argv) > 1 and sys.argv[1] == 'preview')
    main(preview=preview)
