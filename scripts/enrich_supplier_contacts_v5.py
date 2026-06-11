"""Round 4-5 consolidated enrichment — name + care-type search across all
remaining via-commissioner suppliers."""
import openpyxl, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

XLSX = 'data/manual_contracts.xlsx'

ADDITIONS = {
    # Round 4-5 finds
    'alwdo assist': ('https://alwdoassist.co.uk', '0208 064 1911', 'info@alwdoassist.co.uk',
        'https://alwdoassist.co.uk/contact-us/', '', ''),
    'best choice global': ('https://bestchoiceglobal.co.uk', '0203 7457072', 'info@bestchoiceglobal.co.uk',
        'https://bestchoiceglobal.co.uk/contact-us', '', ''),
    'care solutions group': ('https://care-solutionsgroup.com', '', 'info@care-solutionsgroup.com',
        'https://care-solutionsgroup.com/contact', '13850828', ''),
    'carebridge healthcare': ('https://carebridgelimited.co.uk', '07861 701164', 'info@carebridgelimited.co.uk',
        'https://carebridgelimited.co.uk/contact', '', ''),
    'chinite resourcing': ('https://www.chiniteresourcing.com', '01376 433917', 'info@chiniteresourcing.com',
        'https://www.chiniteresourcing.com/contact', '06783750', ''),
    'delphinus healthcare': ('https://www.delphinushealthcare.com', '', 'info@delphinushealthcare.com',
        'https://www.delphinushealthcare.com/contact', '13281676', ''),
    'ejc group': ('https://www.ejcmanagement.co.uk', '07957 723273', 'emma@ejcmanagement.co.uk',
        'https://www.ejcmanagement.co.uk/contact/', '09446033', ''),
    'elite careplus': ('https://elitecareplus.co.uk', '020 7998 7860', 'info@elitecareplus.co.uk',
        'https://elitecareplus.co.uk/contact-us/', '', ''),
    'elliot leigh tlc': ('https://www.elliotleigh.com/tlc', '020 8514 6611', 'tlc@elliotleigh.com',
        'https://www.elliotleigh.com/tlc/contact', '', ''),
    'elysian field': ('https://elysian-field.co.uk', '0121 607 1946', 'hello@elysian-field.co.uk',
        'https://www.elysian-field.co.uk/Contact us.html', '06928301', ''),
    'everyone everywhere care services': ('https://everyoneeverywhere.co.uk', '', 'info@everyoneeverywhere.co.uk',
        'https://everyoneeverywhere.co.uk/contact', '11166716', ''),
    'found8tions youth support services': ('https://www.foundationsyss.co.uk', '0208 058 7055',
        'info@foundationsyss.co.uk', 'https://www.foundationsyss.co.uk/contact', '12809853', ''),
    'fresh start care services': ('https://www.freshstartcare.com', '', 'info@freshstartcare.com',
        'https://www.freshstartcare.com/contact', '', ''),
    'genesis living': ('https://genesisliving.co.uk', '01926 882 211', 'info@genesisliving.co.uk',
        'https://genesisliving.co.uk/contact', '', ''),
    'go ahead homes': ('https://goaheadhomes.com', '0208 144 8888', 'info@goaheadhomes.com',
        'https://goaheadhomes.com/contact/', '11319451', ''),
    'hamletts': ('https://www.hamletts.com', '020 7791 0044', 'info@hamletts.com',
        'https://www.hamletts.com/contactus', '', ''),
    'hillside care services cic': ('https://hillsidecare.co.uk', '0121 554 3909', 'info@hillsidecare.co.uk',
        'https://hillsidecare.co.uk/contact', '', ''),
    'honey crown bee': ('https://honeycrownbee.co.uk', '0795 1000 678', 'info@honeycrownbee.co.uk',
        'https://honeycrownbee.co.uk/contact', '', ''),
    'hope superjobs': ('https://hopesuperjobs.co.uk', '020 8514 6611', 'info@hopesuperjobs.co.uk',
        'https://hopesuperjobs.co.uk/contact-us/', '', ''),
    'immediate social care': ('https://www.immediatesocialcare.co.uk', '0208 412 0929',
        'info@immediatesocialcare.co.uk', 'https://www.immediatesocialcare.co.uk/contact', '', ''),
    'impeccable healthcare services': ('https://www.impeccablehealthcare.co.uk', '0208 609 6686',
        'info@impeccablehealthcare.co.uk', 'https://www.impeccablehealthcare.co.uk/contact/', '', ''),
    'inspiration support services': ('https://www.inspirationss.co.uk', '', 'info@inspirationss.co.uk',
        'https://www.inspirationss.co.uk/contact', '', ''),
    'itrust agency': ('https://itrustcareservices.com', '01582 522302', 'info@itrustcareservices.com',
        'https://itrustcareservices.com/contact', '10144796', ''),
    'jakaranda care': ('https://www.jakarandacare.co.uk', '07555 189197', 'info@jakarandacare.co.uk',
        'https://www.jakarandacare.co.uk/contact', '', ''),
    'jakky care group': ('https://www.jakkycaregroup.co.uk', '07546 334450', 'enquiries@jakkycaregroup.co.uk',
        'https://www.jakkycaregroup.co.uk/contact', '12593302', ''),
    'jem support services': ('https://www.jem.services', '020 3633 1011', 'info@jem.services',
        'https://www.jem.services/about', '11235635', ''),
    'kempshire': ('https://kempshire.co.uk', '01480 411 100', 'info@kempshire.co.uk',
        'https://kempshire.co.uk/contact', '12787041', ''),
    'lifecome': ('https://lifecomecare.co.uk', '020 3441 1810', 'info@lifecomecare.co.uk',
        'https://lifecomecare.co.uk/contact', '', ''),
    'lilibet court care': ('https://www.lillibethealthcare.co.uk', '01234 851 119', 'info@lillibethealthcare.co.uk',
        'https://www.lillibethealthcare.co.uk/contact', '', ''),
    'living spring solutions care & training':
        ('https://www.livingspringsolutions.co.uk', '020 3417 0405', 'info@livingspringsolutions.co.uk',
         'https://www.livingspringsolutions.co.uk/contact/', '08568069', ''),
    'living waters services':
        ('https://www.livingwatersltd.co.uk', '024 7518 6190', 'admin@livingwatersltd.co.uk',
         'https://www.livingwatersltd.co.uk/contact', '', ''),
    'mmr homecare': ('https://www.mmrhomecare.co.uk', '020 8965 9317', 'info@mmrhomecare.co.uk',
        'https://www.mmrhomecare.co.uk/contact', '', ''),
    'mega resources': ('https://www.megaresources.co.uk', '01536 524205', 'info@megaresources.co.uk',
        'https://www.megaresources.co.uk/contact', '', ''),
    'newhaven 16 plus': ('https://newhaven16plus.co.uk', '020 8504 1000', 'info@newhaven16plus.co.uk',
        'https://newhaven16plus.co.uk/contact', '', ''),
    'next step care management': ('http://www.nscm.co.uk', '01737 365 060', 'info@nscm.co.uk',
        'http://www.nscm.co.uk/contact', '', ''),
    'novo healthcare': ('https://www.novohealthcare.co.uk', '0113 518 3790', 'info@novohealthcare.co.uk',
        'https://novohealthcare.co.uk/contact-us/', '', ''),
    'path4you': ('https://path4you.co.uk', '0203 633 9939', 'info@path4you.co.uk',
        'https://path4you.co.uk/contact', '', ''),
    'pmse london': ('https://pmselondonltd.com', '01895 437 760', 'info@pmselondonltd.com',
        'https://pmselondonltd.com/pages/support/contact-us', '12461747', ''),
    'potensial': ('https://potens-uk.com', '0344 326 1100', 'info@potens-uk.com',
        'https://potens-uk.com/contact-us/', '', ''),
    'priory care services': ('https://priorycareservices.com', '020 8688 8800',
        'enquiries@priorycareservices.com', 'https://priorycareservices.com/contact', '', ''),
    'pristine recruitment': ('https://www.pristinerecruitment.co.uk', '020 8446 2209',
        'care@pristinerecruitment.co.uk', 'https://www.pristinerecruitment.co.uk/contact-home-elder-healthcare-carers-london.aspx', '', ''),
    'promises of care': ('https://promisesofcare.co.uk', '01902 587 099', 'info@promisesofcare.co.uk',
        'https://promisesofcare.co.uk/contact-us', '', ''),
    'providence linc united services': ('https://www.plus-uk.org', '020 8297 1250', 'info@plus-uk.org',
        'https://www.plus-uk.org/contact', '02782712', '1031595'),
    'quality care surrey': ('https://www.surreyqualitycare.uk', '01737 906 555', 'info@surreyqualitycare.uk',
        'https://www.surreyqualitycare.uk/contact.html', '', ''),
    'quaywest housing': ('https://quaywestgroup.co.uk', '01926 800 800', 'info@quaywestgroup.co.uk',
        'https://quaywestgroup.co.uk/contact', '09910262', ''),
    'raisso house': ('https://raissohouse.co.uk', '024 7748 8800', 'info@raissohouse.co.uk',
        'https://raissohouse.co.uk/index.php/about/', '', ''),
    'rapha healthcare': ('https://www.raphahealthcare.co.uk', '01753 382 278', 'hello@raphasanctuary.co.uk',
        'https://www.raphahealthcare.co.uk/contact', '', ''),
    'respect care services': ('https://www.respectcare.co.uk', '020 8964 2167', 'info@respectcare.co.uk',
        'http://www.respectcare.co.uk/index.php/contact-us/', '', ''),
    'rethink trading': ('https://www.rethink.org', '0121 522 7007', 'info@rethink.org',
        'https://www.rethink.org/aboutus/who-we-are/contact-us/', '', '271028'),
    'sans soucie home care': ('https://sanssouciehomecare.com', '01483 233 925', 'info@sanssouciehomecare.com',
        'https://sanssouciehomecare.com/contact', '07288457', ''),
    'seven care services': ('https://www.sevencareservices.org', '024 7610 4710', 'info@sevencareservices.org',
        'https://www.sevencareservices.org/contact', '13119584', ''),
    'sgsl': ('https://nsslgroup.co.uk', '01992 367246', 'info@nsslgroup.co.uk',
        'https://nsslgroup.co.uk/contact', '', ''),
    'silver birch': ('https://silverbirchcare.com', '020 8848 1800', 'placements@silverbirchcare.com',
        'https://silverbirchcare.com/contact-us/', '', ''),
    'sixteen plus': ('https://www.sixteenplus.co.uk', '01702 555 466', 'info@sixteenplus.co.uk',
        'https://www.sixteenplus.co.uk/contact', '', ''),
    'southside partnership certitude': ('https://certitude.london', '020 8772 6222', 'info@certitude.london',
        'https://certitude.london/contact-us', '', ''),
    'soithside partnership certitude': ('https://certitude.london', '020 8772 6222', 'info@certitude.london',
        'https://certitude.london/contact-us', '', ''),
    'starlight support services': ('https://www.starlightsupportservices.co.uk', '0121 421 1900',
        'info@starlightsupportservices.co.uk',
        'https://www.starlightsupportservices.co.uk/contact', '', ''),
    'sunderland home care associates 20 20': ('https://www.sunderlandhomecare.co.uk', '0191 510 8366',
        'info@sunderlandhomecare.co.uk', 'https://www.sunderlandhomecare.co.uk/contact', '03564689', ''),
    'sunset rehabiltation healthcare centre':
        ('https://www.sunsetrehabilitation.co.uk', '020 8949 3939', 'info@sunsetrehabilitation.co.uk',
         'https://www.sunsetrehabilitation.co.uk/contact', '13861024', ''),
    'supporting young futures': ('https://syf.org.uk', '020 8989 0900', 'info@syf.org.uk',
        'https://syf.org.uk/contact', '', ''),
    'tbn people support': ('https://tbnpeoplesupport.co.uk', '01603 419 419', 'info@tbnpeoplesupport.co.uk',
        'https://tbnpeoplesupport.co.uk/contact/', '12163121', ''),
    'tbtt direct': ('', '07860 378196', '', '', '07911622', ''),
    'three cs support': ('https://www.threecs.co.uk', '020 8269 4340', 'info@threecs.co.uk',
        'https://www.threecs.co.uk/contact', '02768427', ''),
    'thw way care services': ('http://www.thewaycareservices.co.uk', '0845 259 0216',
        'info@thewaycareservices.co.uk', 'http://www.thewaycareservices.co.uk/contact', '', ''),
    'transforming lives':
        ('https://www.changinglives.org.uk', '0191 273 8891', 'info@changinglives.org.uk',
         'https://www.changinglives.org.uk/contact-us', '', '1141167'),
    'transition care peterborough':
        ('https://transitioncare.org.uk', '0151 949 0156', 'info@transitioncare.org.uk',
         'https://transitioncare.org.uk/contact-us/', '', ''),
    'trends healthcare': ('https://trendshealthcare.co.uk', '07939 865 365', 'info@trendshealthcare.co.uk',
        'https://trendshealthcare.co.uk/contact', '', ''),
    'tropical care': ('https://www.tropicalcare.uk', '020 8773 4470', 'info@tropicalcare.uk',
        'https://www.tropicalcare.uk/contact/', '', ''),
    'uk care partnership': ('https://www.ukcarepartnership.com', '01502 732658', 'info@ukcarepartnership.com',
        'http://www.ukcarepartnership.com/contact.html', '', ''),
    'verity group': ('https://veritygroup.uk', '01249 715 800', 'info@veritygroup.uk',
        'https://veritygroup.uk/contact/', '', ''),
    'vineyard homes': ('https://vineyardhomeslimited.co.uk', '0845 260 0566', 'info@vineyardhomeslimited.co.uk',
        'http://vineyardhomeslimited.co.uk/contact-us/', '10771883', ''),
    'young roots care services': ('http://youngroots.co.uk', '0208 281 7915', 'info@youngroots.co.uk',
        'http://youngroots.co.uk/contact', '10056012', ''),
    'your absolute care': ('https://www.yourabsolutecare.co.uk', '01733 802 444', 'info@yourabsolutecare.co.uk',
        'https://www.yourabsolutecare.co.uk/contact', '', ''),
    'zachs care': ('https://www.zachcareltd.com', '01525 306740', 'info@zachcareltd.com',
        'https://www.zachcareltd.com/our-services', '12521358', ''),
    # Council-managed entities (route to council)
    'harrow council rough sleeping (housing first)':
        ('https://www.harrow.gov.uk/housing/help-rough-sleepers', '020 8901 2680',
         'rough.sleeping@harrow.gov.uk', 'https://www.harrow.gov.uk/contact', '', ''),
    'homes for wandsworth':
        ('https://www.wandsworth.gov.uk/housing', '020 8871 6000', 'housing@wandsworth.gov.uk',
         'https://www.wandsworth.gov.uk/contact', '', ''),
    'lewisham learning disabilities framework (open, suppliers tbd)':
        ('https://lewisham.gov.uk/myservices/socialcare/adult/disability-support',
         '020 8314 6000', 'adultsocialcare@lewisham.gov.uk',
         'https://www.lewisham.gov.uk/contact-us', '', ''),
    'university college london hospitals nhs trust':
        ('https://www.uclh.nhs.uk', '020 3456 7890', 'communications@uclh.nhs.uk',
         'https://www.uclh.nhs.uk/contact-us', '', ''),
}

wb = openpyxl.load_workbook(XLSX)
ws_co = wb['Companies']

updated = 0
for row in ws_co.iter_rows(min_row=2):
    name = str(row[0].value or '').strip()
    if not name: continue
    key = name.lower()
    if key not in ADDITIONS: continue
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
print(f"Updated {updated} suppliers in this round")
