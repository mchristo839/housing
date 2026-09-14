// /api/admin — admin backend (login + dashboard data), dispatched by ?action=
//   POST ?action=login              { username, password } → { token, username }
//   GET  ?action=overview&token=…   → counts, revenue, signups, sales
//   GET  ?q=signups|count&token=…   → legacy readouts (ADMIN_TOKEN)
//
// Auth: `token` is either a session token from action=login (users defined in
// the ADMIN_USERS env var, e.g. "mario:pass1,paul:pass2") or the legacy
// ADMIN_TOKEN env var.
import { sendJson, getQuery, readBody } from "./_lib/http.js";
import { ensureSetup, syncLead, syncSignup, syncPurchase, syncBlocked, enabled as brevoEnabled, LISTS as BREVO_LISTS, EVENTS as BREVO_EVENTS } from "./_lib/brevo.js";
import { listSignups, listSales, recordSale, listCustomers, listUnlocks, setBlocked, setFairUseOverride, fairUseStatus, listSamples, listBlocked } from "./_lib/db.js";
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

// The latest sale per email is what decides their plan and list.
function dedupeSalesByEmail(sales) {
  const latest = new Map();
  for (const s of sales) {
    if (!s.email) continue;
    const e = String(s.email).toLowerCase();
    const cur = latest.get(e);
    if (!cur || String(s.created_at) > String(cur.created_at)) latest.set(e, s);
  }
  return [...latest.values()];
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
      const [signups, sales, leads] = await Promise.all([listSignups(), listSales(), listSamples()]);
      const revenue_pence = sales.reduce((s, r) => s + (r.amount_pence || 0), 0);
      return sendJson(res, 200, {
        username: who,
        signups: { count: signups.length, rows: signups },
        sales: { count: sales.length, revenue_pence, rows: sales, sync },
        leads: { count: leads.length, rows: leads },
      });
    }
    // ── Brevo: the customer record ───────────────────────────────────────────
    if (q.action === "brevo-status") {
      if (!brevoEnabled()) return sendJson(res, 200, { enabled: false });
      const setup = await ensureSetup({ force: q.force === "1" });
      const [leads, signups, sales, blocked] = await Promise.all([listSamples(), listSignups(), listSales(), listBlocked()]);
      return sendJson(res, 200, {
        enabled: true, setup, lists: BREVO_LISTS, events: BREVO_EVENTS,
        counts: { leads: leads.length, signups: signups.length, sales: sales.length, blocked: blocked.length },
      });
    }
    // Backfill everything already on our side into Brevo. Batched, because a
    // serverless call has seconds, not minutes: the admin page loops until done.
    if (q.action === "brevo-sync") {
      if (!brevoEnabled()) return sendJson(res, 400, { error: "brevo_disabled" });
      const stage = String(q.stage || "leads");
      const cursor = Math.max(0, parseInt(q.cursor || "0", 10) || 0);
      const batch = Math.min(50, Math.max(1, parseInt(q.batch || "25", 10) || 25));
      let rows;
      if (stage === "leads") rows = await listSamples();
      else if (stage === "signups") rows = await listSignups();
      else if (stage === "sales") rows = dedupeSalesByEmail(await listSales());
      else if (stage === "blocked") rows = await listBlocked();
      else return sendJson(res, 400, { error: "bad_stage" });
      const slice = rows.slice(cursor, cursor + batch);
      const errors = [];
      for (const r of slice) {
        try {
          const out = stage === "leads" ? await syncLead(r)
                    : stage === "signups" ? await syncSignup(r)
                    : stage === "sales" ? await syncPurchase(r)
                    : await syncBlocked(r.email || r);
          if (out && out.ok === false && !out.skipped) errors.push({ email: r.email || r, error: out.error || out.skipped || "failed" });
        } catch (e) { errors.push({ email: r.email || r, error: String(e.message || e) }); }
      }
      const next = cursor + slice.length;
      return sendJson(res, 200, { stage, total: rows.length, processed: next, done: next >= rows.length, next_cursor: next, errors });
    }

    // ── Customers: usage, block list, fair-use overrides ─────────────────────
    if (q.action === "customers") {
      return sendJson(res, 200, { customers: await listCustomers(), defaults: (await fairUseStatus("_")).limits });
    }
    if (q.action === "customer") {
      if (!q.email) return sendJson(res, 400, { error: "missing_email" });
      const [history, fair] = await Promise.all([listUnlocks(q.email), fairUseStatus(q.email)]);
      return sendJson(res, 200, { email: String(q.email).toLowerCase(), history, fair });
    }
    if (q.action === "block" || q.action === "unblock") {
      if (req.method !== "POST") return sendJson(res, 405, { error: "method_not_allowed" });
      const { email, reason = "" } = await readBody(req);
      if (!email) return sendJson(res, 400, { error: "missing_email" });
      await setBlocked(email, q.action === "block", `${reason} (by ${who})`.trim());
      // Mirror it in Brevo straight away so no automation can email them.
      if (q.action === "block") { try { await syncBlocked(email); } catch (e) { console.error("brevo syncBlocked:", e); } }
      return sendJson(res, 200, { ok: true, email: String(email).toLowerCase(), blocked: q.action === "block" });
    }
    if (q.action === "fair-use") {
      if (req.method !== "POST") return sendJson(res, 405, { error: "method_not_allowed" });
      const { email, daily, monthly, reset } = await readBody(req);
      if (!email) return sendJson(res, 400, { error: "missing_email" });
      const override = await setFairUseOverride(email, reset ? null : { daily, monthly });
      return sendJson(res, 200, { ok: true, email: String(email).toLowerCase(), override });
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
