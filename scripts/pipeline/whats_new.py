"""Step 3 — what has been added since last time, and who should hear about it.

Diffs the first-seen ledger, groups the new providers by council, then drafts
one email per customer covering only the areas that customer has actually
unlocked. Drafts are written to disk for approval; nothing is sent from here.

    python3 scripts/pipeline/whats_new.py                  # since the last run
    python3 scripts/pipeline/whats_new.py --since 2026-08-01
    python3 scripts/pipeline/whats_new.py --min-new 3      # skip thin updates

Customer areas come from the admin API when SITE_URL and ADMIN_TOKEN are set.
Without them the area report is still produced, so the run is useful even with
no credentials to hand.

Output, under data/updates/<date>/:
    report.json     new providers by council and region
    summary.md      the human-readable version, used as the PR body
    emails/*.md     one drafted email per customer, front-matter first
"""
import argparse
import datetime
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.pipeline.common import (  # noqa: E402
    LEDGER, PROVIDERS, UPDATES_DIR, council_key, is_council, read_json,
)

LAST_RUN = UPDATES_DIR / "last_run.json"
SITE_URL = (os.environ.get("SITE_URL") or "").rstrip("/")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN") or ""


def api(action, **params):
    if not (SITE_URL and ADMIN_TOKEN):
        return None
    qs = urllib.parse.urlencode({"action": action, "token": ADMIN_TOKEN, **params})
    url = "%s/api/admin?%s" % (SITE_URL, qs)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:                       # noqa: BLE001 — report and carry on
        print("  admin API %s failed: %s" % (action, e))
        return None


def customer_areas():
    """email -> the distinct areas they have unlocked. Empty when the admin API
    is not reachable, which leaves the area report as the useful output."""
    listing = api("customers")
    if not listing:
        return {}
    out = {}
    for c in listing.get("customers") or []:
        email = c.get("email")
        if not email or c.get("blocked"):
            continue
        detail = api("customer", email=email)
        if not detail:
            continue
        areas, seen = [], set()
        for row in detail.get("history") or []:
            label, key = row.get("area"), row.get("areaKey")
            if not key or key in seen:
                continue
            seen.add(key)
            areas.append({"label": label or key, "key": key})
        if areas:
            out[email] = areas
    return out


