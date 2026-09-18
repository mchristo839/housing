"""Export the London provider list to Excel as a single flat sheet.

One row per distinct provider — no repeats across boroughs — with a Boroughs
column listing every borough they cover. This is the alternative to
export_london_boroughs_xlsx.py's one-tab-per-borough layout, for a reader who
wants one list rather than 33 tabs.

    node scripts/dump_london_boroughs.mjs
    python3 scripts/export_london_flat_xlsx.py [out.xlsx]
"""
import json, re, sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parent.parent
DUMP = ROOT / "data/london_boroughs.json"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "London_Providers_Flat_List.xlsx"

# Same six service categories, and the same matching rules, as the by-borough
# workbook — kept identical so the two exports never disagree with each other.
CATEGORIES = [
    "Children's services",
    "Care leavers / young people",
    "Adults with learning difficulties",
    "Mental health",
    "Homelessness / asylum",
    "Victims of domestic violence",
    "Other services",
]
TICK = "✓"

CATEGORY_TERMS = {
    "Children's services":
        r"\bchildren\b|\bchild\b|looked after|fostering|\bfoster\b",
    "Care leavers / young people":
        r"young pe|young person|care leaver|16\+|semi.?independent",
    "Adults with learning difficulties":
        r"learning disab|learing disab|\bautism\b|\bautistic\b",
    "Mental health":
        r"mental health|\bmental\b",
    "Homelessness / asylum":
        r"homeless|rough sleep|housing first|asylum|refugee|\bnrpf\b|no recourse|"
        r"dispersal|temporary accommodation|emergency|nightly purchased|"
        r"move.?on|probation|\bbail\b",
    "Victims of domestic violence":
        r"domestic violence|domestic abuse|\bvawg\b|\brefuges?\b",
}
OTHER_TERMS = (
    r"\bolder\b|physical disab|substance misuse|sensory|\bhiv\b|"
    r"homecare|extra care|floating support|outreach"
)

COLUMNS = [
    ("Provider", 38), ("Verified", 10),
] + [(c, 13) for c in CATEGORIES] + [
    ("Email", 34), ("Phone", 16), ("Website", 38), ("Contact page", 30),
    ("Primary category", 20), ("Sectors", 34), ("Client groups", 28),
    ("Housing association", 9), ("Employees", 10), ("Scope", 10),
    ("Boroughs (this workbook)", 60), ("Borough count", 8),
    ("All councils contracted", 60), ("Council count", 8), ("Total contracts", 8),
    ("HQ address", 34), ("Description", 40),
]
FIRST_TICK = 3

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
CAT_FILL = PatternFill("solid", fgColor="2E7D4F")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
TITLE_FONT = Font(bold=True, size=13)
TICK_ALIGN = Alignment(horizontal="center", vertical="center")


def categorise(p):
    """Categorise on the provider's own fields and the titles of ALL its
    contracts — not just the ones in a single borough, since this row stands
    for the provider across every borough it appears in."""
    titles = [t for c in (p.get("contracts_list") or []) for t in (c.get("titles") or [])]
    haystack = " ".join([
        p.get("primary_cat", ""),
        " ".join(p.get("sector") or []),
        " ".join(p.get("client_groups") or []),
        " ".join(titles),
    ]).lower()
    hits = {c: bool(re.search(pattern, haystack)) for c, pattern in CATEGORY_TERMS.items()}
    hits["Other services"] = bool(re.search(OTHER_TERMS, haystack)) or not any(hits.values())
    return hits


def row_for(boroughs, p):
    ver = p.get("verification") or {}
    cats = categorise(p)
    return [
        p.get("name", ""),
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
        "; ".join(sorted(boroughs)),
        len(boroughs),
        ", ".join(p.get("councils") or []),
        p.get("council_count") or 0,
        p.get("contracts") or 0,
        p.get("hq_address", ""),
        p.get("description", ""),
    ]


def style_sheet(ws, title, header_row, tick_offset=None, n_rows=0):
    ws.cell(row=1, column=1, value=title).font = TITLE_FONT
    for i, (name, width) in enumerate(header_row, start=1):
        c = ws.cell(row=2, column=i, value=name)
        c.fill = CAT_FILL if name in CATEGORIES else HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = Alignment(vertical="center",
                                horizontal="center" if name in CATEGORIES else "left",
                                wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.row_dimensions[2].height = 42
    ws.freeze_panes = "A3"
    ws.auto_filter.ref = "A2:%s%d" % (get_column_letter(len(header_row)), max(n_rows + 2, 2))

    if tick_offset is not None:
        for i in range(tick_offset, tick_offset + len(CATEGORIES)):
            col = get_column_letter(i)
            dv = DataValidation(type="list", formula1='"%s"' % TICK, allow_blank=True)
            ws.add_data_validation(dv)
            dv.add("%s3:%s%d" % (col, col, n_rows + 2 + 500))


def main():
    data = json.loads(DUMP.read_text())

    # Union every borough each provider appears in, and hydrate from whichever
    # borough entry we saw it in first — the provider record is identical
    # everywhere it appears, so any copy will do.
    boroughs_by_id, provider_by_id = {}, {}
    for borough, rows in data.items():
        for item in rows:
            p = item["p"]
            boroughs_by_id.setdefault(p["id"], set()).add(borough)
            provider_by_id.setdefault(p["id"], p)

    wb = Workbook()
    ws = wb.active
    ws.title = "London providers"

    ordered = sorted(provider_by_id.values(),
                     key=lambda p: (-(p.get("contracts") or 0), p.get("name", "")))
    style_sheet(ws, "London providers — %d distinct" % len(ordered), COLUMNS,
                tick_offset=FIRST_TICK, n_rows=len(ordered))

    r = 3
    for p in ordered:
        row = row_for(boroughs_by_id[p["id"]], p)
        for i, v in enumerate(row, start=1):
            cell = ws.cell(row=r, column=i, value=v)
            if FIRST_TICK <= i < FIRST_TICK + len(CATEGORIES):
                cell.alignment = TICK_ALIGN
            elif i in (COLUMNS.index(("Boroughs (this workbook)", 60)) + 1,
                       COLUMNS.index(("All councils contracted", 60)) + 1):
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        r += 1

    wb.save(OUT)
    print("wrote %s" % OUT)
    print("  distinct providers: %d" % len(ordered))
    print("  with email        : %d" % sum(1 for p in ordered if p.get("email")))
    print("  with website      : %d" % sum(1 for p in ordered if p.get("website")))


if __name__ == "__main__":
    main()
