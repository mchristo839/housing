"""Apply a researched contact-correction CSV to the provider records.

Takes the columns produced by a contact-verification pass — Provider, New email,
Previous email, Website, Phone, Confirmation, Notes — and writes the corrected
email, website and phone onto the matching provider.

    python3 scripts/apply_london_email_refresh.py <file.csv> [--dry-run]

Matching is by name, then by normalised name, then by the previous email. A row
that matches nothing is reported rather than guessed at. Safety check: where the
CSV names a previous email, it has to be the one actually on the record — if the
record has moved on since the research was done the row is skipped, so a stale
sheet cannot quietly undo newer work.
"""
import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROVIDERS = ROOT / "api/_data/providers.json"


def norm_name(s):
    s = unicodedata.normalize("NFKD", str(s)).lower()
    s = re.sub(r"\bt/a\b.*", "", s)
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\b(ltd|limited|cic|c\.i\.c|plc|llp|group|the)\b", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(w[:-1] if len(w) > 4 and w.endswith("s") else w for w in s.split())


def same_url(a, b):
    strip = lambda u: re.sub(r"^https?://(www\.)?", "", str(u or "").strip().lower()).rstrip("/")
    return strip(a) == strip(b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.csv_path, encoding="utf-8-sig") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("Provider") or "").strip()]

    providers = json.loads(PROVIDERS.read_text())
    by_exact = {p["name"].lower(): p for p in providers}
    by_norm = {}
    for p in providers:
        by_norm.setdefault(norm_name(p["name"]), []).append(p)
    by_email = {}
    for p in providers:
        if p.get("email"):
            by_email.setdefault(p["email"].strip().lower(), []).append(p)

    emails = websites = 0
    unmatched, stale, changes = [], [], []

    for r in rows:
        name = (r.get("Provider") or "").strip()
        new_email = (r.get("New email") or "").strip()
        prev_email = (r.get("Previous email") or "").strip()
        website = (r.get("Website") or "").strip()
        phone = (r.get("Phone") or "").strip()

        p = (by_exact.get(name.lower())
             or (by_norm.get(norm_name(name)) or [None])[0]
             or (by_email.get(prev_email.lower()) or [None])[0])
        if p is None:
            unmatched.append(name)
            continue

        current = (p.get("email") or "").strip()
        # Only trust the row if the record still holds the email it was researched
        # against. "Previous email" is sometimes a note rather than an address
        # (a contact-form URL, "general enquiries"), so only compare real ones.
        if prev_email and "@" in prev_email and current and current.lower() != prev_email.lower():
            stale.append((name, current, prev_email))
            continue

        before = (current, (p.get("website") or "").strip())
        if new_email and new_email.lower() != current.lower():
            p["email"] = new_email
            emails += 1
        if website and not same_url(website, p.get("website")):
            p["website"] = website
            p["website_unverified"] = False
            websites += 1
        if phone and not (p.get("phone") or "").strip():
            p["phone"] = phone
        if (p.get("email"), p.get("website")) != before:
            changes.append((name, before, (p.get("email"), p.get("website"))))

    print("rows read        : %d" % len(rows))
    print("emails replaced  : %d" % emails)
    print("websites corrected: %d" % websites)
    print("unmatched        : %d" % len(unmatched))
    for n in unmatched:
        print("   no provider matched: %s" % n)
    print("skipped as stale : %d" % len(stale))
    for n, cur, prev in stale:
        print("   %s — record holds %r, sheet expected %r" % (n, cur, prev))

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    PROVIDERS.write_text(json.dumps(providers))
    print("\nwritten: api/_data/providers.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
