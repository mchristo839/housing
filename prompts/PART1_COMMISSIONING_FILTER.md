# Part 1 — Commissioning Council / Agent Filter

**Status:** live in `build_data.py` (audit at 99.9% confidently mapped, 0 unresolved as of June 2026, including 18 curated rows added via the manual-additions layer for HMPPS CAS-2/CAS-3 and Home Office AASC contracts).

This is one of three filter stages that together turn a postcode into the right list of housing providers. Parts 2 (provider-quality filter) and 3 (contract-type filter) are scoped separately.

---

## 1. Purpose (one sentence)

Given the raw council × company × sector workbook, **resolve every contract's commissioner string to the specific council(s) / county / region / national footprint it covers**, so that a postcode search can later be tier-matched (Local / County / Regional / National) with confidence.

## 2. Input

The `Company × Council × Sector` sheet rows from `data/care_housing_database_v2_ENRICHED.xlsx`. The fields this stage cares about:

| Column | Used for |
|---|---|
| `Council` (commissioner name) | Primary signal: who commissioned the contract |
| `Contract Titles` | Secondary signal: when the commissioner is ambiguous (portal / NHS body), the title may name a council |
| `Geographic Scope` | Recorded hint: `Local` / `Regional` / `National` — used as fallback only |
| `Commissioner Type` | Recorded hint: `Local Council` / `County Council` / `NHS` / `Regional Framework` / `National Government` / `Housing Association` / `Other` |
| `ONS Region` | Used for Regional-tier assignment |

## 3. Output (per row)

```
(council_display_name, scope, county_key, region, via_consortium)
```

Where `scope ∈ {Local, County, Regional, National}` and `county_key` matches the lowercased `admin_county` returned by postcodes.io for matching.

A single source row may emit **multiple** output records — e.g. a joint commissioner naming 3 councils emits 3 rows.

## 4. The eight categories the resolver must handle

Every commissioner falls into one of these. The resolver picks the **first** applicable category in the order shown.

| # | Category | Example commissioner | Action |
|---|---|---|---|
| 1 | **Non-housing body** (university / police / fire / catering / govt dept that doesn't commission housing) | `Hertfordshire Catering Ltd`, `Cabinet Office`, `Crown Commercial Service`, a university or police force | **Drop** the row entirely (`COMMISSIONER_EXCLUDE`). NOTE: Ministry of Justice / HMPPS and Home Office are **NOT** in this list — they genuinely commission supported / probation / asylum housing (CAS-1/2/3, AASC). They route to categories 2 or 8. |
| 2 | **Direct commissioner override** (NHS body / shared-services with documented catchment) | `NHS Sheffield CCG`, `Salford Royal NHS FT`, `LGSS` | Reroute to documented council(s) (`COMMISSIONER_MAP`) |
| 3 | **Purchasing consortium** (members documented) | `ESPO`, `YPO`, `Welland Procurement` | Expand to every member authority, tagged `via {consortium}` (`CONSORTIA`) |
| 4 | **Joint / group commissioning** — commissioner OR title names 2+ specific councils | `Coventry - Solihull - Warwickshire`, `RBKC` (bi-borough), `WCC/RBKC` | Pin to each named council/borough as Local (or County for county-level abbreviations like `WSCC`) (`GROUP_ABBREV` + `classify_title`) |
| 5 | **Single named council / borough / unitary** | `Manchester City Council`, `London Borough of Barnet Council`, `Bradford Metropolitan District Council`, `Kingston upon Thames`, `Buckinghamshire Council` | Local tier for that council |
| 6 | **County Council** | `Kent County Council`, `Hertfordshire County Council` | County tier with `county_key = "kent"` etc. |
| 7 | **Portal / aggregator / NHS body with unmappable footprint** | `IN-TEND LIMITED`, `capitalEsourcing`, `EU Supply Limited`, `NHS Humber & North Yorkshire ICB` | Read the title for a council/county name (`classify_title` on title); if found → Local/County. If title says "pan-London / region-wide" → genuine Regional. Else → exclude from any council tier rather than mis-assign. |
| 8 | **National government / national framework**, commissioner doesn't name a place | `Ministry of Justice` (CAS-2 Nacro national contract), `Home Office` (AASC asylum framework — regional lots), national-government departments with `Geographic Scope = National` | National tier (or Regional when the row's recorded scope is Regional, e.g. AASC regional lots) |

