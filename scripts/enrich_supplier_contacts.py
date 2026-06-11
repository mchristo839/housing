"""Replace 'via-commissioner' contact info with verified direct contacts
for suppliers we've researched. Leave the rest as via-commissioner.

Verified contacts come from web search of each supplier's official site,
CQC listing, Charity Commission register, or NHS service directory.
"""
import openpyxl, sys, io
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

XLSX = 'data/manual_contracts.xlsx'

# (name_lower → (website, phone, email, contact_page, companies_house, charity_no))
VERIFIED = {
    # Major London/national supported-housing providers
    'hestia housing & support':
        ('https://www.hestia.org', '020 7378 3100', 'info@hestia.org',
         'https://www.hestia.org/contact-hestia', '', '294555'),
    'hestia housing and support':
        ('https://www.hestia.org', '020 7378 3100', 'info@hestia.org',
         'https://www.hestia.org/contact-hestia', '', '294555'),
    'look ahead care & support':
        ('https://www.lookahead.org.uk', '020 7937 1166', 'info@lookahead.org.uk',
         'https://www.lookahead.org.uk/about-us/contact-us/', '', ''),
    'look ahead care and support':
        ('https://www.lookahead.org.uk', '020 7937 1166', 'info@lookahead.org.uk',
         'https://www.lookahead.org.uk/about-us/contact-us/', '', ''),
    'look ahead housing & care':
        ('https://www.lookahead.org.uk', '020 7937 1166', 'info@lookahead.org.uk',
         'https://www.lookahead.org.uk/about-us/contact-us/', '', ''),
    'look ahead housing and care':
        ('https://www.lookahead.org.uk', '020 7937 1166', 'info@lookahead.org.uk',
         'https://www.lookahead.org.uk/about-us/contact-us/', '', ''),
    "st mungo's":
        ('https://www.mungos.org', '020 3856 6000', 'info@mungos.org',
         'https://www.mungos.org/contact/', '', '1149085'),
    "st mungos":
        ('https://www.mungos.org', '020 3856 6000', 'info@mungos.org',
         'https://www.mungos.org/contact/', '', '1149085'),
    'st mungo community housing association':
        ('https://www.mungos.org', '020 3856 6000', 'info@mungos.org',
         'https://www.mungos.org/contact/', '', '1149085'),
    'turning point services':
        ('https://www.turning-point.co.uk', '020 7481 7600', 'referrals@turning-point.co.uk',
         'https://www.turning-point.co.uk/contact-us', '', '234887'),
    'catalyst housing':
        ('https://www.catalysthousing.co.uk', '0300 456 2099',
         'customerservice@catalysthousing.co.uk',
         'https://www.catalysthousing.co.uk/contact-us', '', ''),
    'certitude':
        ('https://certitude.london', '020 3397 3033', 'referrals@certitude.london',
         'https://certitude.org.uk/contact', '', ''),

    # Mid-size specialist providers
    'profad care agency':
        ('https://profadcareagency.co.uk', '020 7639 0839', 'info@profadcareagency.co.uk',
         'https://profadcareagency.co.uk/contact', '', ''),
    'chosen care group':
        ('https://chosencaregroup.com', '020 8214 1093', 'complaint@chosencaregroup.com',
         'https://chosencaregroup.com/contact-us/', '', ''),
    'eleanor nursing & social care':
        ('https://www.eleanorhealthcaregroup.co.uk', '020 8690 2406', 'info@eleanorcare.co.uk',
         'https://www.eleanorhealthcaregroup.co.uk/contact-us/', '', ''),
    'eleanor nursing and social care':
        ('https://www.eleanorhealthcaregroup.co.uk', '020 8690 2406', 'info@eleanorcare.co.uk',
         'https://www.eleanorhealthcaregroup.co.uk/contact-us/', '', ''),
    'caretech community services':
        ('https://www.caretech-uk.com', '01707 601 800', 'info@caretech-uk.com',
         'https://www.caretech-uk.com/contact-us', '', ''),
    'grove social care':
        ('https://www.grovesocialcare.co.uk', '01733 568444', 'jobs@grovesocialcare.co.uk',
         'https://www.grovesocialcare.co.uk/contact', '10567559', ''),
    'voyage 1':
        ('https://www.voyagecare.com', '0800 035 3776', 'referrals@voyagecare.com',
         'https://www.voyagecare.com/contact-us/', '', ''),
    'accomplish group support':
        ('https://www.accomplish-group.co.uk', '0151 726 1460', 'info@accomplish-group.co.uk',
         'https://www.accomplish-group.co.uk/contact-us/', '', ''),
    'avenues group':
        ('https://www.avenuesgroup.org.uk', '01622 366 911', 'info@avenuesgroup.org.uk',
         'https://www.avenuesgroup.org.uk/contact-us/', '', ''),
}

wb = openpyxl.load_workbook(XLSX)
ws_co = wb['Companies']

updated = 0
not_found = []
for row in ws_co.iter_rows(min_row=2):
    name = str(row[0].value or '').strip()
    review_tag = str(row[20].value or '').strip()
    if review_tag != 'via-commissioner':
        continue
    key = name.lower()
    if key not in VERIFIED:
        not_found.append(name)
        continue
    website, phone, email, contact, ch_num, charity_num = VERIFIED[key]
    row[12].value = website        # Website
    row[13].value = phone          # Telephone
    row[14].value = email          # Email
    row[15].value = contact        # Contact Page
    if ch_num: row[7].value = ch_num
    if charity_num: row[16].value = charity_num
    row[20].value = 'verified'
    updated += 1
    print(f"  ✓ {name:45s} -> {website}")

wb.save(XLSX)
print(f"\nSummary:")
print(f"  Enriched (now 'verified')      : {updated}")
print(f"  Still 'via-commissioner'       : {len(not_found)}")
print(f"  (Use council-routed contact path until directly enriched)")
