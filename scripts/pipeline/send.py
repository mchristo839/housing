"""Step 4 — send the approved drafts.

Deliberately separate from the rest of the pipeline and never run on a
schedule: the drafts are reviewed first, and only then is this run by hand (or
through the send-customer-update workflow, which needs a button press).

    python3 scripts/pipeline/send.py --date 2026-09-15            # dry run
    python3 scripts/pipeline/send.py --date 2026-09-15 --send     # actually send
    python3 scripts/pipeline/send.py --date 2026-09-15 --send --only a@b.com

Needs BREVO_API_KEY. Records who was sent to in the run's sent.json, and skips
them if the script is run twice, so a repeat run cannot double-mail anyone.
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.pipeline.common import UPDATES_DIR  # noqa: E402

API_KEY = os.environ.get("BREVO_API_KEY") or ""
FROM_EMAIL = os.environ.get("AFFILIATE_FROM_EMAIL") or "hello@findahousingprovider.co.uk"
FROM_NAME = "Find a Housing Provider"


def parse_draft(path):
    """Front matter, then the body. Returns None if the file is malformed rather
    than guessing at a recipient."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return None
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    if not meta.get("to") or not meta.get("subject"):
        return None
    return {"to": meta["to"], "subject": meta["subject"], "meta": meta, "body": m.group(2).strip()}


def to_html(body):
    """The drafts are written as light markdown; this is the small subset of it
    they actually use."""
    out = []
    for block in body.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if all(l.lstrip().startswith("- ") for l in block.splitlines() if l.strip()):
            items = "".join("<li>%s</li>" % l.lstrip()[2:].strip() for l in block.splitlines() if l.strip())
            out.append("<ul>%s</ul>" % items)
            continue
        lines = []
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("- "):
                lines.append("<li>%s</li>" % line[2:])
            else:
                lines.append(line)
        html = "<br>".join(lines)
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"(<li>.*</li>)", r"<ul>\1</ul>", html)
        out.append("<p>%s</p>" % html)
    return ('<div style="font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif;'
            'font-size:15px;line-height:1.55;color:#1c1c1c">%s</div>' % "".join(out))


def send_one(to, subject, html):
    payload = json.dumps({
        "sender": {"name": FROM_NAME, "email": FROM_EMAIL},
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": html,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email", data=payload,
        headers={"api-key": API_KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return True, r.status
    except urllib.error.HTTPError as e:
        return False, "%s %s" % (e.code, e.read().decode("utf-8", "replace")[:200])
    except Exception as e:                        # noqa: BLE001
        return False, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--send", action="store_true", help="actually send (default is a dry run)")
    ap.add_argument("--only", default=None, help="send to this address only")
    args = ap.parse_args()

    run_dir = UPDATES_DIR / args.date
    emails_dir = run_dir / "emails"
    if not emails_dir.exists():
        print("no drafts at %s" % emails_dir)
        return 1

    sent_path = run_dir / "sent.json"
    sent = json.loads(sent_path.read_text()) if sent_path.exists() else {}

    drafts = sorted(emails_dir.glob("*.md"))
    if not drafts:
        print("no drafts to send")
        return 0
    if args.send and not API_KEY:
        print("BREVO_API_KEY is not set — refusing to send")
        return 1

    ok = failed = skipped = 0
    for path in drafts:
        d = parse_draft(path)
        if not d:
            print("  MALFORMED  %s" % path.name)
            failed += 1
            continue
        if args.only and d["to"] != args.only:
            continue
        if d["to"] in sent:
            print("  already sent  %s (%s)" % (d["to"], sent[d["to"]]))
            skipped += 1
            continue
        if not args.send:
            print("  DRY RUN  %-34s %s" % (d["to"], d["subject"]))
            ok += 1
            continue
        good, info = send_one(d["to"], d["subject"], to_html(d["body"]))
        if good:
            sent[d["to"]] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            print("  sent     %-34s %s" % (d["to"], d["subject"]))
            ok += 1
        else:
            print("  FAILED   %-34s %s" % (d["to"], info))
            failed += 1

    if args.send:
        sent_path.write_text(json.dumps(sent, indent=2), encoding="utf-8")

    print("\n%s: %d ok, %d failed, %d already sent"
          % ("sent" if args.send else "dry run", ok, failed, skipped))
    if not args.send:
        print("nothing was sent — re-run with --send once the drafts are approved")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
