# Portal scrapers — separate database, never auto-merged

This subsystem **does not touch the main pipeline or the live site directly.**
It scrapes UK procurement portals, normalises results into our column schema,
diffs them against your main + manual data, writes audit CSVs for you to
review, and (for approved rows) appends them to a **SEPARATE curated-scrape
database** that the live build pipeline does NOT load.

## Three tiers of data, strictly separated

| File | Loaded by `build_data.py`? | Contents | Touch policy |
|---|---|---|---|
| `data/care_housing_database_v2_ENRICHED.xlsx` | ✅ Yes | Monthly source workbook | Refreshed once a month from the original source |
| `data/manual_contracts.xlsx` | ✅ Yes | Hand-verified curated contracts (CAS-2/3, AASC, etc.) | Only edited by hand; never auto-populated |
| `data/scraped/curated_scraped.xlsx` | ❌ **No** | Scraper findings the human approved | Auto-populated by `promote_to_manual.py`; reference / review only |

To surface a scraped row on the live site, you must **manually copy it from
`curated_scraped.xlsx` into `manual_contracts.xlsx`**. That deliberate step is
the gate that keeps low-confidence scraped data out of live results.

## The workflow

```
  1. python scripts/scrape_all.py            ─→ data/scraped/raw/*.json
  2. python scripts/normalise.py             ─→ data/scraped/normalised.xlsx
  3. python scripts/filter_scraped.py        ─→ data/scraped/normalised_filtered.xlsx
                                                (apply main-pipeline NONCARE / junk_title filters)
  4. python scripts/dedup_report.py          ─→ data/scraped/audit/{new_*,coverage_gap.md}
  5. Review CSVs in Excel; set scrape_action=APPROVE on rows to keep
  6. python scripts/promote_to_manual.py --from data/scraped/audit/<file>.csv
                                             ─→ data/scraped/curated_scraped.xlsx  (SEPARATE)

  7. (Optional, manual) If you decide a row is high-confidence enough to surface
     on the live site, COPY IT BY HAND from curated_scraped.xlsx into
     manual_contracts.xlsx. THEN:
        npm run data → npm run build → npx vercel deploy --prod
```

The live site never auto-picks-up scraper output. Promotion to curated is
automatic for `APPROVE`-marked rows; promotion to live is always a hand step.

## What each portal looks like and how much patience it needs

| Portal | API type | Search filter? | Rate limit | Estimated run time (2020 → today) |
|---|---|---|---|---|
| **Find-a-Tender** | Bulk OCDS feed | ❌ No — filter client-side | 12 req/min | ~6–10 hours |
| **Contracts Finder** | Search API (POST OCDS) | ✅ Yes — `keyword` + `noticeStatuses=Awarded` | ~60 req/min | ~30–60 minutes |
| **Sell2Wales** | HTML scrape only (stub) | — | unknown | TBD |
| **Public Contracts Scotland** | RSS / search (stub) | — | unknown | TBD |
| **eTendersNI** | HTML scrape (stub) | — | unknown | TBD |
| **Atamis (NHS)** | No public API (stub) | — | unknown | most also on FTS so low priority |

**Important rate-limit reality:** Find-a-Tender is the BIGGEST source by volume,
but its public bulk API is throttled at 12 requests per minute. Each request
returns 100 releases. That's a maximum ~72,000 releases per hour of bulk-feed
pagination. Since 2020 there are several million UK procurement releases in
total — the scraper filters client-side and stops cleanly when it hits the
`--to` date or KeyboardInterrupt, so it's resumable.

**Practical recommendation:** start with Contracts Finder (fast, has search).
Once you've reviewed its output, run Find-a-Tender overnight or in the
background to catch the high-volume tail.

## Usage

```bash
# 1. Run scrapers. Examples:
python scripts/scrape_all.py --only contractsfinder --from 2023-01-01
python scripts/scrape_all.py --only fts --from 2024-01-01 --limit 500   # quick smoke
python scripts/scrape_all.py --from 2020-01-01                          # full run, ALL portals

# 2. Normalise to a single xlsx
python scripts/normalise.py

# 3. Diff against your main + manual data
python scripts/dedup_report.py

# 4. Open in Excel, mark rows APPROVE/SKIP/REJECT in scrape_action column
#    (default = SKIP; only APPROVE rows are promoted)

# 5. Promote
python scripts/promote_to_manual.py --from data/scraped/audit/new_providers.csv
python scripts/promote_to_manual.py --from data/scraped/audit/new_contracts.csv

# 6. Rebuild & deploy
npm run data && npm run build && npx vercel deploy --prod
```

## How the dedup decides "is this already in our data?"

Per the choice you made when designing this system:

- **Exact match** on `norm(company)` AND `norm(council)` → considered the same pair.
- Within an exact-match pair, the **title** is checked at fuzzy 0.85 similarity
  to existing titles for that pair. If the title is novel (e.g. a new framework
  round for an existing relationship), it goes to `potential_duplicates.csv`
  for human review rather than being silently merged.

This is conservative on adding (won't double-count) and liberal on surfacing
(every genuinely-new contract reaches the audit).

## Schema

All scrapers yield dicts with the keys in `scrapers/base.py::CONTRACT_FIELDS`:

  - The first 17 keys are the EXACT column schema of the main workbook's
    `Company × Council × Sector` sheet.
  - The last 5 (`source_portal`, `source_url`, `source_id`, `scraped_at`,
    `cpv_codes`, `contract_value_gbp`, `status`) are audit-trail extras.
    They live in `data/scraped/normalised.xlsx` for provenance but are
    stripped when rows are promoted into `data/manual_contracts.xlsx`.

## What the filter actually keeps (must-housing logic)

A scraped notice is yielded by the scraper ONLY IF:

  - Title matches `HOUSING_TITLE` regex (supported living / accommodation /
    housing related / extra care / HMPPS CAS / NHS supported living etc.)
  - OR CPV codes include a housing CPV (85311000-family, 98341000-family,
    70210000)
  - AND title does NOT match `EXCLUDE_TITLE` exclusions
  - AND CPV is not purely clinical (33xx / 60xx / 72xx prefixes)

These are mirrored from `build_data.py` and centralised in `scrapers/base.py`.

## Adding a new portal

1. Create `scrapers/<name>.py` subclassing `PortalScraper`.
2. Implement `scrape()` yielding normalised dicts (use `empty_row()` then fill).
3. Register it in `scripts/scrape_all.py::ALL_SCRAPERS`.
4. Run `python scripts/scrape_all.py --only <name>` to test.

## Why this is a separate database, not direct merge

- **Provenance** — every scraped row carries the source URL forever
- **Quality gate** — humans approve before users see anything
- **Resumable** — partial runs don't corrupt main data
- **Audit** — when something looks wrong months later, you can see exactly
  which scrape contributed which row
- **Idempotent monthly refresh** — re-running the scrapers doesn't double-count;
  the dedup catches it

## Honest limitations

1. Find-a-Tender's lack of search API means full historical runs take hours.
2. Atamis (NHS), Sell2Wales, PCS, NI are STUBS — they'll silently yield zero
   rows until someone implements them.
3. The CPV-code filter is good but not perfect — some genuine housing contracts
   carry no CPV. Title is the fallback.
4. The buyer-name → `Commissioner Type` classifier is heuristic; the dedup
   keeps the resolver in `build_data.py` as the final authority.
