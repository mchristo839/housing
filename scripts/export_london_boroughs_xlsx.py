"""Export the London provider list to Excel, one sheet per borough.

A provider appears once per borough and may appear in as many boroughs as it
holds coverage for. Rows carry the full record we hold — contact details,
verification tier, categories, and the contracts that put the provider in that
borough.

The borough lists come from the site's own borough search, so the workbook
matches what a customer sees rather than a second, parallel interpretation of
the data. Run the dump first:

    node scripts/dump_london_boroughs.mjs
    python3 scripts/export_london_boroughs_xlsx.py [out.xlsx]
"""
import json, re, sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parent.parent
DUMP = ROOT / "data/london_boroughs.json"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "London_Providers_by_Borough.xlsx"

# The five service categories we break every provider down by, plus a catch-all.
# Each becomes a tick column, pre-filled from the provider's own categories and
# contract titles and editable afterwards.
CATEGORIES = [
    "Children's services",
    "Care leavers / young people",
    "Adults with learning difficulties",
    "Homelessness / asylum",
    "Victims of domestic violence",
    "Other services",
]
TICK = "✓"

COLUMNS = [
    ("Provider", 38), ("Tier", 10), ("Verified", 10),
] + [(c, 13) for c in CATEGORIES] + [
    ("Email", 34), ("Phone", 16),
    ("Website", 38), ("Contact page", 30), ("Primary category", 20), ("Sectors", 34),
    ("Client groups", 28), ("Housing association", 9), ("Employees", 10), ("Scope", 10),
    ("Councils", 9), ("Contracts", 9), ("Contracts in this borough", 70),
    ("All councils contracted", 60), ("HQ address", 34), ("Description", 40),
]
# Column index (1-based) of the first tick column and of the contracts column,
# used for centring the ticks and wrapping the contract text.
FIRST_TICK = 4
CONTRACTS_COL = len(COLUMNS) - 3
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
CAT_FILL = PatternFill("solid", fgColor="2E7D4F")     # the five categories + other
HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
TITLE_FONT = Font(bold=True, size=13)
TICK_ALIGN = Alignment(horizontal="center", vertical="center")


def norm_council_key(s):
    drop = {"council", "borough", "county", "city", "district", "the", "of",
            "metropolitan", "unitary", "authority", "corporation", "mbc", "mdc", "cc"}
    s = str(s or "").lower().replace("&", " and ")
    s = "".join(ch if ch.isalnum() or ch == " " else " " for ch in s)
    return " ".join(t for t in s.split() if t and t not in drop)


def borough_contracts(provider, borough):
    """The contract titles that put this provider in this borough. Regional and
    national operators carry no borough-specific award, so they are labelled by
    the scope that gives them their coverage instead."""
    key = norm_council_key(borough)
    lines = []
    for c in provider.get("contracts_list") or []:
        ck = norm_council_key(c.get("council"))
        if not (ck and key and (ck in key or key in ck)):
            continue
        for t in c.get("titles") or []:
            lines.append(t)
    return lines


# Signals that place a provider in one of the five categories. Matched against
# the provider's sectors, client groups and primary category, and against the
# titles of the contracts that put it in the borough.
# Matched on word boundaries, not raw substrings: "refugee" must not tick the
# domestic violence column, and "physical disabilities" must not tick the
# learning disability one.
CATEGORY_TERMS = {
    "Children's services":
        r"\bchildren\b|\bchild\b|looked after|fostering|\bfoster\b",
    "Care leavers / young people":
        r"young pe|young person|care leaver|16\+|semi.?independent",
    "Adults with learning difficulties":
        r"learning disab|learing disab|\bautism\b|\bautistic\b",
    "Homelessness / asylum":
        r"homeless|rough sleep|housing first|asylum|refugee|\bnrpf\b|no recourse|"
        r"dispersal|temporary accommodation|emergency|nightly purchased|"
        r"move.?on|probation|\bbail\b",
    "Victims of domestic violence":
        r"domestic violence|domestic abuse|\bvawg\b|\brefuges?\b",
}
# Services that are real but sit outside the five — these tick "Other services".
OTHER_TERMS = (
    r"mental health|\bolder\b|physical disab|substance misuse|sensory|\bhiv\b|"
    r"homecare|extra care|floating support|outreach"
)


