"""Round 3 enrichment — added name+care-type search results."""
import openpyxl, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

XLSX = 'data/manual_contracts.xlsx'

# Round 3 finds (name + care type search)
ROUND3 = {
    'comfort zone care services':
        ('', '01582 933363', '', '', '10250111', ''),
    'deway care':
        ('', '01708 981452', '', '', '12254439', ''),
    's & p care services':
        ('https://spcare.co.uk', '', 'info@spcare.co.uk',
         'https://spcare.co.uk/contact', '', ''),
    's and p care services':
        ('https://spcare.co.uk', '', 'info@spcare.co.uk',
         'https://spcare.co.uk/contact', '', ''),
    'your choice (barnet) ltd':
        ('https://yourchoicebarnet.org', '020 8440 9278', 'supportedliving@yourchoicebarnet.org',
         'https://yourchoicebarnet.org/contact-us/', '', ''),
    'your choice barnet':
        ('https://yourchoicebarnet.org', '020 8440 9278', 'supportedliving@yourchoicebarnet.org',
         'https://yourchoicebarnet.org/contact-us/', '', ''),
    'metropolitan thames valley housing':
        ('https://www.mtvh.co.uk', '0203 535 3535', 'communications@mtvh.co.uk',
         'https://www.mtvh.co.uk/contact-us/', '', ''),
    'lifeways supported independent living':
        ('https://lifeways.co.uk', '0333 321 4881', 'head.office@lifeways.co.uk',
         'https://lifeways.co.uk/contact-us', '', ''),
    'dimensions personalised support':
        ('https://www.dimensions-uk.org', '0300 303 9001', 'info@dimensions-uk.org',
         'https://www.dimensions-uk.org/contact-us/', '', '1108960'),
    'united response services':
        ('https://www.unitedresponse.org.uk', '0800 0884 377', 'info@unitedresponse.org.uk',
         'https://www.unitedresponse.org.uk/contact-us/', '', '265249'),
    'social interest group':
        ('https://socialinterestgroup.org.uk', '020 3668 9270',
         'enquiries@socialinterestgroup.org.uk',
         'https://socialinterestgroup.org.uk/contact-us/', '', '1144625'),
    'coventry refugee & migrant centre':
        ('https://covrefugee.org', '024 7622 7254', 'info@covrefugee.org',
         'https://covrefugee.org/contact-us/', '', '1126381'),
    'coventry refugee and migrant centre':
        ('https://covrefugee.org', '024 7622 7254', 'info@covrefugee.org',
         'https://covrefugee.org/contact-us/', '', '1126381'),
    'north worcestershire basement project':
        ('https://www.basementproject.org', '01527 832993', 'info@basementproject.org',
         'https://www.basementproject.org/contact/', '05230659', '1106209'),
    'camden society london thera trust':
        ('https://www.thecamdensociety.co.uk', '020 7281 1888', 'info@thecamdensociety.co.uk',
         'https://www.thera.co.uk/about/companies/the-camden-society/', '', ''),
    'step4ward services kent':
        ('https://step4wd.co.uk', '01843 220 944', 'info@step4wd.co.uk',
         'https://step4wd.co.uk/contact', '11932388', ''),
    'step4ward services':
        ('https://step4wd.co.uk', '01843 220 944', 'info@step4wd.co.uk',
         'https://step4wd.co.uk/contact', '11932388', ''),
    'capital letters':
        ('https://capitalletters.org.uk', '020 3950 4640', 'info@capitalletters.org.uk',
         'https://capitalletters.org.uk/contact-us/', '', ''),
    'expert link':
        ('https://expertlink.org.uk', '01392 247 999', 'info@expertlink.org.uk',
         'https://expertlink.org.uk/contact/', '', '1177817'),
    'valley housing':
        ('https://valley-supported-living.org.uk', '01706 878 031',
         'fbarker@valley-supported-living.org.uk',
         'https://valley-supported-living.org.uk/contact/', '', ''),
    'hestia':
        ('https://www.hestia.org', '020 7378 3100', 'info@hestia.org',
         'https://www.hestia.org/contact-hestia', '', '294555'),
}

wb = openpyxl.load_workbook(XLSX)
ws_co = wb['Companies']

updated = already = skipped = 0
for row in ws_co.iter_rows(min_row=2):
    name = str(row[0].value or '').strip()
    if not name: continue
    review_tag = str(row[20].value or '').strip()
    key = name.lower()
    if key not in ROUND3: continue
    if review_tag == 'verified':
        already += 1
        continue
    website, phone, email, contact, ch_num, charity_num = ROUND3[key]
    if website: row[12].value = website
    if phone: row[13].value = phone
    if email: row[14].value = email
    if contact: row[15].value = contact
    if ch_num: row[7].value = ch_num
    if charity_num: row[16].value = charity_num
    # Only flag as fully verified if we have at least 2 of (website, phone, email)
    has_contact = sum([1 if website else 0, 1 if phone else 0, 1 if email else 0])
    if has_contact >= 2:
        row[20].value = 'verified'
        updated += 1
    else:
        row[20].value = 'partial'
        updated += 1
        print(f"  partial: {name}")

wb.save(XLSX)
print(f"\nRound 3 enrichment results:")
print(f"  Newly verified: {updated}")
print(f"  Already done  : {already}")
