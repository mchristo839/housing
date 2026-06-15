// GET /api/result  → full provider list, for verified one-off purchases.
// Unlock paths:
//   ?session_id=...            just paid via Checkout → verify session paid + load scope
//   ?email=...&postcode=...    returning customer → has any past purchase + load postcode
//   ?dev=1&postcode=...        local only, when ALLOW_DEV_UNLOCK=1
import { resolvePostcode, matchResolved, matchByCouncil, matchByCounty, fullResultOf, PLAN_ALLOWANCE } from "./_lib/match.js";
import { getStripe, sessionIsActive, purchasesForEmail } from "./_lib/billing.js";
import { sendJson, getQuery } from "./_lib/http.js";
import { savePurchase, meterUnlock, areaKeyOf } from "./_lib/db.js";

async function listFor(q) {
  // q can be { postcode } | { council } | { county }
  if (q.postcode) return fullResultOf(matchResolved(await resolvePostcode(q.postcode)));
  if (q.council)  return fullResultOf(matchByCouncil(q.council));
  if (q.county)   return fullResultOf(matchByCounty(q.county));
  const e = new Error("missing"); e.code = "notfound"; throw e;
}

export default async function handler(req, res) {
  try {
    const q = getQuery(req);

    // dev-only unlock for local preview
    if (q.dev === "1" && process.env.ALLOW_DEV_UNLOCK === "1" && (q.postcode || q.council || q.county)) {
      return sendJson(res, 200, { ...(await listFor(q)), subscribed: true, dev: true });
    }

    const stripe = getStripe();
    if (!stripe) return sendJson(res, 503, { error: "payments_not_configured" });

    // 1) just paid — verify via the checkout session
    if (q.session_id) {
      const session = await stripe.checkout.sessions.retrieve(q.session_id);
      const { active, email, tier, postcode, council, county, addTemplates, customerId } = await sessionIsActive(stripe, session);
      if (!active) return sendJson(res, 402, { error: "not_paid" });
      const scope = { postcode: postcode || q.postcode, council: council || q.council, county: county || q.county };
      if (!scope.postcode && !scope.council && !scope.county) {
        return sendJson(res, 200, { paid: true, email, tier, needPostcode: true });
      }
      // Record the purchase in the DB (best-effort; failure here doesn't block delivery)
      try { await savePurchase(q.session_id, { email, tier, scope, addTemplates }); } catch {}
      const data = await listFor(scope);
      // Count this first unlock against a capped subscription's monthly allowance.
      if (session.mode === "subscription") {
        const allowance = PLAN_ALLOWANCE[tier] ?? Infinity;
        if (allowance !== Infinity && customerId) {
          try { await meterUnlock(customerId, allowance, areaKeyOf({ council: data.council, county: data.countyName, postcode: data.postcode })); } catch {}
        }
      }
      return sendJson(res, 200, { ...data, subscribed: true, paid: true, email, tier, addTemplates });
    }

    // 2) returning customer — verify a past purchase / active plan, then load the scope
    if (q.email && (q.postcode || q.council || q.county)) {
      const info = await purchasesForEmail(stripe, q.email);
      if (!info.active) return sendJson(res, 402, { error: "no_purchase", email: info.email });
      const data = await listFor(q);
      // Enforce the monthly allowance for capped subscribers (Starter 5 / Plus 10).
      if (info.subscription) {
        const allowance = PLAN_ALLOWANCE[info.tier] ?? Infinity;
        if (allowance !== Infinity) {
          const areaKey = areaKeyOf({ council: data.council, county: data.countyName, postcode: data.postcode || q.postcode });
          const meter = await meterUnlock(info.customerId || info.email, allowance, areaKey);
          if (!meter.allowed) {
            return sendJson(res, 402, { error: "monthly_limit", tier: info.tier, used: meter.count, allowance: meter.allowance });
          }
        }
      }
      return sendJson(res, 200, { ...data, subscribed: true, paid: true, email: info.email, purchases: info.purchases, tier: info.tier });
    }

    return sendJson(res, 400, { error: "missing_params" });
  } catch (e) {
    if (e.code === "notfound") return sendJson(res, 404, { error: "postcode_not_found" });
    return sendJson(res, 500, { error: "server_error", detail: String(e.message || e) });
  }
}