## 5. The `classify_title` resolver — what it scans for

Called for both the commissioner field AND the title. Three passes per string:

1. **Curated multi-borough / multi-council abbreviations** (`GROUP_ABBREV`): `RBKC` → K&C + Westminster, `LBTH` → Tower Hamlets, etc. Hand-maintained because abbreviations aren't derivable.
2. **County-council abbreviations** (`county_abbrev`, auto-built from any "X County Council" in the Councils sheet): `WSCC` → West Sussex CC, `KCC` → Kent CC.
3. **Full council/borough names** (`place_council`, auto-built): every council name from the Councils sheet, matched as a whole word.

**Safety rails:**
- Length ≥ 4 chars (no matching on short tokens).
- `PLACE_STOP` excludes region names + generic words ("london", "city", "council", "central").
- Substring filter drops a place that is a sub-phrase of a longer matched place ("Lincolnshire" inside "North East Lincolnshire" doesn't double-match).
- Both the index and the query side normalise text the same way: strip `(london|royal) borough of`, replace non-alpha with space, collapse multiple spaces, lowercase. Without this Kingston upon Thames, Redcar & Cleveland, Brighton & Hove silently failed to resolve.

## 6. The pin guard (critical — don't remove)

`load_company_sector` only pins a row to specific councils when:

```
(len(comm_members) >= 2 or title_members) and not PAN_RE.search(titles)
```

i.e. a **genuine group** — commissioner names ≥ 2 councils, OR the title explicitly names specific council(s). A *single*-council commissioner with `Geographic Scope = Regional` keeps that recorded scope — it does NOT get demoted to Local. `PAN_RE` ("pan-London", "region-wide", "all boroughs") overrides everything → genuinely Regional.

This is what prevents real Regional/National frameworks collapsing to Local.

## 7. What this filter explicitly does NOT do (scope boundary)

Reserved for Parts 2 and 3:

- **Does NOT decide whether a company is a real housing provider.** A "TSG Building Services Ltd" or "Greenbrook Healthcare" surfacing for a postcode is a *provider-quality* issue (Part 2), not a commissioner-resolution issue.
- **Does NOT decide whether a contract title is housing-related.** Filtering out homecare/respite/FM/medical/research titles is a *contract-type* issue (Part 3).
- **Does NOT enrich provider records** (employees, charity status, LHA, client groups) — separate enrichment stage.
- **Does NOT do postcode → council resolution at search time** — that's `postcodes.io` + `match.js`, not this stage.

## 8. Manual additions layer (curated rows that survive monthly refresh)

When a contract is genuine but missing from the monthly source workbook
(e.g. national HMPPS/Home Office frameworks that aren't picked up by the
council-procurement scrape), add it to a SEPARATE file the refresh doesn't
touch: a manual-additions workbook with the SAME column structure as the
main source. The pipeline loads it AFTER the main file and merges its rows
into the same `(cats, contracts, Companies)` state — so curated rows go
through the exact same 8-category resolver as everything else.

Currently 18 such rows live in this layer:
- 1 × CAS-2 (Nacro, National) — Ministry of Justice national bail / HDC contract
- 8 × CAS-3 (3 × Mears Group northern lots + 5 × The Housing Network southern/midland lots) — MOJ regional probation accommodation
- 9 × AASC (2 × Mears + 4 × Serco + 3 × Clearsprings Ready Homes) — Home Office asylum framework, regional lots

Every row cites its Find-a-Tender reference / contract value / bed-space
count in the title so the source is auditable. Treat manual additions as
data, not as rule-changes — they go through the same resolver as the main
file. Net-new providers (Mears Group, Serco) ride in the manual file's
Companies sheet alongside the contract rows.

## 9. Adding a new entry (the only edits you should ever make)

| Symptom | Action |
|---|---|
| A new multi-borough abbreviation appears (e.g. another London bi-borough) | Add to `GROUP_ABBREV` |
| A new purchasing consortium appears | Add to `CONSORTIA` with its member authorities |
| An NHS body / shared-services body with documented single or small-bounded catchment appears | Add to `COMMISSIONER_MAP` |
| A government department / police / university / catering body appears as commissioner | Add to `COMMISSIONER_EXCLUDE` |
| A portal name (IN-TEND-style) appears | Add to `COMMISSIONER_JUNK` so it falls through to title-routing rather than being treated as a council |

All five live at the top of `build_data.py`. After any edit: `npm run data` → re-run the audit (§10) → check unresolved count stays at 0.

## 10. Criteria for adding to `COMMISSIONER_MAP` specifically

A commissioner needs an override entry when **all four** are true:

1. It isn't a council name (so `match.js`'s normalizer can never reach the right council from the string alone).
2. There's a documented, bounded catchment (NHS ICB published coverage, NHS FT clinical catchment, shared-services member list). Ideally ≤ 8 councils.
3. The contract title doesn't reliably name the council (else `classify_title` would already handle it).
4. It's a real commissioner — NOT a portal used by many councils (IN-TEND, capitalEsourcing → `COMMISSIONER_JUNK`) and NOT a mis-listed provider (housing associations → `COMMISSIONER_EXCLUDE`).