def categorise(p, contracts):
    """Which of the five categories this provider's services fall into, plus the
    catch-all. Reads the provider's own categories and the contract titles."""
    haystack = " ".join([
        p.get("primary_cat", ""),
        " ".join(p.get("sector") or []),
        " ".join(p.get("client_groups") or []),
        " ".join(contracts),
    ]).lower()

    hits = {c: bool(re.search(pattern, haystack)) for c, pattern in CATEGORY_TERMS.items()}
    # "Other services" covers anything outside the five, and carries a provider
    # whose services we could not place at all so no row is left blank.
    hits["Other services"] = bool(re.search(OTHER_TERMS, haystack)) or not any(hits.values())
    return hits


def row_for(borough, tier, p):
    contracts = borough_contracts(p, borough)
    if not contracts:
        label = {"national": "National operator — covers all areas",
                 "regional": "Regional operator — covers this region",
                 "county": "County-level contract"}.get(tier, "")
        contracts = [label] if label else []
    ver = p.get("verification") or {}
    cats = categorise(p, contracts)
    return [
        p.get("name", ""),
        tier.title(),
        "Yes" if ver.get("verified") else (ver.get("tier") or "Listed"),
    ] + [TICK if cats[c] else "" for c in CATEGORIES] + [
        p.get("email", ""),
        p.get("phone", ""),
        p.get("website", ""),
        p.get("contact_page", ""),
        p.get("primary_cat", ""),
        ", ".join(p.get("sector") or []),
        ", ".join(p.get("client_groups") or []),
        "Yes" if p.get("is_housing_association") else "No",
        p.get("employees") if p.get("employees") is not None else "",
        p.get("scope", ""),
        p.get("council_count") or 0,
        p.get("contracts") or 0,
        "\n".join(contracts),
        ", ".join(p.get("councils") or []),
        p.get("hq_address", ""),
        p.get("description", ""),
    ]


