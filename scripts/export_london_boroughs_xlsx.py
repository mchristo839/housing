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
import json, sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
DUMP = ROOT / "data/london_boroughs.json"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "London_Providers_by_Borough.xlsx"

COLUMNS = [
    ("Provider", 38), ("Tier", 10), ("Verified", 10), ("Email", 34), ("Phone", 16),
    ("Website", 38), ("Contact page", 30), ("Primary category", 20), ("Sectors", 34),
    ("Client groups", 28), ("Housing association", 9), ("Employees", 10), ("Scope", 10),
    ("Councils", 9), ("Contracts", 9), ("Contracts in this borough", 70),
    ("All councils contracted", 60), ("HQ address", 34), ("Description", 40),
]
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
TITLE_FONT = Font(bold=True, size=13)


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


def row_for(borough, tier, p):
    contracts = borough_contracts(p, borough)
    if not contracts:
        label = {"national": "National operator — covers all areas",
                 "regional": "Regional operator — covers this region",
                 "county": "County-level contract"}.get(tier, "")
        contracts = [label] if label else []
    ver = p.get("verification") or {}
    return [
        p.get("name", ""),
        tier.title(),
        "Yes" if ver.get("verified") else (ver.get("tier") or "Listed"),
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


def style_sheet(ws, title, header_row):
    ws.cell(row=1, column=1, value=title).font = TITLE_FONT
    for i, (name, width) in enumerate(header_row, start=1):
        c = ws.cell(row=2, column=i, value=name)
        c.fill, c.font = HEADER_FILL, HEADER_FONT
        c.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A3"
    ws.auto_filter.ref = "A2:%s2" % get_column_letter(len(header_row))


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

    # ── One sheet per borough ────────────────────────────────────────────────
    for borough in sorted(data):
        rows = data[borough]
        sheet = wb.create_sheet(safe_sheet_name(borough))
        style_sheet(sheet, "%s — %d providers" % (borough, len(rows)), COLUMNS)
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
                if i == 16:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
            r += 1

    # ── Flat sheet: every borough × provider row in one table ────────────────
    flat = wb.create_sheet("All boroughs")
    flat_cols = [("Borough", 26)] + COLUMNS
    style_sheet(flat, "Every provider, by borough", flat_cols)
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
                flat.cell(row=r, column=i, value=v)
            r += 1

    wb.save(OUT)
    print("wrote %s" % OUT)
    print("  sheets            : %d (Summary + %d boroughs + All boroughs)" % (len(wb.sheetnames), len(data)))
    print("  borough × provider: %d rows" % totals["total"])
    print("  distinct providers: %d" % len(distinct))


if __name__ == "__main__":
    main()
