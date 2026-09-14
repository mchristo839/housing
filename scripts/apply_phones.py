"""Merge scraped telephone numbers into providers.json.

Reads /tmp/claude-0/phones/out-*.json, validates every number against UK
numbering rules, normalises the spacing, and writes it onto the matching
provider. A provider that already has a phone number is never overwritten.

Dry run by default; pass --apply to write.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPLY = "--apply" in sys.argv
IN_DIR = Path("/tmp/claude-0/phones")

# Valid UK ranges. 01/02 geographic, 03 non-geographic, 07 mobile,
# 08 freephone/special, 09 premium (kept but flagged odd for a provider).
VALID_PREFIX = ("01", "02", "03", "07", "08")
# The 01 area codes that are four digits rather than five.
FOUR_DIGIT_AREA = {"0113", "0114", "0115", "0116", "0117", "0118", "0121",
                   "0131", "0141", "0151", "0161", "0191"}

def clean(raw):
    """Return a normalised UK number, or None if it is not a plausible one."""
    if not raw:
        return None
    s = str(raw).strip()
    if s.lower() in ("null", "none", "n/a", ""):
        return None
    # Keep digits and a leading +; drop extensions and everything after.
    s = re.split(r"(?i)\b(ext|extension|x)\b", s)[0]
    digits = re.sub(r"[^\d+]", "", s)
    if digits.startswith("+44"):
        digits = "0" + digits[3:]
    elif digits.startswith("0044"):
        digits = "0" + digits[4:]
    elif digits.startswith("44") and len(digits) == 12:
        digits = "0" + digits[2:]
    if not digits.startswith("0") or not digits[1:].isdigit():
        return None
    n = len(digits)
    # UK numbers are 10 or 11 digits including the leading 0 (01xxx are 10 or 11).
    if n not in (10, 11):
        return None
    if not digits.startswith(VALID_PREFIX):
        return None
    if len(set(digits[1:])) <= 1:          # 00000000000, 01111111111
        return None
    # Format the way the existing records read. Area codes are 3, 4 or 5 digits
    # long, so 01 numbers are split on the real boundary rather than guessed at:
    # 0161 496 0000 but 01234 567890.
    if digits.startswith("02"):                      # 020 7946 0000
        return "%s %s %s" % (digits[:3], digits[3:7], digits[7:])
    if digits.startswith("07"):                      # 07700 900123
        return "%s %s" % (digits[:5], digits[5:])
    if digits.startswith(("03", "08", "09")):        # 0333 000 0000
        return "%s %s %s" % (digits[:4], digits[4:7], digits[7:])
    if digits[:4] in FOUR_DIGIT_AREA and n == 11:    # 0161 496 0000
        return "%s %s %s" % (digits[:4], digits[4:7], digits[7:])
    return "%s %s" % (digits[:5], digits[5:])        # 01234 567890 / 01234 56789

def main():
    rows = []
    for f in sorted(IN_DIR.glob("out-*.json")):
        try:
            rows.extend(json.loads(f.read_text()))
        except Exception as e:
            print("could not read %s: %s" % (f.name, e))
    print("lookup rows read     : %d from %d files" % (len(rows), len(list(IN_DIR.glob("out-*.json")))))

    providers = json.loads((ROOT / "api/_data/providers.json").read_text())
    by_id = {p["id"]: p for p in providers}

    applied, rejected, already, unknown, blank = 0, [], 0, [], 0
    for r in rows:
        pid = r.get("id")
        p = by_id.get(pid)
        if p is None:
            unknown.append(pid)
            continue
        raw = r.get("phone")
        if not raw or str(raw).lower() == "null":
            blank += 1
            continue
        phone = clean(raw)
        if phone is None:
            rejected.append((p["name"], raw))
            continue
        if p.get("phone"):
            already += 1
            continue
        p["phone"] = phone
        if r.get("source"):
            note = "Phone from %s." % r["source"]
            p["notes"] = (p.get("notes") or "").strip()
            p["notes"] = (p["notes"] + " " + note).strip()
        applied += 1

    print("numbers applied      : %d" % applied)
    print("no number found      : %d" % blank)
    print("failed validation    : %d" % len(rejected))
    for name, raw in rejected[:15]:
        print("     - %s: %r" % (name, raw))
    if already:
        print("already had a phone  : %d (left alone)" % already)
    if unknown:
        print("unknown provider ids : %d %s" % (len(unknown), unknown[:5]))

    still = sum(1 for p in providers if not p.get("phone"))
    print("providers still without a phone: %d of %d" % (still, len(providers)))

    if APPLY:
        (ROOT / "api/_data/providers.json").write_text(json.dumps(providers))
        print("WRITTEN")
    else:
        print("dry run - nothing written (pass --apply)")

if __name__ == "__main__":
    main()
