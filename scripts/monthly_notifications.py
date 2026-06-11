"""Monthly notification email runner.

Run this after each monthly data rebuild. It:
  1. Reads the notify-signups list (data/notify_signups.json)
  2. Compares current providers.json to the snapshot from last month
  3. For each user, finds NEW providers in their saved postcode / council / county
  4. Sends an email summarising what's new
  5. Saves a snapshot of providers.json so next month can diff again

USAGE:
  RESEND_API_KEY=re_... python scripts/monthly_notifications.py
  python scripts/monthly_notifications.py preview     # don't send, just print

SETUP:
  • Sign up at https://resend.com (free tier covers 3,000 emails/mo)
  • Set RESEND_API_KEY env var (or put in ~/.claude/settings.json env block)
  • Optionally: NOTIFY_FROM_EMAIL = "alerts@yourdomain.com" (after domain verify)
"""
import os, json, sys, requests, time
from pathlib import Path
from collections import defaultdict

SIGNUPS = Path('data/notify_signups.json')
PROVIDERS = Path('api/_data/providers.json')
SNAPSHOT = Path('data/verification/providers_last_month.json')
RESEND_KEY = os.environ.get('RESEND_API_KEY', '')
FROM_EMAIL = os.environ.get('NOTIFY_FROM_EMAIL', 'alerts@findahousingprovider.vercel.app')

def load_signups():
    if not SIGNUPS.exists(): return []
    return json.load(open(SIGNUPS, encoding='utf-8'))

def find_new_providers(prov_now, prov_last):
    """Return {provider_id: provider_dict} for providers added since last month."""
    last_ids = {p['id'] for p in prov_last}
    return {p['id']: p for p in prov_now if p['id'] not in last_ids}

def matches_scope(provider, scope):
    """True if a provider serves the user's saved area."""
    councils = [c.lower().strip() for c in (provider.get('councils') or [])]
    regions  = [r.lower().strip() for r in (provider.get('regions')  or [])]
    if scope.get('postcode'):
        # Can't precisely resolve postcode→council without postcodes.io
        # fall back to: any council match
        return False  # would need API call to resolve
    if scope.get('council'):
        c = scope['council'].lower().strip()
        return any(c in x or x in c for x in councils)
    if scope.get('county'):
        # Approximation: if provider serves any council whose name contains the county
        c = scope['county'].lower().strip()
        return any(c in x or x in c for x in councils)
    return False

def send_email(to_email, subject, html):
    if not RESEND_KEY:
        print(f"[DRY-RUN] Would send to {to_email}: {subject}")
        return True
    r = requests.post('https://api.resend.com/emails',
        headers={'Authorization': f'Bearer {RESEND_KEY}',
                 'Content-Type': 'application/json'},
        json={'from': FROM_EMAIL, 'to': to_email, 'subject': subject, 'html': html},
        timeout=30)
    if r.status_code in (200, 201):
        return True
    print(f"ERROR sending to {to_email}: {r.status_code} {r.text[:200]}")
    return False

def build_email_html(area_label, providers):
    rows = '\n'.join(
        f'<tr><td style="padding:8px;border-bottom:1px solid #eee;"><b>{p["name"]}</b><br>'
        f'<span style="font-size:13px;color:#666;">{p.get("primary_cat","")}</span></td>'
        f'<td style="padding:8px;border-bottom:1px solid #eee;font-size:13px;">'
        f'{(p.get("email") or p.get("phone") or "")[:50]}</td></tr>'
        for p in providers[:20])
    extra = f"<p>…and {len(providers)-20} more, all in your unlock report.</p>" if len(providers) > 20 else ""
    return f"""
    <div style="font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
      <h2 style="color:#1F4E79;">{len(providers)} new providers commissioned in {area_label}</h2>
      <p>This month's data refresh added the following supported-living and social-housing
         providers active in your watched area:</p>
      <table style="width:100%;border-collapse:collapse;">{rows}</table>
      {extra}
      <p style="margin-top:24px;">
        <a href="https://findahousingprovider.vercel.app" style="background:#1F4E79;color:#fff;padding:10px 18px;border-radius:6px;text-decoration:none;">See the full list →</a>
      </p>
      <p style="font-size:12px;color:#999;margin-top:32px;">
        You're receiving this because you signed up for alerts at findahousingprovider.vercel.app.
        Reply STOP to unsubscribe.
      </p>
    </div>
    """

def main():
    preview = (len(sys.argv) > 1 and sys.argv[1] == 'preview')
    signups = load_signups()
    if not signups:
        print("No signups yet."); return
    prov_now = json.load(open(PROVIDERS, encoding='utf-8'))
    if not SNAPSHOT.exists():
        # First run — save snapshot, send nothing
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        json.dump(prov_now, open(SNAPSHOT, 'w', encoding='utf-8'))
        print(f"First run — saved snapshot ({len(prov_now)} providers). No emails this month.")
        return

    prov_last = json.load(open(SNAPSHOT, encoding='utf-8'))
    new_providers = find_new_providers(prov_now, prov_last)
    print(f"New providers since last snapshot: {len(new_providers)}")

    sent = 0
    for s in signups:
        email = s.get('email')
        for scope in s.get('areas', []):
            label = scope.get('postcode') or scope.get('council') or scope.get('county') or 'your area'
            relevant = [p for p in new_providers.values() if matches_scope(p, scope)]
            if not relevant: continue
            subject = f"{len(relevant)} new providers in {label} this month"
            html = build_email_html(label, relevant)
            if preview:
                print(f"  WOULD SEND to {email}: {subject} ({len(relevant)} providers)")
            else:
                if send_email(email, subject, html):
                    sent += 1
                    time.sleep(0.2)

    if not preview:
        json.dump(prov_now, open(SNAPSHOT, 'w', encoding='utf-8'))
        print(f"\nEmails sent: {sent}.  Snapshot updated.")

if __name__ == '__main__':
    main()
