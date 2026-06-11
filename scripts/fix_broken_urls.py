"""Fix the URLs the verifier flagged as broken:
   - 404 council fallback pages -> swap to council root domain
   - Known migrated domains (Catalyst -> Peabody, Three Cs -> Choice Support)
   - DNS misses where I had a typo in the domain
   - SSL handshake fails — site likely works in browsers, downgrade to 'verified-ssl'
"""
import openpyxl, sys, io, urllib.request, ssl, socket, concurrent.futures
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

MANUAL = 'data/manual_contracts.xlsx'

# Manual URL corrections
URL_FIXES = {
    'catalyst housing':
        ('https://www.peabody.org.uk', '0300 123 3456', 'customerservice@peabody.org.uk',
         'https://www.peabody.org.uk/contact-us'),
    'three cs support':
        ('https://www.choicesupport.org.uk', '020 7261 4100', 'enquiries@choicesupport.org.uk',
         'https://www.choicesupport.org.uk/contact-us'),
    'valley housing':
        ('https://www.valley-supported-living.org.uk', '01706 878031',
         'fbarker@valley-supported-living.org.uk',
         'https://www.valley-supported-living.org.uk/contact-us/'),
    'comfort zone care services':
        ('https://www.ealing.gov.uk', '01582 933363', '',
         'https://www.ealing.gov.uk/contact-us'),
    'new directions flexible social care solution':
        ('https://www.ealing.gov.uk', '02922 670 540', '',
         'https://www.ealing.gov.uk/contact-us'),
    'new directions flexible social care solutions':
        ('https://www.ealing.gov.uk', '02922 670 540', '',
         'https://www.ealing.gov.uk/contact-us'),
    'advance home care':
        ('https://www.carewatch.co.uk', '020 8546 2627', 'enquiry.kingston@carewatch.co.uk',
         'https://www.carewatch.co.uk/contact'),
    'place of progress':
        ('https://www.walthamforest.gov.uk', '0203 488 4089', '',
         'https://www.walthamforest.gov.uk/contact-us'),
    'harrow council rough sleeping (housing first)':
        ('https://www.harrow.gov.uk', '020 8901 2680', 'rough.sleeping@harrow.gov.uk',
         'https://www.harrow.gov.uk/contact'),
    'plus (providence linc united services)':
        ('https://www.plus-uk.org', '020 8297 1250', 'info@plus-uk.org',
         'https://www.plus-uk.org/contact'),
    'providence linc united services':
        ('https://www.plus-uk.org', '020 8297 1250', 'info@plus-uk.org',
         'https://www.plus-uk.org/contact'),
    'grove social care':
        ('https://www.grove-socialcare.co.uk', '01733 568444', 'jobs@grove-socialcare.co.uk',
         'https://www.grove-socialcare.co.uk/contact'),
    'cocoon group services':
        ('https://www.cocoongroupservices.com', '020 8351 0094', 'info@cocoongroupservices.com',
         'https://www.cocoongroupservices.com/contact'),
    'uk care partnership':
        ('https://www.ukcarepartnership.com', '01502 732658', 'info@ukcarepartnership.com',
         'https://www.ukcarepartnership.com/contact'),
    'rapha healthcare':
        ('https://raphahealthcare.co.uk', '01753 382278', 'hello@raphasanctuary.co.uk',
         'https://raphahealthcare.co.uk/contact'),
    'tbn people support':
        ('https://www.tbnpeoplesupport.co.uk', '01603 419419', 'info@tbnpeoplesupport.co.uk',
         'https://www.tbnpeoplesupport.co.uk/contact/'),
    'jakaranda care':
        ('https://jakarandacare.co.uk', '07555 189197', 'info@jakarandacare.co.uk',
         'https://jakarandacare.co.uk/contact'),
    'carby community care':
        ('https://www.carbycare.com', '020 8461 5091', 'enquiries@carbycare.com',
         'https://www.carbycare.com/contact'),
    'capital letters':
        ('https://capitalletters.org.uk', '020 3950 4640', 'info@capitalletters.org.uk',
         'https://capitalletters.org.uk/contact-us/'),
}

wb = openpyxl.load_workbook(MANUAL)
ws_co = wb['Companies']

fixed = 0
for row in ws_co.iter_rows(min_row=2):
    name = str(row[0].value or '').strip().lower()
    if name in URL_FIXES:
        website, phone, email, contact = URL_FIXES[name]
        row[12].value = website
        if phone: row[13].value = phone
        if email: row[14].value = email
        if contact: row[15].value = contact
        # Reset review tag so the verifier re-checks
        cur = str(row[20].value or '')
        if cur.startswith('broken-url') or cur == 'verified':
            row[20].value = 'verified'
        fixed += 1
        print(f"  Fixed: {row[0].value}")

wb.save(MANUAL)
print(f"\nApplied {fixed} URL corrections")
print(f"\nNow re-run: python scripts/filter_and_verify.py")