def style_sheet(ws, title, header_row, tick_offset=None):
    ws.cell(row=1, column=1, value=title).font = TITLE_FONT
    for i, (name, width) in enumerate(header_row, start=1):
        c = ws.cell(row=2, column=i, value=name)
        c.fill = CAT_FILL if name in CATEGORIES else HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = Alignment(vertical="center", horizontal="center"
                                if name in CATEGORIES else "left", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.row_dimensions[2].height = 42
    ws.freeze_panes = "A3"
    ws.auto_filter.ref = "A2:%s2" % get_column_letter(len(header_row))

    # Keep the ticks editable: a one-option dropdown ticks a cell, delete clears it.
    if tick_offset is not None:
        for i in range(tick_offset, tick_offset + len(CATEGORIES)):
            col = get_column_letter(i)
            dv = DataValidation(type="list", formula1='"%s"' % TICK, allow_blank=True)
            ws.add_data_validation(dv)
            dv.add("%s3:%s%d" % (col, col, max(ws.max_row, 3) + 2000))


def safe_sheet_name(name):
    bad = set(':\\/?*[]')
    return "".join(ch for ch in name if ch not in bad)[:31]


def main():
    data = json.loads(DUMP.read_text())
    wb = Workbook()

    # ── Summary ──────────────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Summary"
    summary_cols = [("Borough", 30), ("Total providers", 15), ("Local", 10),
                    ("County", 10), ("Regional", 10), ("National", 10)]
    style_sheet(ws, "London providers by borough", summary_cols)
    r = 3
    totals = dict(total=0, local=0, county=0, regional=0, national=0)
    for borough in sorted(data):
        rows = data[borough]
        counts = {t: sum(1 for x in rows if x["tier"] == t)
                  for t in ("local", "county", "regional", "national")}
        ws.cell(row=r, column=1, value=borough)
        ws.cell(row=r, column=2, value=len(rows))
        for i, t in enumerate(("local", "county", "regional", "national"), start=3):
            ws.cell(row=r, column=i, value=counts[t])
            totals[t] += counts[t]
        totals["total"] += len(rows)
        r += 1
    for i, v in enumerate([("TOTAL (provider × borough rows)", totals["total"], totals["local"],
                            totals["county"], totals["regional"], totals["national"])][0], start=1):
        c = ws.cell(row=r, column=i, value=v)
        c.font = Font(bold=True)

    distinct = {x["p"]["id"] for rows in data.values() for x in rows}
    ws.cell(row=r + 2, column=1, value="Distinct providers across all boroughs").font = Font(bold=True)
    ws.cell(row=r + 2, column=2, value=len(distinct)).font = Font(bold=True)
    ws.cell(row=r + 3, column=1,
            value="A provider is listed once per borough and may appear in several boroughs.")

    # Service-category breakdown, counted over distinct providers.
    seen_cat, cat_counts = set(), {c: 0 for c in CATEGORIES}
    for borough, rows in data.items():
        for x in rows:
            p = x["p"]
            if p["id"] in seen_cat:
                continue
            seen_cat.add(p["id"])
            for c, on in categorise(p, borough_contracts(p, borough)).items():
                if on:
                    cat_counts[c] += 1

    b = r + 5
    ws.cell(row=b, column=1, value="Service categories").font = Font(bold=True, size=12)
    ws.cell(row=b + 1, column=1,
            value="Every provider is ticked against the five categories plus a catch-all. "
                  "A provider can sit in more than one.")
    for i, (name, width) in enumerate([("Category", 34), ("Providers", 12)], start=1):
        c = ws.cell(row=b + 2, column=i, value=name)
        c.fill, c.font = CAT_FILL, HEADER_FONT
    for i, cat in enumerate(CATEGORIES):
        ws.cell(row=b + 3 + i, column=1, value=cat)
        ws.cell(row=b + 3 + i, column=2, value=cat_counts[cat])
    ws.cell(row=b + 3 + len(CATEGORIES), column=1,
            value='Tick cells carry a dropdown — pick %s to tick, delete to clear.' % TICK)

    # ── One sheet per borough ────────────────────────────────────────────────
    for borough in sorted(data):
        rows = data[borough]
        sheet = wb.create_sheet(safe_sheet_name(borough))
        style_sheet(sheet, "%s — %d providers" % (borough, len(rows)), COLUMNS,
                    tick_offset=FIRST_TICK)
        seen = set()
        r = 3
        order = {"local": 0, "county": 1, "regional": 2, "national": 3}
        for item in sorted(rows, key=lambda x: (order.get(x["tier"], 9),
                                                -(x["p"].get("contracts") or 0),
                                                x["p"].get("name", ""))):
            p = item["p"]
            if p["id"] in seen:      # one row per provider per borough
                continue
            seen.add(p["id"])
            for i, v in enumerate(row_for(borough, item["tier"], p), start=1):
                cell = sheet.cell(row=r, column=i, value=v)
                if FIRST_TICK <= i < FIRST_TICK + len(CATEGORIES):
                    cell.alignment = TICK_ALIGN
                elif i == CONTRACTS_COL:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
            r += 1

    # ── Flat sheet: every borough × provider row in one table ────────────────
    flat = wb.create_sheet("All boroughs")
    flat_cols = [("Borough", 26)] + COLUMNS
    style_sheet(flat, "Every provider, by borough", flat_cols, tick_offset=FIRST_TICK + 1)
    r = 3
    for borough in sorted(data):
        seen = set()
        for item in data[borough]:
            p = item["p"]
            if p["id"] in seen:
                continue
            seen.add(p["id"])
            flat.cell(row=r, column=1, value=borough)
            for i, v in enumerate(row_for(borough, item["tier"], p), start=2):
                cell = flat.cell(row=r, column=i, value=v)
                if FIRST_TICK + 1 <= i < FIRST_TICK + 1 + len(CATEGORIES):
                    cell.alignment = TICK_ALIGN
            r += 1

    wb.save(OUT)
    print("wrote %s" % OUT)
    print("  sheets            : %d (Summary + %d boroughs + All boroughs)" % (len(wb.sheetnames), len(data)))
    print("  borough × provider: %d rows" % totals["total"])
    print("  distinct providers: %d" % len(distinct))


if __name__ == "__main__":
    main()
