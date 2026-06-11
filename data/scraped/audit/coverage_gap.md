# Scrape coverage gap report

Scraped rows reviewed: **51**.

## What I found

| Bucket | Rows | What to do |
|---|---:|---|
| New providers (never seen) | 39 across 35 companies | Review `new_providers.csv`, then promote |
| New contracts (existing provider, new council/region) | 3 | Review `new_contracts.csv`, then promote |
| Possible new awards on existing pairs | 0 | Review `potential_duplicates.csv` — likely a re-tender of an existing framework |

## Top 20 new providers by row count

| Provider | Scraped rows | Sample council |
|---|---:|---|
| Wybone Limited | 2 | Swale Borough Council |
| Phoenix Lodge Coventry Limited | 2 | COVENTRY CITY COUNCIL |
| Tunstall Healthcare (UK) Ltd | 2 | NORTHERN HOUSING CONSORTIUM LIMITED |
| Warmpro Insulation Specialists Ltd | 2 | Tuntum Housing Association |
| WARD HADAWAY LLP | 1 | WEST MIDLANDS COMBINED AUTHORITY |
| ANTHONY COLLINS LIMITED | 1 | WEST MIDLANDS COMBINED AUTHORITY |
| Eddisons | 1 | Homes England (the name adopted by the H |
| Walker Morris | 1 | Homes England (the name adopted by the H |
| Lambert Smith Hampton Group Limited | 1 | Amplius Living |
| Queen Alexandra College | 1 | EAST RIDING OF YORKSHIRE COUNCIL |
| allpay Ltd | 1 | NORTHERN HOUSING CONSORTIUM LIMITED |
| Locata Housing Services Limited | 1 | Bath and North East Somerset Council |
| Deloitte LLP | 1 | The Insolvency Service |
| Ridge and Partners LLP | 1 | Liverpool City Council |
| Taking Care Personal Alarms Ltd | 1 | NORTHERN HOUSING CONSORTIUM LIMITED |
| Eurocell Building Plastics Ltd | 1 | NOTTINGHAM CITY COUNCIL |
| Hampshire Partitioning Contracts Ltd (TA HP Contracts) | 1 | Hampshire County Council |
| Safe Families for Children | 1 | DERBY CITY COUNCIL |
| RAPLEYS LIMITED LIABILITY PARTNERSHIP | 1 | Places for People Group Limited |
| Premier Modular Limited | 1 | Countess of Chester Hospital NHS Foundat |

## Recommended next step

```
python scripts/promote_to_manual.py --from data/scraped/audit/new_providers.csv
```
