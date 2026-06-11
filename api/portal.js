// POST /api/portal  { email }  → Stripe billing portal URL so subscribers can
// manage or cancel their subscription. Stripe-managed; no custom account system.
import { getStripe, activeSubscriptionForEmail } from "./_lib/billing.js";
import { sendJson, readBody, originOf } from "./_lib/http.js";

export default async function handler(req, res) {
  if (req.method !== "POST") return sendJson(res, 405, { error: "method_not_allowed" });
  const stripe = getStripe();
  if (!stripe) return sendJson(res, 503, { error: "payments_not_configured" });

  try {
    const { email } = await readBody(req);
    const { active, customerId } = await activeSubscriptionForEmail(stripe, email);
    if (!active || !customerId) return sendJson(res, 404, { error: "no_subscription" });
    const session = await stripe.billingPortal.sessions.create({
      customer: customerId,
      return_url: originOf(req),
    });
    return sendJson(res, 200, { url: session.url });
  } catch (e) {
    return sendJson(res, 500, { error: "portal_failed", detail: String(e.message || e) });
  }
}
