# DATA UPDATE — refreshed enriched database (2026-06-01)

The enrichment session finished. `data/care_housing_database_v2_ENRICHED.xlsx` has been
**replaced with the final, corrected version**. Re-run the data build to pick it up:

```
python build_data.py
```

## What changed in the Companies tab
New / updated columns (all 5,814 companies):

| Column | Notes |
|--------|-------|
| Address, Website, Telephone | from Google Maps + corrections |
| **Email** | 3,801 filled (65%). Generic inboxes preferred (info@, enquiries@). |
| **Contact Page** | clickable contact-form URL for companies with no email |
| **Charity Number / Charity Income (GBP) / Charity Status / Charity Activities** | 294 charity matches (Companies-House-number + name-verified) |
| **Website Review** | `needs review` = website couldn't be confidently matched to the company (165 rows). Treat its Website/Contact Page as low-confidence. |

## New CSVs in data/
- `verified_leads.csv` — clean outreach list (5,621 rows). Has a `website_verified` column; the 165 low-confidence ones are excluded from contact links here.
- `needs_review.csv` — the 165 isolated companies to revisit later (website still unverified).

## Coverage
- Email: 3,801 / 5,814 (65%)
- Reachable (email **or** a verified contact link): 5,688 (97.8%)
- Flagged `needs review` (isolated): 165

## Recommended for the site
- Show **Email** where present; fall back to **Contact Page** link otherwise.
- For rows where `Website Review = needs review`, either hide the website/contact or badge it "unverified".
- Charity Income/Status/Activities are good for provider detail pages (only ~294 have them — render conditionally).