## 11. Verification — the audit script (must run after every refresh)

For every kept housing-contract row, classify by resolution source:

| Bucket | Description |
|---|---|
| A | Named council (direct) |
| B | County council (direct) |
| C | GROUP_ABBREV / multi-borough |
| D | CONSORTIA member expansion |
| E | COMMISSIONER_MAP override |
| F | Title-pinned (commissioner ambiguous, title named council) |
| G | PAN-region / genuinely Regional |
| H | National (gov dept + national scope) |
| I | Excluded (non-housing body) |
| **J** | **UNRESOLVED — fallback to recorded scope only** |

**Pass condition: bucket J = 0.** Any non-zero J means a commissioner failed all the routing rules — investigate and add an appropriate override.

Current state: 2,997 mapped (A-H, 99.9%) / 4 excluded (I, 0.1%) / **0 unresolved (J)**.

## 12. Files & functions

| Element | Location |
|---|---|
| Resolver | `build_data.py::classify_title` |
| Pin guard | `build_data.py::load_company_sector` (the `if (len(comm_members) >= 2 or title_members)` block) |
| Override map | `build_data.py::COMMISSIONER_MAP` + `match_commissioner_override` |
| Consortium expansion | `build_data.py::CONSORTIA` + `match_consortium` |
| Multi-borough abbreviations | `build_data.py::GROUP_ABBREV` |
| Portal blocklist | `build_data.py::COMMISSIONER_JUNK` |
| Non-housing exclusion | `build_data.py::COMMISSIONER_EXCLUDE` |
| Place index | `build_data.py::build_place_maps` |
| Manual additions loader | `build_data.py::load_manual_additions` reading `data/manual_contracts.xlsx` |
| Search-time matcher | `api/_lib/match.js::matchResolved` (consumes this stage's output) |

## 13. If you're an AI re-deriving this stage from scratch

> You are given a workbook (`Company × Council × Sector`, `Companies`, `Councils` sheets — columns per §2 of the project's MASTER_SPEC.md). Produce, for each row, one or more `(council, scope, county_key, region, via)` records, applying the eight categories in §4 in priority order. The output must be deterministic (same input → same output). Implement `classify_title` per §5 with both index and query text normalised identically (strip "(london|royal) borough of", replace non-alpha with space, collapse whitespace, lowercase). Pin to multiple councils only when the conditions in §6 are met. Never invent data: if a commissioner falls through every category, emit it to a review bucket rather than guessing a location. Run the audit in §11; the pass condition is bucket J = 0.