def serves(provider, area_key):
    """Does this provider hold a contract in the customer's area? Compared on the
    same loose council key the search uses, so "Havering" matches "LONDON
    BOROUGH OF HAVERING"."""
    k = council_key(area_key)
    if not k:
        return False
    for c in provider.get("contracts_list") or []:
        gk = council_key(c.get("council"))
        if gk and (gk == k or gk in k or k in gk):
            return True
        if c.get("county") and council_key(c["county"]) == k:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="YYYY-MM-DD (default: the last run)")
    ap.add_argument("--min-new", type=int, default=1,
                    help="don't draft an email below this many new providers")
    args = ap.parse_args()

    ledger = read_json(LEDGER, {})
    providers = read_json(PROVIDERS, [])
    if not ledger:
        print("no ledger yet — run scripts/pipeline/ingest.py first")
        return 1

    since = args.since or (read_json(LAST_RUN, {}) or {}).get("date")
    if not since:
        # First run: report on the newest date in the ledger rather than calling
        # every provider we have ever held "new".
        since = max(ledger.values())
        print("no previous run recorded — reporting on %s only" % since)

    new_ids = {pid for pid, seen in ledger.items() if seen >= since}
    by_id = {p["id"]: p for p in providers}
    new_providers = [by_id[i] for i in new_ids if i in by_id]

    by_council, by_region = defaultdict(list), defaultdict(int)
    for p in new_providers:
        for c in p.get("contracts_list") or []:
            # Awards also come from NHS bodies, portals and housing associations.
            # They are real, but they are not places a customer can search, so
            # they would only pad the report.
            if c.get("council") and is_council(c["council"]):
                by_council[c["council"]].append(p["name"])
            if c.get("region"):
                by_region[c["region"]] += 1

    today = datetime.date.today().isoformat()
    out_dir = UPDATES_DIR / today
    (out_dir / "emails").mkdir(parents=True, exist_ok=True)

    report = {
        "generated": today,
        "since": since,
        "new_providers": len(new_providers),
        "councils_affected": len(by_council),
        "by_council": {k: sorted(set(v)) for k, v in sorted(by_council.items())},
        "by_region": dict(sorted(by_region.items(), key=lambda x: -x[1])),
        "provider_names": sorted(p["name"] for p in new_providers),
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── drafts ───────────────────────────────────────────────────────────────
    areas = customer_areas()
    drafted, skipped_thin = 0, 0
    for email, cust_areas in sorted(areas.items()):
        hits = {}
        for a in cust_areas:
            matched = [p for p in new_providers if serves(p, a["key"])]
            if matched:
                hits[a["label"]] = matched
        total = sum(len(v) for v in hits.values())
        if total < args.min_new:
            skipped_thin += 1
            continue
        lines = [
            "---",
            "to: %s" % email,
            "subject: %d new providers added in your areas" % total,
            "areas: %s" % ", ".join(hits),
            "new_providers: %d" % total,
            "---",
            "",
            "Hi,",
            "",
            "A quick update — we've just finished this month's refresh of the "
            "provider database, and there are now %d providers in the areas you follow "
            "that weren't there last time." % total,
            "",
        ]
        for area, matched in sorted(hits.items()):
            lines.append("**%s** — %d new" % (area, len(matched)))
            for p in sorted(matched, key=lambda x: x["name"])[:10]:
                lines.append("  - %s" % p["name"])
            if len(matched) > 10:
                lines.append("  - ...and %d more" % (len(matched) - 10))
            lines.append("")
        lines += [
            "They're live now, with contact details and the contracts they hold, "
            "so you can open your areas and pick up the new entries.",
            "",
            "Thanks,",
            "Find a Housing Provider",
        ]
        safe = email.replace("@", "_at_").replace("/", "_")
        (out_dir / "emails" / ("%s.md" % safe)).write_text("\n".join(lines), encoding="utf-8")
        drafted += 1

    # ── summary, used as the PR body ─────────────────────────────────────────
    md = [
        "# Data refresh — %s" % today,
        "",
        "**%d new providers** since %s, across **%d councils**."
        % (len(new_providers), since, len(by_council)),
        "",
    ]
    if by_region:
        md += ["| Region | New providers |", "|---|---|"]
        md += ["| %s | %d |" % (r, n) for r, n in report["by_region"].items()]
        md.append("")
    if by_council:
        md += ["## By council", "", "| Council | New providers |", "|---|---|"]
        md += ["| %s | %d |" % (c, len(set(v))) for c, v in sorted(by_council.items())]
        md.append("")
    if areas:
        md += ["## Customer emails drafted", "",
               "%d drafted, %d skipped as too thin (under %d new providers in their areas)."
               % (drafted, skipped_thin, args.min_new),
               "", "Drafts are in `data/updates/%s/emails/`. Nothing has been sent — "
               "review them, then run the send workflow." % today, ""]
    else:
        md += ["## Customer emails", "",
               "Not drafted: the admin API was unreachable, so customer areas are unknown. "
               "Set `SITE_URL` and `ADMIN_TOKEN` and re-run to draft them.", ""]
    (out_dir / "summary.md").write_text("\n".join(md), encoding="utf-8")

    print("new providers since %s : %d" % (since, len(new_providers)))
    print("councils affected      : %d" % len(by_council))
    print("customer emails drafted: %d (%d too thin)" % (drafted, skipped_thin))
    (UPDATES_DIR / "last_run.json").write_text(
        json.dumps({"date": today, "since": since, "new_providers": len(new_providers)}, indent=2),
        encoding="utf-8")

    print("written                : %s" % out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
