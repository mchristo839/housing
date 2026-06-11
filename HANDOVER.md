# Find a Housing Provider — Handover Pack

Complete handover for a developer taking over hosting + ongoing maintenance.
Stack: **Vite + React** (frontend) → **Vercel** (hosting + serverless API) →
**Vercel KV (Upstash Redis)** (database) → **Stripe** (payments) →
**Firecrawl** (data verification). Codebase is built and operated through
**Claude Code** sessions.

---

## 1. What this product is

A paid postcode-search engine that returns every supported-living and social-housing
provider commissioned in a UK area, with verified contact details. Customers
(landlords + property developers) pay:
- **£29.99** per postcode unlock — one-off
- **£49.99** per county unlock — one-off
- **+£12.00** optional add-on: 3 outreach email templates

Live site: <https://findahousingprovider.vercel.app>

Currently in the database:
- ~1,900 providers
- ~1,880 of them Verified (98%)
- ~370 confirmed-not-housing on the permanent drop list

---

## 2. What's in this repo

```
.
├── api/                    # Vercel serverless functions (Node)
│   ├── _data/             # Server-only generated provider DB (providers.json, db.json)
│   ├── _lib/              # Shared helpers (match.js, billing.js, db.js, http.js)
│   ├── preview.js         # /api/preview  → counts + price for a search
│   ├── checkout.js        # /api/checkout → Stripe Checkout session
│   ├── result.js          # /api/result   → full provider list after payment
│   ├── portal.js          # /api/portal   → Stripe customer portal link
│   ├── notify-signup.js   # /api/notify-signup → save user to KV
│   └── admin.js           # /api/admin    → token-gated readout of signups
│
├── src/                   # React frontend (Vite)
│   ├── App.jsx           # Main app (~1,400 lines)
│   ├── data.js           # API client + savedEmail localStorage
│   ├── styles.css        # All CSS
│   ├── pdf.js            # PDF generator (pdfmake)
│   ├── message.js        # Outreach message builder
│   ├── engine_maps.js    # Council name normalisation maps
│   └── components/       # Results, GuidePage, Footer, etc.
│
├── data/                  # Source data + verification artefacts
│   ├── care_housing_database_v2_ENRICHED.xlsx  # MAIN source spreadsheet (monthly)
│   ├── manual_contracts.xlsx                    # Manual additions + verified contacts
│   ├── MANUAL_DROP_LIST.json                    # Permanent ban list (~370 entries)
│   └── verification/
│       ├── VERIFIED.json                        # Master verified-providers list
│       ├── firecrawl_analysed.json              # Per-supplier Firecrawl verdict cache
│       └── firecrawl_discovered_urls.json       # Cached URL discoveries
│
├── scripts/               # Maintenance + data scripts (Python)
│   ├── ingest_contract.py            # Process new Contracts Finder CSV → deploy
│   ├── firecrawl_verify.py           # Bulk Firecrawl /extract verification
│   ├── firecrawl_search_unverified.py  # Find websites for unverified suppliers
│   ├── firecrawl_lookup_names.py     # Look up names directly (no providers.json)
│   ├── firecrawl_lookup_batched.py   # Batched runner with apply+deploy per batch
│   ├── local_scrape_verify.py        # Free Python fallback (cloudscraper+DDG+Playwright)
│   ├── apply_firecrawl.py            # Apply Firecrawl verdicts to drop/verified lists
│   ├── sweep_homecare_only.py        # Demote pure-homecare from Verified
│   ├── final_push.py                 # Multi-CSV ingest + verify + deploy
│   └── monthly_notifications.py      # Monthly diff + send email (uses Resend)
│
├── docs/                  # Process + handover docs
│   ├── VERIFICATION_PROCESS.md      # The 4-step Firecrawl verification process
│   └── UPLOAD_NEW_CONTRACT.md       # Monthly CSV upload runbook
│
├── public/                # Static assets
│   ├── stats.json         # Public-safe homepage stats
│   └── email-templates.md # The 3 outreach templates (delivered after upsell)
│
├── build_data.py          # MAIN BUILD SCRIPT — regenerates api/_data/* from sources
├── package.json           # Node deps
├── vite.config.js         # Vite build config
├── vercel.json            # Vercel routing + serverless config
└── HANDOVER.md            # this file
```

