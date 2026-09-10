// /api/result  → full provider list, for verified purchases.
// Unlock paths (GET):
//   ?session_id=...            just paid via Checkout → verify session paid + load scope
//   ?email=...&postcode=...    returning customer → has any past purchase + load postcode
//   ?dev=1&postcode=...        local only, when ALLOW_DEV_UNLOCK=1
// Audit (POST): { event: "pdf", email, area }  → logs a PDF download
//
// Every unlock is written to the audit log, counted against fair-use caps
// (distinct areas per day / month, even on Unlimited), and refused outright for
// blocked accounts.
import { resolvePostcode, matchResolved, matchByCouncil, matchByCounty, fullResultOf, PLAN_ALLOWANCE } from "./_lib/match.js";
import { getStripe, sessionIsActive, purchasesForEmail } from "./_lib/billing.js";
import { sendJson, getQuery, readBody } from "./_lib/http.js";
import { savePurchase, recordSale, meterUnlock, areaKeyOf, claimOnce, recordUnlock, fairUseStatus, isBlocked, FAIR_USE } from "./_lib/db.js";
import { notifySale, notifyFairUse } from "./_lib/alerts.js";
import { timingSafeEqual } from "node:crypto";

// The owner's testing unlock. Only ever true for an exact match against a
// DEV_UNLOCK_KEY of at least 24 characters, compared in constant time so the
// key can't be recovered by timing. Local development uses ALLOW_DEV_UNLOCK=1,
// an env var that is never set in production.
function devKeyMatches(supplied) {
  const key = process.env.DEV_UNLOCK_KEY || "";
  if (key.length >= 24) {
    const a = Buffer.from(supplied), b = Buffer.from(key);
    if (a.length !== b.length) return false;
    try { return timingSafeEqual(a, b); } catch { return false; }
  }
  return process.env.ALLOW_DEV_UNLOCK === "1" && supplied === "1";
}

// One-off buyers may only re-open the area they paid for: the same postcode,
// or any postcode in the same council, or the council/county they bought.
const normPc = (s) => String(s || "").toUpperCase().replace(/\s+/g, "");
const same = (a, b) => !!a && !!b && String(a).trim().toLowerCase() === String(b).trim().toLowerCase();
export async function purchaseCoversArea(purchases, q, data) {
  for (const p of purchases || []) {
    if (p.postcode && q.postcode && normPc(p.postcode) === normPc(q.postcode)) return true;
    if (p.council && (same(p.council, data.council) || same(p.council, q.council))) return true;
    if (p.county && (same(p.county, data.countyName) || same(p.county, q.county))) return true;
    if (p.postcode && data.council) {
      try { if (same(matchResolved(await resolvePostcode(p.postcode)).council, data.council)) return true; } catch {}
    }
  }
  return false;
}

async function listFor(q) {
  // q can be { postcode } | { council } | { county }
  if (q.postcode) return fullResultOf(matchResolved(await resolvePostcode(q.postcode)));
  if (q.council)  return fullResultOf(matchByCouncil(q.council));
  if (q.county)   return fullResultOf(matchByCounty(q.county));
  const e = new Error("missing"); e.code = "notfound"; throw e;
}

const clientOf = (req) => ({
  ip: String(req.headers["x-forwarded-for"] || req.socket?.remoteAddress || "").split(",")[0].trim() || null,
  ua: req.headers["user-agent"] || null,
});
const areaLabel = (data, q) => data.postcode || q.postcode || data.council || q.council || data.countyName || q.county || "";

// Fair use: distinct areas per day / month, on every plan including Unlimited.
// Re-opening an area already counted today is always allowed. Returns null if
// OK, or the 402 payload to send.
export async function fairUseCheck(email, areaKey) {
  const s = await fairUseStatus(email);
  if (s.dayAreas.includes(areaKey)) return null;
  if (s.day >= s.limits.daily) return { error: "fair_use_limit", scope: "day", used: s.day, limit: s.limits.daily };
  if (s.month >= s.limits.monthly && !s.monthAreas.includes(areaKey)) return { error: "fair_use_limit", scope: "month", used: s.month, limit: s.limits.monthly };
  return null;
}

// Log the unlock, then alert the owner once per day if usage looks like scraping.
async function logUnlock(req, { email, data, q, tier }) {
  const areaKey = areaKeyOf({ council: data.council, county: data.countyName, postcode: data.postcode || q.postcode });
  const { ip, ua } = clientOf(req);
  await recordUnlock({ email, kind: "unlock", area: areaLabel(data, q), areaKey, tier, ip, ua });
  const s = await fairUseStatus(email);
  if (s.day >= FAIR_USE.flagAt && await claimOnce(`fairflag:${email}:${new Date().toISOString().slice(0, 10)}`)) {
    await notifyFairUse(email, { day: s.day, month: s.month, limits: s.limits, area: areaLabel(data, q), tier, ip });
  }
}

