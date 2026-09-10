// GET /api/health → operational readiness probe.
// Reports whether the two production dependencies are wired up, WITHOUT leaking
// any secret values (only booleans + the Stripe key mode + a live KV round-trip):
//   • Stripe   — is a secret key configured, and is it live or test mode?
//   • Database — is a persistent KV/Redis store connected, and does a set/get
//                round-trip actually succeed? (in-memory fallback → not ok)
// Returns 200 when everything needed to take real money is in place, else 503.
import { kvHealth } from "./_lib/db.js";
import { sendJson } from "./_lib/http.js";

export default async function handler(req, res) {
  const stripeKey = process.env.STRIPE_SECRET_KEY || "";
  const stripe = {
    configured: !!stripeKey,
    mode: stripeKey.startsWith("sk_live") ? "live"
        : stripeKey.startsWith("sk_test") ? "test" : null,
  };

  let kv;
  try { kv = await kvHealth(); }
  catch (e) { kv = { backend: "unknown", persistent: false, ok: false, error: String(e.message || e) }; }

  // Email (Brevo): is a key set, is it valid, and is our From address a
  // verified sender? Receipts, owner alerts and affiliate logins all depend on it.
  const email = await emailHealth();

  const ok = stripe.configured && kv.persistent && kv.ok;
  return sendJson(res, ok ? 200 : 503, {
    ok,
    stripe,
    kv,
    email,
    checkedAt: new Date().toISOString(),
  });
}

async function emailHealth() {
  const key = process.env.BREVO_API_KEY;
  const from = process.env.AFFILIATE_FROM_EMAIL || "hello@findahousingprovider.co.uk";
  const alertsTo = process.env.SALE_ALERT_EMAILS ? "custom" : "default (hello@)";
  if (!key) return { configured: false, from, alertsTo, keyValid: false, senderVerified: false };
  const headers = { "api-key": key, Accept: "application/json" };
  let keyValid = false, senderVerified = false, error = null;
  try {
    const acct = await fetch("https://api.brevo.com/v3/account", { headers });
    keyValid = acct.ok;
    if (!acct.ok) error = `account: HTTP ${acct.status}`;
    if (acct.ok) {
      const s = await fetch("https://api.brevo.com/v3/senders", { headers });
      if (s.ok) {
        const list = (await s.json()).senders || [];
        senderVerified = list.some((x) => String(x.email).toLowerCase() === from.toLowerCase() && x.active !== false);
        if (!senderVerified) error = `sender ${from} not in Brevo verified senders`;
      } else error = `senders: HTTP ${s.status}`;
    }
  } catch (e) { error = String(e.message || e); }
  return { configured: true, from, alertsTo, keyValid, senderVerified, ok: keyValid && senderVerified, error };
}
