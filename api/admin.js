// /api/admin — admin backend (login + dashboard data), dispatched by ?action=
//   POST ?action=login              { username, password } → { token, username }
//   GET  ?action=overview&token=…   → counts, revenue, signups, sales
//   GET  ?q=signups|count&token=…   → legacy readouts (ADMIN_TOKEN)
//
// Auth: `token` is either a session token from action=login (users defined in
// the ADMIN_USERS env var, e.g. "mario:pass1,paul:pass2") or the legacy
// ADMIN_TOKEN env var.
import { sendJson, getQuery, readBody } from "./_lib/http.js";
import { listSignups, listSales, recordSale } from "./_lib/db.js";
import { getStripe, listPaidSessions } from "./_lib/billing.js";
import { verifyCredentials, createAdminSession, verifyAdminToken } from "./_lib/adminAuth.js";

// Pull paid Checkout Sessions straight from Stripe into the sales ledger.
// Keys match what the webhook writes (payment_intent for one-offs, invoice
// for subscriptions) so the two sources never double-count.
async function syncSalesFromStripe() {
  const stripe = getStripe();
  if (!stripe) return { synced: 0, error: "payments_not_configured" };
  const sessions = await listPaidSessions(stripe);
  let synced = 0;
  for (const s of sessions) {
    const md = s.metadata || {};
    const stripe_id = s.mode === "subscription"
      ? (typeof s.invoice === "string" ? s.invoice : s.invoice?.id) || s.id
      : (typeof s.payment_intent === "string" ? s.payment_intent : s.payment_intent?.id) || s.id;
    await recordSale({
      stripe_id,
      email: s.customer_details?.email || s.customer_email || null,
      amount_pence: s.amount_total || 0,
      type: s.mode === "subscription" ? "subscription" : "one_off",
      tier: md.tier || null,
      affiliate_code: md.affiliate_code || null,
      created_at: new Date(s.created * 1000).toISOString(),
    });
    synced++;
  }
  return { synced };
}

export default async function handler(req, res) {
  const q = getQuery(req);

  if (q.action === "login") {
    if (req.method !== "POST") return sendJson(res, 405, { error: "method_not_allowed" });
    try {
      const { username, password } = await readBody(req);
      if (!verifyCredentials(username, password)) {
        return sendJson(res, 401, { error: "bad_credentials" });
      }
      const token = await createAdminSession(username);
      return sendJson(res, 200, { ok: true, token, username: String(username).toLowerCase() });
    } catch (e) {
      return sendJson(res, 500, { error: "login_failed", detail: String(e.message || e) });
    }
  }

  const who = await verifyAdminToken(q.token);
  if (!who) return sendJson(res, 401, { error: "unauthorized" });

  try {
    if (q.action === "overview") {
      let sync = null;
      try { sync = await syncSalesFromStripe(); } catch (e) { sync = { error: String(e.message || e) }; }
      const [signups, sales] = await Promise.all([listSignups(), listSales()]);
      const revenue_pence = sales.reduce((s, r) => s + (r.amount_pence || 0), 0);
      return sendJson(res, 200, {
        username: who,
        signups: { count: signups.length, rows: signups },
        sales: { count: sales.length, revenue_pence, rows: sales, sync },
      });
    }
    // Legacy readouts
    if (q.q === "signups") {
      const rows = await listSignups();
      return sendJson(res, 200, { count: rows.length, rows });
    }
    if (q.q === "count" || (!q.q && !q.action)) {
      const rows = await listSignups();
      return sendJson(res, 200, { signups: rows.length });
    }
    return sendJson(res, 400, { error: "unknown_query" });
  } catch (e) {
    return sendJson(res, 500, { error: "admin_failed", detail: String(e.message || e) });
  }
}
