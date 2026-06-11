"""Rounds 3-4 consolidated enrichment — apply all name+care-type finds."""
import openpyxl, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

XLSX = 'data/manual_contracts.xlsx'

ADDITIONS = {
    # Round 3 (already applied — re-include for safety)
    'comfort zone care services':
        ('', '01582 933363', '', '', '10250111', ''),
    'deway care':
        ('https://www.cqc.org.uk/location/1-15672134042', '01708 981452', '', '', '12254439', ''),
    's & p care services':
        ('https://spcare.co.uk', '', 'info@spcare.co.uk', 'https://spcare.co.uk/contact', '', ''),
    's and p care services':
        ('https://spcare.co.uk', '', 'info@spcare.co.uk', 'https://spcare.co.uk/contact', '', ''),
    'your choice (barnet) ltd':
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
    # Round 4 finds
    'abiding':
        ('https://www.abidingcare.co.uk', '020 3794 9775', 'referrals@abidingcare.co.uk',
         'https://www.abidingcare.co.uk/contact', '', ''),
    'access for living':
        ('http://accessforliving.org.uk', '020 8690 1911', 'info@accessforliving.org.uk',
         'http://accessforliving.org.uk/contact/', '', ''),
    'advance home care':
        ('https://www.carewatch.co.uk/kingston', '020 8546 2627', 'enquiry.kingston@carewatch.co.uk',
         'https://www.carewatch.co.uk/kingston/contact', '', ''),
    'anytime homes':
        ('https://anytimecare2020.co.uk', '01708 766 388', 'info@anytimecare2020.co.uk',
         'https://anytimecare2020.co.uk/contact-us/', '', ''),
    'aspiration care':
        ('https://aspirationscare.com', '01452 399 190', 'info@aspirationscare.com',
         'https://aspirationscare.com/contact/', '', ''),
    'assured living care services':
        ('https://assuredlivingservices.co.uk', '01322 386 022', 'info@assuredlivingservices.co.uk',
         'https://assuredlivingservices.co.uk/contact', '14365652', ''),
    'aurora options':
        ('https://www.auroraoptions.org.uk', '020 7237 1055', 'info@auroraoptions.org.uk',
         'https://www.auroraoptions.org.uk/Contact', '', ''),
    'be caring':
        ('https://www.becaring.org.uk', '0191 281 2797', 'adminBeCaring@BeCaring.org.uk',
         'https://becaring.org.uk/contact-us/', '', ''),
    'barmat healthcare':
        ('https://barmathealthcare.co.uk', '020 8214 1170', 'info@barmathealthcare.co.uk',
         'https://barmathealthcare.co.uk/contact-us/', '', ''),
    'carby community care':
        ('https://www.carbycare.com', '020 8461 5091', 'enquiries@carbycare.com',
         'https://www.carbycare.com/contact', '', ''),
}

wb = openpyxl.load_workbook(XLSX)
ws_co = wb['Companies']

updated = 0
already = 0
for row in ws_co.iter_rows(min_row=2):
    name = str(row[0].value or '').strip()
    if not name: continue
    review_tag = str(row[20].value or '').strip()
    key = name.lower()
    if key not in ADDITIONS: continue
    if review_tag == 'verified':
        already += 1
        continue
    website, phone, email, contact, ch_num, charity_num = ADDITIONS[key]
    if website: row[12].value = website
    if phone: row[13].value = phone
    if email: row[14].value = email
    if contact: row[15].value = contact
    if ch_num: row[7].value = ch_num
    if charity_num: row[16].value = charity_num
    has_contact = sum([1 if website else 0, 1 if phone else 0, 1 if email else 0])
    if has_contact >= 2:
        row[20].value = 'verified'
    else:
        row[20].value = 'partial'
    updated += 1

wb.save(XLSX)
print(f"Newly updated: {updated} (was already verified: {already})")
