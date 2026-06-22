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

  const ok = stripe.configured && kv.persistent && kv.ok;
  return sendJson(res, ok ? 200 : 503, {
    ok,
    stripe,
    kv,
    checkedAt: new Date().toISOString(),
  });
}
