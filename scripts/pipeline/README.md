# Data refresh pipeline

Keeps the database growing and gives existing customers a reason to stay
subscribed: every fortnight we pull new awards from the procurement portals,
and every month we tell each customer what has appeared in the areas they pay
for.

Nothing reaches a customer without someone approving it. The data lands in a
pull request; the emails land in a pull request and then need a button press.

## The four steps

| Step | Script | What it does |
|---|---|---|
| 1 | `harvest.py` | Pulls the portals, keeps the housing awards made by real councils, drops suppliers we already hold, writes `data/harvest/candidates_<date>.csv` |
| 2 | `ingest.py` | Folds that CSV into `providers.json`, `db.json`, `councilmap.json` and the first-seen ledger |
| 3 | `whats_new.py` | Diffs the ledger, reports new providers by council, drafts one email per customer |
| 4 | `send.py` | Sends approved drafts. Never scheduled, dry-runs by default |

Run them by hand in the same order:

```
python3 scripts/pipeline/harvest.py --days 60
python3 scripts/pipeline/ingest.py
node scripts/build_stats.mjs
python3 scripts/pipeline/whats_new.py --min-new 3
python3 scripts/pipeline/send.py --date YYYY-MM-DD          # dry run
python3 scripts/pipeline/send.py --date YYYY-MM-DD --send   # for real
```

Steps 1 and 2 are idempotent: running them twice over the same awards creates
no duplicate providers and no duplicate contracts.

## On a schedule

| Workflow | When | Result |
|---|---|---|
| `data-refresh.yml` | Every other Monday, 06:00 UTC | Draft PR with the new providers |
| `customer-update.yml` | 1st of the month, 08:00 UTC | Draft PR with the per-customer email drafts |
| `send-customer-update.yml` | Manual only | Sends the approved drafts |

The fortnightly cadence is a weekly cron that exits on odd ISO weeks, because
GitHub cron has no "every two weeks". Both scheduled workflows also take a
manual run, and `data-refresh` has a `force` input for an off week.

## Secrets

| Secret | Needed by | Without it |
|---|---|---|
| `SITE_URL` | customer-update | Area report still runs; no per-customer drafts |
| `ADMIN_TOKEN` | customer-update | Same |
| `BREVO_API_KEY` | send | Refuses to send |
| `AFFILIATE_FROM_EMAIL` | send | Falls back to `hello@findahousingprovider.co.uk` |

`GITHUB_TOKEN` is provided automatically and is what opens the PRs.

## The ledger

`data/provider_ledger.json` maps a provider id to the date we first saw it.
It is what makes "12 new providers in Havering since last month" a fact rather
than a guess. Providers that predate the ledger carry a `2000-01-01` baseline
so the first run does not announce the whole database as new.

Do not delete it. Rebuilding it would date every provider to the rebuild and
the next customer email would claim thousands of new entries.

## Things worth knowing

**The harvest filter is strict on purpose.** The portals tag anything touching
housing as Sector "Housing", which sweeps in solicitors, flooring contractors
and, in one real case, a bin supplier. A title has to name a placement service
explicitly. Some genuine providers will be missed; that is the right trade when
the alternative is a law firm appearing in a list customers pay for.

**New records are `Listed`, not `Verified`.** They come from award notices, so
most have no contact details until an enrichment pass runs over them
(`scripts/enrich_supplier_contacts_v5.py`, `scripts/firecrawl_verify.py`).
Worth doing before the monthly email, so the new entries are actually useful.

**`send.py` will not mail anyone twice.** Each run records who it sent to in
that run's `sent.json` and skips them next time.
