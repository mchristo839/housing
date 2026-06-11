# Data Verification Process

This document is the runbook for the data quality process behind
findahousingprovider.vercel.app. The site charges customers £29.99 for postcode-level
provider data, so accuracy must be defensible.

## Three quality tiers

Every provider in the database sits in one of three tiers. Customers see the tier on
every result so they know what they're paying for.

| Tier | Badge on UI | What it means |
|---|---|---|
| **Verified** | ✅ Verified | Passed the 4-step verification check below. Website confirmed to match the limited-company name. Housing service confirmed. Contacts verified (or contact-us page captured). |
| **Listed** | 📋 Listed | On a government framework contract (Contracts Finder / Find a Tender) but not yet manually verified. Source-data contact details are shown but flagged as unverified. |
| **Confirmed-bad** | _(hidden)_ | Verified to be an unrelated business (vet, pizza takeaway, building company etc.) Permanently filtered out of results. Lives in `data/MANUAL_DROP_LIST.json`. |

## The 4-step verification check

Run for every provider before they move from **Listed** → **Verified**.

### Step 1 — Website ownership

Fetch the website attached to the provider in source data and confirm the limited-
company name appears somewhere on the homepage / about / footer / contact page.

- ✓ Match → go to **Step 3**
- ✗ No match → go to **Step 2**

### Step 2 — Find the real website

Web-search:
```
"[Company Name Limited]" supported living OR assisted living
OR asylum OR homelessness OR supported accommodation
```

The right result will have a URL containing the company keyword AND a page that
mentions the company name. Update the stored website to the real URL.

If no result is found, mark **UNCLEAR** — provider stays as **Listed** awaiting human
review (not dropped — false drops cost ideal clients).

### Step 3 — Service confirmation

Confirm the verified website offers at least one of:

- Supported living
- Assisted living
- Supported accommodation
- Extra care
- Residential care / care home / nursing home
- Asylum accommodation
- Homelessness / refuge / hostel
- Sheltered housing
- Care for young people / care leavers / 16+
- Mental-health accommodation
- Semi-independent / transitional accommodation
- Domestic-abuse / women's refuge / family accommodation

**Mixed providers count** — many companies start as homecare and expand into
supported living. If supported living is mentioned anywhere on the site (even
as a secondary service), keep them.

- ✓ Service confirmed → **KEEP** + write contacts (Step 4)
- ✗ No housing service AND no contracts-finder link → **DROP**

### Step 4 — Contact details

For each verified provider capture:

- **Website** (the verified one from Step 1/2)
- **Phone** (from the homepage / contact page)
- **Email** — if not visible, capture the **/contact-us URL**
- **Address** (registered office or operating address)

Write all four to `data/manual_contracts.xlsx` → `Companies` sheet. They will
survive every monthly source refresh.

## Files in the verification system

| File | Purpose | Lives in repo? |
|---|---|---|
| `data/verification/VERIFIED.json` | Provider names confirmed Verified + verification date | Yes |
| `data/scraped/VERIFICATION_V2_QUEUE.csv` | Queue of providers awaiting verification | Yes |
| `data/scraped/VERIFICATION_V2_RESULTS.csv` | Audit trail of every Step-1/2/3/4 result | Yes |
| `data/MANUAL_DROP_LIST.json` | Confirmed-bad businesses (permanent ban) | Yes |
| `data/manual_contracts.xlsx` → Companies | Verified website/phone/email/address per company | Yes |

## Scripts

| Script | What it does |
|---|---|
| `python scripts/verify_provider_v2.py queue` | Generate the current verification queue |
| `python scripts/verify_provider_v2.py status` | Show progress (Verified vs Listed vs Drop) |
| `python scripts/verify_provider_v2.py apply` | Apply pending verdicts to drop list + Companies sheet |
| `python scripts/record_v2_result.py <args>` | Record one verification result |
| `python build_data.py` | Rebuild providers.json with current verification status attached |

## Monthly refresh workflow

The source data (`care_housing_database_v2_ENRICHED.xlsx`) gets refreshed monthly
from CCS and Contracts Finder.

