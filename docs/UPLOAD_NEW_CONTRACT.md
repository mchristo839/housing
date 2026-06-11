# Uploading a New Contract Award

This is the one-command workflow for adding a new contract notice to the database.
It handles every step — parsing, deduplication, contact verification, and deployment.

## The command

```powershell
python scripts/ingest_contract.py "C:\path\to\notice.csv"
```

To also push live immediately:
```powershell
python scripts/ingest_contract.py "C:\path\to\notice.csv" --deploy
```

To skip the Firecrawl verification step (faster, used for testing):
```powershell
python scripts/ingest_contract.py "C:\path\to\notice.csv" --no-verify
```

## What it does, stage by stage

| Stage | Action |
|---|---|
| **1. PARSE** | Reads the CSV. Filters down to housing-related notices only. |
| **2. CHECK** | For every (supplier × council) pair, looks up if we already have it. |
| **3. CLASSIFY** | Buckets into three groups: already-known / new-link-to-existing-supplier / brand-new-supplier. |
| **4. WRITE** | Appends new entries to `data/manual_contracts.xlsx` (Companies sheet + CCS sheet). |
| **5. VERIFY** | For brand-new suppliers ONLY, runs Firecrawl `/search` to find their website, then `/extract` to confirm services + grab contacts. |
| **6. APPLY** | Promotes Firecrawl KEEPs to Verified, adds DROPs to the drop list. |
| **7. BUILD** | Regenerates `providers.json` with the new entries + verification flags. |
| **8. DEPLOY** | (Only with `--deploy`) Pushes to https://findahousingprovider.vercel.app |

## Supplier-name skip filter

The ingest also strips supplier names that are **individual facilities** rather
than operating companies. We want the parent operator (which may own dozens of
care homes), NOT each individual facility as a separate provider.

Currently skipped at parse time:
- Any supplier name containing **"care home"** (e.g. "Wollaton View Care Home")
- Any supplier name containing **"nursing home"**

This is controlled by `SKIP_SUPPLIER_PATTERNS` in `scripts/ingest_contract.py`.
To extend (e.g. to skip "lodge" or "manor" patterns), edit that list.

## Housing-notice filter (June 2026 update)

The `is_housing_notice()` function decides which CSV rows reach the verifier.
The June 2026 expansion fixed a major gap — old filter caught only ~50% of
housing-related notices because it required terms like "supported living"
in the title. The new filter looks at both **title and description** and
accepts a much wider vocabulary:

**Now caught as housing:**
- residential care / residential home / residential bed
- care home / nursing home / care and nursing
- housing related / housing support / housing & support
- floating support / tenancy support
- looked after / children's home
- ageing well / DPS for care / care and support
- assessment beds / short-term assessment
- refuges / domestic abuse / modern slavery
- day services (often bundled with supported living)
- substance misuse (often includes housing-related support)

**Explicitly excluded as non-housing:**
- telecare / telehealth / lifeline / community alarm (assistive tech only)
- transport / vehicle hire / fuel cards
- stationery / office supplies / IT services / broadband
- audit / legal / insurance / banking
- civil engineering / highways / roofing / lift maintenance

**Validation:** When re-running the 7 source CSVs after the expansion, the
new filter caught **+100 housing notices per CSV** that the old one missed
(e.g. notices(23) went from 155 → 255 housing notices kept, with all 100
extra clearly housing — residential care, looked-after, ageing well, etc.).

If you notice a CSV producing fewer than ~50% housing notices after parsing,
the filter may need another term added. Check the `is_housing_notice()`
function in `scripts/ingest_contract.py`.

## Batch-of-N processing for very large CSVs

For CSVs producing 1,000+ truly-new suppliers, use the batched runner:

```powershell
python scripts/firecrawl_lookup_batched.py data/verification/need_firecrawl.json 750
```

It processes 750 names at a time, then runs apply+rebuild+deploy after each
batch. So if Firecrawl credits run out part-way, you still get the partial
results live. Safer for big runs than the one-shot script.

## What format the CSV needs

Standard Contracts Finder export. Required columns:

- `Notice Identifier`
- `Title`
- `Organisation Name` (the buyer/council)
- `Region`
- `Awarded Date`
- `Awarded Value`
- `Description`
- `Supplier [Name|Address|Ref type|Ref Number|Is SME|Is VCSE]`

That's the exact format you've been downloading from
[contractsfinder.service.gov.uk](https://www.contractsfinder.service.gov.uk/Search).

## Typical session

You download a CSV after the monthly procurement report drops:

```powershell
# Pretend your CSV is in Downloads
python scripts/ingest_contract.py "C:\Users\paul_\Downloads\notices_july.csv" --deploy
```

Output looks like:

```
=== STAGE 1: PARSE — C:\Users\paul_\Downloads\notices_july.csv ===
  Read 412 rows from .../notices_july.csv
  Kept 187 housing notices, skipped 225 non-housing

=== STAGE 2-3: CHECK + CLASSIFY ===
  Classification:
    Already in DB (supplier+council):    143
    New council link to known supplier:   62
    Brand new supplier:                   12

=== STAGE 4: WRITE to manual_contracts.xlsx ===
  Wrote: 12 new Companies rows, 74 CCS rows

=== STAGE 5: VERIFY new suppliers (Firecrawl) ===
  Running Firecrawl on 12 new suppliers...
  [  1/12] KEEP            Foo Care Ltd  -> https://foocare.co.uk/
  [  2/12] KEEP            Bar Support Services  -> https://barsupport.org/
  ...

=== STAGE 6-7: APPLY verdicts + REBUILD ===
  VERIFIED:  +10  (total 1629)
  DROPS:     +1   (total 164)

=== STAGE 8: DEPLOY ===
  ▲ Aliased  https://findahousingprovider.vercel.app

=== DONE ===
  Total providers: 1662  (1629 Verified)
  New suppliers added: 12
  New council links:   62
  Already on file:     143
```

## Cost per upload

- New suppliers per month: typically 50-150 across all council CSVs
- Firecrawl `/search` + `/extract`: ~15 credits per new supplier
- Monthly Firecrawl cost: **50-150 × 15 = 750-2,250 credits**
- Fits comfortably in the **Hobby plan ($19/mo, 3,000 credits)** after the initial big run

## Safety net

- Every stage prints what it's doing — you can stop at any point with Ctrl+C
- New entries are written to `manual_contracts.xlsx` only — your original source data
  is never touched
- Firecrawl results cache in `firecrawl_analysed.json`, so re-running won't double-spend
  credits on the same supplier
- The file `MANUAL_DROP_LIST.json` persists, so any confirmed-bad supplier you've already
  flagged won't be re-added by accident

## If something goes wrong

| Problem | Fix |
|---|---|
| "Permission denied" on `manual_contracts.xlsx` | Close the file in Excel first |
| Firecrawl 402 Payment Required | You hit the credit ceiling — upgrade plan or wait until next billing cycle |
| Wrong council assigned | The CSV's `Organisation Name` was a procurement portal — add it to `PORTAL_ORG_MAP` in the script |
| New supplier ends up Listed instead of Verified | Firecrawl couldn't find their site by name — search manually + edit `manual_contracts.xlsx` Companies row 13 (Website) |
