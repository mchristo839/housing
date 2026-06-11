"""Swap client-facing email aliases (referrals@, intake@, placements@, etc.)
for general business contact addresses on the same domain.

Reasoning: our users (landlords / property owners) want to contact the
supplier about a property they could lease/buy/operate from — they're not
prospective clients. Sending a property pitch to referrals@ goes to the
wrong inbox.

For each supplier with a client-facing prefix, swap to in priority order:
  1. info@<domain>
  2. enquiries@<domain>
  3. contact@<domain>
  4. hello@<domain>
  5. admin@<domain>
"""
import openpyxl, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

MANUAL = 'data/manual_contracts.xlsx'

# Email prefixes that route to client intake — wrong audience for landlord enquiries
CLIENT_PREFIXES = re.compile(
    r"^(referral|referrals|intake|placement|placements|clientservices|"
    r"client\.services|service\.users|user\.support|"
    r"refuge\.referrals|crisis|crisisline|helpline|advice)@",
    re.I
)

# Per-supplier overrides — for cases where neither info@ nor enquiries@ is the
# actual right contact, but we know a better one
KNOWN_BUSINESS_EMAILS = {
    'turning point services':           'info@turning-point.co.uk',
    'certitude':                        'info@certitude.london',
    'voyage 1':                         'info@voyagecare.com',
    'abiding':                          'info@abidingcare.co.uk',
    "solace women's aid":               'info@solacewomensaid.org',
    "solace womens aid":                'info@solacewomensaid.org',
    'centrepoint soho':                 'info@centrepoint.org',
    'depaul':                           'info@depaul.org.uk',
    'thames reach':                     'info@thamesreach.org.uk',
    'single homeless project':          'info@shp.org.uk',
    'choice support':                   'enquiries@choicesupport.org.uk',
    'caysh':                            'info@caysh.org',
    'social interest group':            'enquiries@socialinterestgroup.org.uk',
    'angel housing':                    'admin@angelsupport.co.uk',
    'aurora options':                   'info@auroraoptions.org.uk',
    'brightsky youth services':         'info@brightskyyouthservices.co.uk',
    'cambridge housing society':        'enquiries@chsgroup.org.uk',
    'metropolitan thames valley housing': 'info@mtvh.co.uk',
    'pristine recruitment':             'info@pristinerecruitment.co.uk',
    'profad care agency':               'info@profadcareagency.co.uk',
    'eleanor nursing & social care':    'info@eleanorcare.co.uk',
    'eleanor nursing and social care':  'info@eleanorcare.co.uk',
    'rethink trading':                  'info@rethink.org',
    'caretech community services':      'info@caretech-uk.com',
    'st mungo':                         'info@mungos.org',
    "st mungo's":                       'info@mungos.org',
    'st mungos':                        'info@mungos.org',
    'st mungo community housing association': 'info@mungos.org',
}

def derive_business_email(old_email, supplier_name_lc):
    """Given a client-facing email like referrals@foo.com, return the best
    business equivalent on the same domain."""
    # Direct supplier override?
    if supplier_name_lc in KNOWN_BUSINESS_EMAILS:
        return KNOWN_BUSINESS_EMAILS[supplier_name_lc]
    # Same-domain fallback
    m = re.match(r"^[^@]+@(.+)$", old_email)
    if not m: return old_email
    domain = m.group(1)
    # info@ is the safest generic
    return f"info@{domain}"

wb = openpyxl.load_workbook(MANUAL)
ws_co = wb['Companies']

# Email is column 15 (1-indexed) — confirm
changes = []
for row in ws_co.iter_rows(min_row=2):
    name = str(row[0].value or '').strip()
    email = str(row[14].value or '').strip()
    if not email: continue
    if CLIENT_PREFIXES.match(email):
        new_email = derive_business_email(email, name.lower())
        if new_email and new_email != email:
            changes.append((name, email, new_email))
            row[14].value = new_email

wb.save(MANUAL)

print(f"Swapped {len(changes)} client-facing emails for business contacts:\n")
print(f"  {'SUPPLIER':40s}  {'OLD':40s}  -> NEW")
print('='*120)
for name, old, new in changes:
    print(f"  {name[:38]:40s}  {old[:38]:40s}  -> {new}")