1. Drop in the new source file
2. Run `python build_data.py` — produces the new `providers.json` with all
   existing verifications carried over
3. Run `python scripts/verify_provider_v2.py queue` — generates a NEW queue of just
   the newly-appeared providers
4. Work through verification of new providers (typically 50-100/month)
5. Run `python scripts/verify_provider_v2.py apply` to lock in verdicts
6. `npm run build && vercel deploy --prod --yes`

## Trust & messaging

Customers see on every result page:

- **Top of result page**: "_All verified providers passed our 4-step check:
  website ownership, service confirmation, and contact verification._"
- **Per-provider card**: Verified ✅ badge OR Listed 📋 chip
- **Filter toggle**: "Show verified providers only" (off by default — shows both,
  but Verified always sort above Listed)

## Customer guarantee

Because the data is paid for, the page commits to:

- Refund within 14 days if **any verified provider's** website is incorrect at
  time of viewing
- Continuous re-verification — verified providers are re-checked every 90 days
- Customer-flagged corrections fixed within 5 working days

## Automated verification pipeline

In addition to the manual 4-step check, two automated sources do most of
the work at scale.

### Companies House API (free, authoritative)

For every provider, we look up the UK limited company and capture:

- Company number
- **Active / Dissolved status** — dissolved companies are auto-dropped
- **SIC industry codes** — which categorise the business. Housing-relevant
  codes include 87100/87200/87300/87900 (residential care), 88100/88990
  (social work), 68201 (housing association real estate), 41100 (building
  development).
- Registered office address
- Date of incorporation

Setup: free key from https://developer.company-information.service.gov.uk/
then `python scripts/companies_house_lookup.py`.

Output: `data/verification/companies_house.json`

### Apify bulk web scraper

A single Apify Cheerio Scraper job hits all ~1,800 provider websites in
parallel and extracts:

- Page text + page title
- Emails, phone numbers, contact-page URL
- Whether the limited-company name appears on the page
- Which housing keywords appear (supported living, care home, refuge…)
- Whether any clearly-non-housing terms appear (pizza, vet, plumbing…)

Setup: token from https://apify.com then
```
python scripts/apify_verify.py submit
python scripts/apify_verify.py fetch <runId>
python scripts/apify_verify.py analyse
```

Output: `data/verification/apify_analysed.json`. Cost: ~$1-2 per full run.

### Auto-promote

`python scripts/auto_verify.py` reads both sources and promotes providers
to **Verified** when ALL of:

1. Companies House status = active
2. SIC code matches housing/care category
3. Apify confirms website mentions the company name
4. Apify confirms website mentions at least one housing keyword
5. Apify captured at least one contact channel (email/phone/contact-page)

It auto-drops only when:

- CH says dissolved/liquidated, OR
- SIC is in a clearly-non-housing category AND site has a clearly-non-housing
  term AND no housing keyword

Anything else stays "Listed" — humans review the edge cases.

### Full automated refresh — total flow

```
# 1. New source data drops in (monthly)
python build_data.py

# 2. Companies House lookup on NEW providers only
python scripts/companies_house_lookup.py

# 3. Apify bulk scrape on all providers (catches website changes too)
python scripts/apify_verify.py submit
# ...wait for run to finish (~5-10 min for 1800 sites)
python scripts/apify_verify.py fetch <runId>
python scripts/apify_verify.py analyse

# 4. Auto-promote anyone the two sources both confirm
python scripts/auto_verify.py preview     # see what would change
python scripts/auto_verify.py             # apply

# 5. Rebuild + deploy
python build_data.py && npm run build && vercel deploy --prod --yes
```

## Roadmap

- [x] 4-step verification process defined
- [x] Persistent CSV + JSON storage of verification verdicts
- [x] Per-provider verification tier attached to providers.json
- [x] UI badge for Verified vs Listed
- [x] Quality filter toggle on results page ("Verified only")
- [x] Trust banner on results page
- [x] Companies House API integration
- [x] Apify bulk scraper integration
- [x] Auto-promote pipeline
- [ ] Refund flow if verified provider's data is wrong
- [ ] 90-day re-verification cron
- [ ] Customer correction submission form
