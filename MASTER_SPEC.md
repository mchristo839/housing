# Find a Housing Provider — Master Data Spec ("the master prompt")

This is the single source of truth for how raw council/care-contract data is turned into the
site's data. It is **deterministic**: the same input file always produces the same output.
That determinism is why processing is a fixed Python script (`build_data.py`) and **not** an
LLM prompt — an LLM re-reading 8,000+ rows would not return the same result twice.

Use this document to (a) run the monthly refresh, (b) understand/extend the rules, or (c) hand
to a developer or AI to rebuild the pipeline exactly.

---

## 1. Monthly update — the whole procedure

1. Export this month's data as the workbook described in §2 (same sheets/columns).
2. Drop it in `data/` (overwrite `care_housing_database_v2_ENRICHED.xlsx`, **or** keep your own
   name and point at it):
   ```
   FAHP_INPUT=data/your_new_file.xlsx npm run data
   ```
   (plain `npm run data` uses the default file name.)
3. That regenerates `api/_data/{providers,db,councilmap,lha}.json` and `public/stats.json`.
4. Check the printed summary (providers kept, drops, tiers).
5. `npm run build` to verify, then `npx vercel deploy --prod` to publish.

Auxiliary files in `data/` are **optional** (used only to enrich): `Care_Database_Employee_Numbers.xlsx`
(staff counts), `CareLeads_Provider_Contacts.xlsx` (in-network contacts), `LHA_Rates_by_Council_2026_27.xlsx`
(rent rates). If absent, the build still runs.

---

## 2. Required input format (the workbook)

A single `.xlsx` with three sheets:

**`Company × Council × Sector`** — one row per (provider × commissioner × sector). Columns used:
| Col | Name | Use |
|---|---|---|
| 0 | Company | provider name |
| 1 | Sector | `Homecare` / `Housing` |
| 2 | Council | commissioner (council / consortium / portal / NHS body) |
| 3 | Contracts (this council, this sector) | contract count |
| 10 | Categories | atomic service categories (`;`/`|` separated) |
| 12 | Contract Titles | contract names (`;` separated) |
| 13 | ONS Region | one of the 9 English regions |
| 14 | Commissioner Type | `Local Council` / `County Council` / `NHS` / `Regional Framework` / `National Government` / `Housing Association` / `Other` |
| 15 | Geographic Scope | `Local` / `Regional` / `National` (treated as a hint, reconciled below) |

**`Companies`** — one row per provider: Company, Total/Homecare/Housing Contracts, All Councils,
Address, Website, Telephone, Email, Contact Page, Charity Number/Income/Status/Activities, Website Review,
Is SME.

**`Councils`** — Council, ONS Region, Asylum Contractor (per council).

---

## 3. The rules, in order (what `build_data.py` does)

### 3a. Which COMPANIES are kept
A provider is included only if **all** of:
1. **Housing-led** — `Housing Contracts > 0` and `Housing ≥ Homecare` (drops homecare-dominant agencies). In-network curated contacts are kept if they have any housing footprint.
2. **Not a non-care business** — name not in the blocklist (`NONCARE_NAME`: facilities, security, cleaning, catering, construction, staffing/recruitment, hotels, furniture, travel, logistics, marine, KPMG/Ipsos/AECOM, research services, …) and not a soft-blocked construction/regeneration major (`NONCARE_SOFT`: ENGIE/Equans/Lovell/Kier/… unless the name also contains a care/housing word).
3. **Holds ≥1 genuine housing contract** (see 3b) — else dropped as homecare/non-housing.
4. **Reachable** — has an email, a contact page, or a verified website.

### 3b. Which CONTRACTS count (per-contract housing test)
A contract counts only if **housing is part of the agreement**:
- **Excluded outright (`is_junk_title` → `FM_TITLE`/`IRRELEVANT_TITLE`):** facilities/works/lighting/highways/repairs/maintenance/decoration; **food/catering/meals/supplies/laundry/kitchen**; travel/logistics/marine; **research/assessment/consultancy**; **medical (GP surgery/clinic/pharmacy/dental)**; COVID-19 "Wave 2" emergency one-offs; furniture/furnishings.
- **Excluded as care-delivery, not housing (`HOMECARE_OVERRIDE`):** home-based care, domiciliary, care-at-home, reablement, day care, **short breaks/respite** — the provider delivers care into someone else's scheme, so it is not housing provision (even if the title mentions "extra care"/"sheltered housing").
- **Kept (`HOUSING_TITLE` or Sector = `Housing`):** supported living, supported/community accommodation, housing/housing-related support, extra care, sheltered, hostel, refuge, emergency/temporary accommodation, asylum, move-on, tenancy.

Matching (which councils a provider appears under) is based **only** on councils where they hold a kept housing contract.

### 3c. Contract title cleaning
- Decode HTML entities (`&apos;` → `'`).
- Strip the trailing **commissioner (council)** and **supplier (company)** names and the `- AWARD` tag, leaving just what the contract is for.
- Titles are shown in full (no truncation); facilities/junk titles are stripped from display.