export default async function handler(req, res) {
  try {
    // ── audit events from the client (PDF downloads) ──────────────────────────
    if (req.method === "POST") {
      const body = await readBody(req);
      if (body.event === "pdf" && body.email) {
        const { ip, ua } = clientOf(req);
        await recordUnlock({ email: body.email, kind: "pdf", area: String(body.area || "").slice(0, 80), ip, ua });
        return sendJson(res, 200, { ok: true });
      }
      return sendJson(res, 400, { error: "unknown_event" });
    }

    const q = getQuery(req);

    // Owner-only unlock, for testing the live site without paying.
    // Requires the exact DEV_UNLOCK_KEY secret in ?dev=. Without that env var
    // set there is no way in, and a wrong key is indistinguishable from an
    // ordinary unauthenticated request.
    if (q.dev != null && (q.postcode || q.council || q.county)) {
      if (devKeyMatches(String(q.dev))) {
        console.warn("dev unlock used:", { area: q.postcode || q.council || q.county, ip: String(req.headers["x-forwarded-for"] || "").split(",")[0].trim() || null, at: new Date().toISOString() });
        return sendJson(res, 200, { ...(await listFor(q)), subscribed: true, dev: true });
      }
      return sendJson(res, 403, { error: "forbidden" });
    }

    const stripe = getStripe();
    if (!stripe) return sendJson(res, 503, { error: "payments_not_configured" });

    // 1) just paid — verify via the checkout session
    if (q.session_id) {
      const session = await stripe.checkout.sessions.retrieve(q.session_id);
      const { active, email, tier, postcode, council, county, addTemplates, customerId } = await sessionIsActive(stripe, session);
      if (!active) return sendJson(res, 402, { error: "not_paid" });
      if (email && await isBlocked(email)) return sendJson(res, 403, { error: "account_blocked" });
      const scope = { postcode: postcode || q.postcode, council: council || q.council, county: county || q.county };
      if (!scope.postcode && !scope.council && !scope.county) {
        return sendJson(res, 200, { paid: true, email, tier, needPostcode: true });
      }
      // Record the purchase in the DB (best-effort; failure here doesn't block delivery)
      try { await savePurchase(q.session_id, { email, tier, scope, addTemplates }); } catch {}
      // Also write the sales ledger here so admin sees the sale even if the
      // Stripe webhook is late or not registered. Same keys as the webhook.
      try {
        const stripe_id = session.mode === "subscription"
          ? (typeof session.invoice === "string" ? session.invoice : session.invoice?.id) || session.id
          : (typeof session.payment_intent === "string" ? session.payment_intent : session.payment_intent?.id) || session.id;
        const sale = await recordSale({
          stripe_id, email, amount_pence: session.amount_total || 0,
          type: session.mode === "subscription" ? "subscription" : "one_off",
          tier, affiliate_code: session.metadata?.affiliate_code || null,
        });
        // Whichever of webhook / result lands first sends the one alert.
        if (sale.fresh) await notifySale(sale, { area: scope.postcode || scope.council || scope.county || "" });
      } catch {}
      const data = await listFor(scope);
      // Count this first unlock against a capped subscription's monthly allowance.
      if (session.mode === "subscription") {
        const allowance = PLAN_ALLOWANCE[tier] ?? Infinity;
        if (allowance !== Infinity && customerId) {
          try { await meterUnlock(customerId, allowance, areaKeyOf({ council: data.council, county: data.countyName, postcode: data.postcode })); } catch {}
        }
      }
      if (email) { try { await logUnlock(req, { email, data, q: scope, tier }); } catch {} }
      return sendJson(res, 200, { ...data, subscribed: true, paid: true, email, tier, addTemplates });
    }

    // 2) returning customer — verify a past purchase / active plan, then load the scope
    if (q.email && (q.postcode || q.council || q.county)) {
      if (await isBlocked(q.email)) return sendJson(res, 403, { error: "account_blocked" });
      const info = await purchasesForEmail(stripe, q.email);
      if (!info.active) return sendJson(res, 402, { error: "no_purchase", email: info.email });
      const data = await listFor(q);
      // Subscribers can open any area; one-off buyers only the area they bought.
      if (!info.subscription && !(await purchaseCoversArea(info.purchases, q, data))) {
        const purchased = info.purchases.map((p) => p.postcode || p.council || p.county).filter(Boolean);
        return sendJson(res, 402, { error: "area_not_purchased", email: info.email, purchased });
      }
      if (info.subscription) {
        const areaKey = areaKeyOf({ council: data.council, county: data.countyName, postcode: data.postcode || q.postcode });
        // Fair use applies to every plan, Unlimited included.
        const fair = await fairUseCheck(info.email, areaKey);
        if (fair) return sendJson(res, 402, { ...fair, tier: info.tier });
        // Enforce the monthly allowance for capped subscribers (Starter 5 / Plus 10).
        const allowance = PLAN_ALLOWANCE[info.tier] ?? Infinity;
        if (allowance !== Infinity) {
          const meter = await meterUnlock(info.customerId || info.email, allowance, areaKey);
          if (!meter.allowed) {
            return sendJson(res, 402, { error: "monthly_limit", tier: info.tier, used: meter.count, allowance: meter.allowance });
          }
        }
      }
      try { await logUnlock(req, { email: info.email, data, q, tier: info.tier }); } catch {}
      return sendJson(res, 200, { ...data, subscribed: true, paid: true, email: info.email, purchases: info.purchases, tier: info.tier });
    }

    return sendJson(res, 400, { error: "missing_params" });
  } catch (e) {
    if (e.code === "notfound") return sendJson(res, 404, { error: "postcode_not_found" });
    return sendJson(res, 500, { error: "server_error", detail: String(e.message || e) });
  }
}
