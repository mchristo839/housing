"""
CareLeads — Provider Website Scraper
Uses Firecrawl to scrape each provider's website and extract:
  - Description / what they do
  - Services offered
  - Areas / regions covered
  - Any housing / property contact info

Run: python scrape_provider_websites.py
Output: care_provider_scraped.xlsx

Requirements:
  pip install firecrawl-py pandas openpyxl
  Set FIRECRAWL_API_KEY in environment or .env file
"""

import os
import time
import json
import pandas as pd
from firecrawl import FirecrawlApp

# ── CONFIG ──────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")   # set in your env or paste here
INPUT_FILE  = "CareLeads_Provider_Contacts.xlsx"
OUTPUT_FILE = "care_provider_scraped.xlsx"
DELAY_SECONDS = 2          # polite delay between requests
MAX_PROVIDERS = None       # set to e.g. 5 to test on first 5, None for all

# What to extract from each site via Firecrawl's LLM extraction
EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {
            "type": "string",
            "description": "1-3 sentence description of what the organisation does"
        },
        "services": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of care or housing services offered, e.g. 'Supported living', 'Domiciliary care', 'Mental health'"
        },
        "regions_covered": {
            "type": "array",
            "items": {"type": "string"},
            "description": "UK regions or counties where they operate, e.g. 'London', 'Yorkshire', 'National'"
        },
        "client_groups": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Client groups served, e.g. 'Learning disabilities', 'Mental health', 'Homeless', 'Older people'"
        },
        "property_housing_contact": {
            "type": "string",
            "description": "Any dedicated property, housing or estates email address or contact if mentioned"
        },
        "number_of_services_or_locations": {
            "type": "string",
            "description": "How many services, homes, or locations they operate if stated"
        }
    },
    "required": ["description"]
}

EXTRACTION_PROMPT = (
    "Extract key information about this care or housing organisation. "
    "Focus on: what they do, who they support, where they operate in the UK, "
    "and any property or housing contact details."
)

# ── LOAD PROVIDERS ───────────────────────────────────────────────────────────
def load_providers(path):
    df = pd.read_excel(path, skiprows=1)
    df.columns = [
        'Provider Name', 'Contracts', 'Use This Email',
        'Property Email', 'Phone', 'Website',
        'HQ Address', 'Notes', 'Source'
    ]
    df = df[df['Provider Name'].notna() & (df['Provider Name'] != 'Provider Name')]
    df = df[df['Website'].notna() & df['Website'].str.startswith('http', na=False)]
    df = df.drop_duplicates(subset='Website')   # deduplicate by URL
    return df.reset_index(drop=True)

# ── SCRAPE ONE URL ───────────────────────────────────────────────────────────
def scrape_provider(app, url):
    """Scrape a single provider URL. Returns dict of extracted fields."""
    try:
        result = app.scrape_url(
            url,
            params={
                "formats": ["extract"],
                "extract": {
                    "schema": EXTRACTION_SCHEMA,
                    "prompt": EXTRACTION_PROMPT,
                }
            }
        )
        extracted = result.get("extract", {})
        return {
            "scrape_status": "ok",
            "description":       extracted.get("description", ""),
            "services":          "; ".join(extracted.get("services", [])),
            "regions_covered":   "; ".join(extracted.get("regions_covered", [])),
            "client_groups":     "; ".join(extracted.get("client_groups", [])),
            "property_contact":  extracted.get("property_housing_contact", ""),
            "service_count":     extracted.get("number_of_services_or_locations", ""),
            "raw_extract":       json.dumps(extracted),
        }
    except Exception as e:
        return {
            "scrape_status": f"error: {e}",
            "description": "", "services": "", "regions_covered": "",
            "client_groups": "", "property_contact": "", "service_count": "",
            "raw_extract": "",
        }

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    if not API_KEY:
        raise ValueError(
            "FIRECRAWL_API_KEY not set. "
            "Run: export FIRECRAWL_API_KEY=your_key_here"
        )

    app = FirecrawlApp(api_key=API_KEY)
    providers = load_providers(INPUT_FILE)

    if MAX_PROVIDERS:
        providers = providers.head(MAX_PROVIDERS)

    print(f"Scraping {len(providers)} providers...\n")

    results = []
    for i, row in providers.iterrows():
        name = row['Provider Name']
        url  = row['Website']
        print(f"[{i+1}/{len(providers)}] {name} — {url}")

        scraped = scrape_provider(app, url)
        print(f"  → {scraped['scrape_status']}")
        if scraped['description']:
            print(f"  → {scraped['description'][:100]}...")

        results.append({
            **row.to_dict(),
            **scraped,
        })

        time.sleep(DELAY_SECONDS)

    # ── SAVE ──────────────────────────────────────────────────────────────────
    out = pd.DataFrame(results)
    out.to_excel(OUTPUT_FILE, index=False)
    print(f"\nDone. Saved to {OUTPUT_FILE}")

    # Summary
    ok    = out[out['scrape_status'] == 'ok']
    error = out[out['scrape_status'] != 'ok']
    print(f"  Successful: {len(ok)}")
    print(f"  Errors:     {len(error)}")
    if len(error):
        print("  Failed URLs:")
        for _, r in error.iterrows():
            print(f"    {r['Provider Name']}: {r['scrape_status']}")

if __name__ == "__main__":
    main()