### 3d. Geography & tier of each contract — "which councils qualify"
For each contract, in priority order:
1. **Joint/group commissioning** — the resolver reads **both the commissioner name and the title** for
   council names + abbreviations and **pins to every council named**, when it's genuinely a group
   (commissioner names **2+ councils**, e.g. "Coventry - Solihull - Warwickshire" or "WCC/RBKC", **or**
   the title names specific council(s)). A *single*-council commissioner keeps its recorded scope (so
   genuine regional/national frameworks aren't collapsed to Local). Specifically:
   - **Curated abbreviations** (`GROUP_ABBREV`): `RBKC` → Kensington & Chelsea **+** Westminster (bi-borough); `LBTH`→Tower Hamlets; `LBHF`→Hammersmith & Fulham; `LBBD`,`LBWF`,`RBG`,`RBWM`…
   - **County-council abbreviations** (`county_abbrev`, auto-built): `WSCC`→West Sussex, `KCC`→Kent, `HCC`→Hertfordshire, etc.
   - **Full council/borough names** in the title (auto-built `place_council`, ≥6 chars to avoid ambiguity).
   - *Skipped if the title says "pan-London / London-wide / region-wide" (`PAN_RE`)* → then it's genuinely Regional.
2. **Purchasing consortium** (`CONSORTIA`) → expand to **every member authority** (County or Local), tagged `via {consortium}`:
   - **ESPO** → Leicestershire, Lincolnshire, Cambridgeshire, Norfolk, Warwickshire (County) + Peterborough (Local).
   - **YPO** → Barnsley, Bradford, Calderdale, Doncaster, Kirklees, North Yorkshire, Rotherham, Wakefield, Bolton, Knowsley, Wigan, St Helens.
   - **Welland Procurement** → Melton, Harborough, Rutland, South Kesteven.
3. **County Council commissioner** → **County** tier for that county.
4. **Portal / shared-service / NHS-CSU commissioner** (`COMMISSIONER_JUNK`: shared services, IN-TEND, e-tendering, procurement, consortium, ESI) → region is unreliable; derive area from the title (county/region); if undeterminable, **exclude from any region tier** rather than mis-assign.
5. **`National` Geographic Scope** with `National Government`/`NHS` commissioner and no place in the title → **National**; with a single-council commissioner → Local; with a Regional Framework → Regional.
6. Otherwise the commissioner's own council/region (its recorded `Geographic Scope`).

### 3e. Enrichment
- **Client groups** ("what they do") inferred from contract titles: Learning disabilities, Autism, Mental health, Physical disabilities, Acquired brain injury, Older people, Homelessness, Young people & care leavers, Substance misuse, Domestic abuse, Asylum & refugees, Sensory impairment.
- **Housing-association flag** (heuristic: name contains "housing association"/known HA / "housing"+trust/association / ends "Homes").
- **Charity** record (number/income/status/activities) where present.
- **Employees** + confidence (matched by name from the employees file).
- **In-network** flag + contact override (from the curated contacts file).
- **LHA** rates joined by council (shared/1/2/3/4-bed) for the LHA teaser + report.

---

## 4. Output (what the site reads)

| File | Public? | Contents |
|---|---|---|
| `api/_data/providers.json` | **server-only** | full provider records (schema below) |
| `api/_data/db.json` | server-only | `{c: council→[ids], county: county→[ids], r: region→[ids], n: [ids]}` index |
| `api/_data/councilmap.json` | server-only | auto-generated `normalisedCouncil → [council keys]` (every council with contracts) |
| `api/_data/lha.json` | server-only | council → LHA rates |
| `public/stats.json` | public | `{providers, councils, regions, in_network}` aggregates only — **no names/contacts** |

**Provider record schema:**
```json
{
  "id": "creative-support", "name": "Creative Support",
  "website": "...", "website_unverified": false, "email": "...", "contact_page": "", "phone": "...",
  "regions": ["North West", ...], "councils": ["Manchester City Council", ...],
  "scope": "National", "employees": 5612, "employee_confidence": "High",
  "sector": ["Supported living", ...], "primary_cat": "Supported living",
  "client_groups": ["Learning disabilities", ...], "is_housing_association": false,
  "description": "...", "hq_address": "...",
  "contracts": 35, "housing_contracts": 30, "total_contracts": 50,
  "contracts_list": [ {"council":"Manchester City Council","region":"North West","scope":"County|Local|Regional|National","county":"","via":"","n":1,"sectors":["Housing"],"titles":["..."]} ],
  "is_sme": null, "in_network": true, "charity": null, "contact_name": "", "contact_title": ""
}
```

**Matching at search time** (`api/_lib/match.js`): postcode → `postcodes.io` → admin_district + admin_county + region →
- **Local** = providers in `db.c` for the district (resolved via `councilmap`),
- **County** = `db.county` for `admin_county`,
- **Regional** = `db.r` for the region (minus local/county), + the region's Home-Office asylum contractor,
- **National** = `db.n` (minus the rest).
Each provider's `contracts_list` is trimmed to only the **relevant** entries (this council / this county / this region / national).

---

## 5. How to extend (most edits are one line, at the top of `build_data.py`)

- **A supplier/non-care company slips through** → add a word to `IRRELEVANT_TITLE` or `NONCARE_NAME`.
- **A new purchasing consortium** → add to `CONSORTIA` with its member councils.
- **A new abbreviation** (e.g. another London bi-borough) → add to `GROUP_ABBREV`.
- After any edit: `npm run data` → `npm run build` → deploy.

---

## 6. If you ever want an AI to re-derive this (the literal prompt)

> You are given a council care-contract workbook (sheets: `Company × Council × Sector`, `Companies`,
> `Councils`, columns as in §2). Produce `providers.json` and a `db.json` index per the schema in §4,
> applying — deterministically and in this order — the rules in §3: keep only housing-led, reachable,
> care/housing companies (§3a); count only contracts where housing is part of the agreement, excluding
> facilities/food/supplies/medical/research/COVID and care-delivery-only contracts (§3b); clean titles
> (§3c); decide each contract's council(s)/tier by title-named councils → consortium members → county
> council → portal/NHS title-routing → national/regional (§3d); enrich with client groups, HA flag,
> charity, employees, LHA (§3e). **Do not invent data.** If a contract names no council and isn't
> pan-region, exclude it from the region tier rather than guessing.

Note: prefer running `build_data.py` — it is the canonical, reproducible implementation of the above.