---

## 3. Environment variables (set these in Vercel)

**Required for the product to function:**

| Variable | Where it's used | What to put |
|---|---|---|
| `STRIPE_SECRET_KEY` | api/checkout, result, portal | `sk_live_...` (live mode) — set up product at stripe.com |
| `STRIPE_PUBLISHABLE_KEY` | Optional — not used currently | `pk_live_...` |

**Required for data verification (server-side only — scripts on the developer's machine):**

| Variable | Where | What |
|---|---|---|
| `FIRECRAWL_API_KEY` | Python scripts | `fc-...` from https://firecrawl.dev — Standard plan $99/mo recommended for initial bulk runs, Hobby $19/mo for ongoing |

**For email notifications (optional, when ready):**

| Variable | Where | What |
|---|---|---|
| `RESEND_API_KEY` | scripts/monthly_notifications.py | `re_...` from https://resend.com (free 3,000 emails/mo) |
| `NOTIFY_FROM_EMAIL` | same | e.g. `alerts@findahousingprovider.co.uk` (after domain verify) |

**For the database (set automatically by Vercel KV provisioning):**

| Variable | Set by |
|---|---|
| `KV_URL`, `KV_REST_API_URL`, `KV_REST_API_TOKEN`, `KV_REST_API_READ_ONLY_TOKEN` | Vercel Dashboard → Storage → Create KV Database → Connect Project |

**Admin readout endpoint:**

| Variable | What |
|---|---|
| `ADMIN_TOKEN` | Any secret string — protects `/api/admin?token=...` |

---

## 4. Setup — copy across to developer's machine

The developer should:

1. **Get the code**
   - Receive the project folder (everything except `node_modules/`, `dist/`, `.vercel/`)
   - The `.claude/settings.json` in the project root will need their own API keys

2. **Install dependencies**
   ```bash
   npm install
   pip install -r requirements.txt   # see "Python scripts setup" below
   ```

3. **Set up Vercel project**
   ```bash
   npm install -g vercel
   vercel login
   vercel link                       # creates .vercel/ config; pick "create new project"
   ```

4. **Set env vars in Vercel dashboard** (the list in section 3)

5. **Provision Vercel KV** (5-min, one-time)
   - Vercel dashboard → Storage → Create Database → KV
   - Connect to project → auto-adds env vars
   - Redeploy

6. **Deploy**
   ```bash
   npm run build
   vercel deploy --prod --yes
   ```

7. **Point the domain**
   - Buy/transfer domain (e.g. `findahousingprovider.co.uk`)
   - In Vercel project settings → Domains → add custom domain
   - Update DNS A/CNAME as Vercel instructs

---

## 5. Python scripts setup

The data verification + monthly refresh runs in Python from a local machine. Setup:

```bash
pip install requests openpyxl pandas beautifulsoup4 cloudscraper fake-useragent duckduckgo-search playwright
playwright install chromium
```

Then for any script:
```bash
cd /path/to/findahousingprovider
export FIRECRAWL_API_KEY="fc-..."
python scripts/ingest_contract.py "C:/Downloads/notices.csv" --deploy
```

---

## 6. Monthly operating runbook

Every month, when new procurement data lands:

1. **Get a Contracts Finder CSV** for the past month
   - https://www.contractsfinder.service.gov.uk/Search → export to CSV
2. **Ingest it**
   ```bash
   python scripts/ingest_contract.py "Downloads/notices.csv" --deploy
   ```
   This auto: parses → dedups → Firecrawl-verifies new suppliers → rebuilds → deploys
3. **Run the homecare-only sweep** to clean stragglers
   ```bash
   python scripts/sweep_homecare_only.py
   ```
4. **Send monthly notifications** to signups
   ```bash
   export RESEND_API_KEY="re_..."
   python scripts/monthly_notifications.py
   ```

Time: ~30-60 minutes per month, mostly waiting for the Firecrawl + rebuild + deploy.

Full details: `docs/UPLOAD_NEW_CONTRACT.md`

---

## 7. What's NOT included in the hand-off

These are not in the repo and the new developer needs to set up:

| Item | Why | How |
|---|---|---|
| `node_modules/` | Built locally via `npm install` | — |
| `dist/` | Built locally via `npm run build` | — |
| `.vercel/` | Per-deploy config | `vercel link` |
| Live Stripe keys | Sensitive, owner-only | Stripe dashboard → API keys |
| Live Firecrawl key | Sensitive, owner-only | Firecrawl dashboard |
| Production domain | Owned by the business | Vercel dashboard → Domains |
| KV database | Provisioned per deployment | Vercel dashboard → Storage |

---

## 8. Key technical decisions to know about

| Decision | Why |
|---|---|
| **Data lives server-side** | `api/_data/providers.json` is never served publicly — only counts/price come back from `/api/preview`, full list only after Stripe payment via `/api/result` |
| **Verification = Firecrawl LLM extraction** | 4-step check: website ownership, real services, contact extraction, drop-list filtering. 1,800+ already through this. |
| **manual_contracts.xlsx is the source of truth** | The main spreadsheet refreshes monthly; the manual file holds verified contacts that survive every refresh |
| **norm() function is critical** | Strips Ltd/Limited/PLC/LLP/CIC for duplicate detection. **Must stay in sync across `build_data.py`, `ingest_contract.py`, `final_push.py`** |
| **homecare-only filter** | Customers want supported-living/social-housing operators, not pure-homecare. Three layers of filtering ensure this. |
| **norm-based dedup at every ingest** | Saves ~50% of new-supplier credits per CSV ingest. |

---

## 9. How to work with Claude Code on this codebase

The codebase is built and operated through Claude Code. To pick up where this
session leaves off:

1. **Read the memory files** at `~/.claude/projects/.../memory/`:
   - `findahousingprovider.md` — overall project
   - `findahousingprovider_contract_upload.md` — CSV upload workflow + norm() rule
   - `findahousingprovider_verification.md` — Firecrawl process

2. **Common starter prompts:**
   - *"I have a new CSV at C:/path/notices.csv — please ingest it"*
   - *"Run the monthly notification email send"*
   - *"Re-verify all unverified providers via Firecrawl"*
   - *"Add a new column to the search results showing X"*

3. **Anything destructive Claude will ask first.** Anything routine
   (CSV ingest, build, deploy) it will just do.

---

## 10. Support contacts / where to ask questions

| Question | Where |
|---|---|
| Vercel hosting | https://vercel.com/docs |
| Vercel KV | https://vercel.com/docs/storage/vercel-kv |
| Stripe payments | https://stripe.com/docs |
| Firecrawl extraction | https://docs.firecrawl.dev |
| Resend emails | https://resend.com/docs |
| Anything in the codebase | Open a Claude Code session in this project folder + ask |

---

## 11. Open items the new developer might address

| Item | Effort | Priority |
|---|---|---|
| Provision Vercel KV in the new account | 5 min | High |
| Set up Stripe live keys + payouts | 30 min | High |
| Sign up for Resend + verify domain | 15 min | Medium |
| Set up custom domain | 15 min | Medium |
| Monthly Contracts Finder CSV ingest | 30 min/mo | Ongoing |
| Wire customer correction submission form | 1-2 hrs | Low |
| Schedule monthly notification cron | 30 min | Medium |

---

*Generated 2026-06-11. Latest live state: 1,910 providers, 1,883 Verified.*
