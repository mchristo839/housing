// Stripe helpers. One-off payments per area (postcode / county / region).
import Stripe from "stripe";

export function getStripe() {
  const key = process.env.STRIPE_SECRET_KEY;
  return key ? new Stripe(key) : null;
}

const ACTIVE_SUB = new Set(["active", "trialing", "past_due"]);

// Legacy — kept so old subscription callers still resolve gracefully.
export async function activeSubscriptionForEmail(stripe, email) {
  const clean = String(email || "").trim().toLowerCase();
  if (!clean) return { active: false };
  const customers = await stripe.customers.list({ email: clean, limit: 20 });
  for (const c of customers.data) {
    const subs = await stripe.subscriptions.list({ customer: c.id, status: "all", limit: 20 });
    if (subs.data.some((s) => ACTIVE_SUB.has(s.status))) {
      return { active: true, email: clean, customerId: c.id };
    }
  }
  return { active: false, email: clean };
}

// Has this email got any completed one-off payment for our checkout?
// We accept any successful payment_intent or checkout.session.completed.
export async function purchasesForEmail(stripe, email) {
  const clean = String(email || "").trim().toLowerCase();
  if (!clean) return { active: false, purchases: [] };
  const customers = await stripe.customers.list({ email: clean, limit: 20 });
  const purchases = [];
  for (const c of customers.data) {
    const intents = await stripe.paymentIntents.list({ customer: c.id, limit: 100 });
    for (const pi of intents.data) {
      if (pi.status === "succeeded" && pi.metadata?.tier) {
        purchases.push({
          tier: pi.metadata.tier,
          postcode: pi.metadata.postcode,
          createdAt: pi.created,
        });
      }
    }
  }
  return { active: purchases.length > 0, email: clean, purchases };
}

// Verify a one-off payment checkout session. Returns the tier + postcode + email
// metadata if the payment succeeded.
export async function sessionIsActive(stripe, session) {
  if (!session) return { active: false };
  const email = session.customer_details?.email || session.customer_email || null;
  const md = session.metadata || {};
  // One-off payment mode
  if (session.mode === "payment") {
    return {
      active: session.payment_status === "paid",
      email,
      tier: md.tier || "postcode",
      postcode: md.postcode || null,
      council: md.council || null,
      county: md.county || null,
      addTemplates: md.addTemplates === "1",
    };
  }
  // Legacy subscription path — kept so any in-flight subs still verify
  if (session.mode === "subscription") {
    const subId = typeof session.subscription === "string"
      ? session.subscription : session.subscription?.id;
    if (!subId) return { active: false, email };
    const sub = await stripe.subscriptions.retrieve(subId);
    return { active: ACTIVE_SUB.has(sub.status), email, customerId: sub.customer, status: sub.status };
  }
  return { active: false, email };
}
