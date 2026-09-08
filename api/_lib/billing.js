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

// Plan rank, highest allowance first. A customer can end up with more than one
// active subscription (each Checkout creates a new Customer), so access is
// always judged by their BEST plan, and metering keyed to that plan's customer.
const PLAN_RANK = { monthly_full: 3, monthly_plus: 2, monthly_starter: 1 };
const rankOf = (sub) => PLAN_RANK[sub.metadata?.tier] || 1;

// All Stripe customers + active subscriptions for an email, best plan first.
export async function bestActiveSubscriptionForEmail(stripe, email) {
  const clean = String(email || "").trim().toLowerCase();
  if (!clean) return { customers: [], subscriptions: [], best: null };
  const customers = (await stripe.customers.list({ email: clean, limit: 20 })).data;
  const subscriptions = [];
  for (const c of customers) {
    const subs = await stripe.subscriptions.list({ customer: c.id, status: "all", limit: 20 });
    for (const s of subs.data) if (ACTIVE_SUB.has(s.status)) subscriptions.push(s);
  }
  subscriptions.sort((a, b) => rankOf(b) - rankOf(a) || b.created - a.created);
  return { customers, subscriptions, best: subscriptions[0] || null };
}

// Does this email have access — either a completed one-off payment OR an
// active monthly subscription? Returns { active, subscription, purchases }.
// An active subscriber unlocks any area they search.
export async function purchasesForEmail(stripe, email) {
  const clean = String(email || "").trim().toLowerCase();
  if (!clean) return { active: false, purchases: [] };
  const { customers, best } = await bestActiveSubscriptionForEmail(stripe, clean);
  const purchases = [];
  const subscription = !!best;
  const customerId = best ? (typeof best.customer === "string" ? best.customer : best.customer?.id) : null;
  const tier = best ? (best.metadata?.tier || "monthly_starter") : null;
  for (const c of customers) {
    // One-off purchases?
    const intents = await stripe.paymentIntents.list({ customer: c.id, limit: 100 });
    for (const pi of intents.data) {
      if (pi.status === "succeeded" && pi.metadata?.tier) {
        purchases.push({
          tier: pi.metadata.tier,
          postcode: pi.metadata.postcode, council: pi.metadata.council, county: pi.metadata.county,
          createdAt: pi.created,
        });
      }
    }
  }
  // Guest one-off purchases: Checkout in payment mode doesn't create a Customer
  // unless asked to, so older purchases only exist as a Checkout Session.
  if (purchases.length === 0) {
    try {
      const sessions = await stripe.checkout.sessions.list({ customer_details: { email: clean }, limit: 100 });
      for (const s of sessions.data) {
        if (s.mode === "payment" && s.payment_status === "paid" && s.metadata?.tier) {
          purchases.push({ tier: s.metadata.tier, postcode: s.metadata.postcode, council: s.metadata.council, county: s.metadata.county, createdAt: s.created });
        }
      }
    } catch { /* lookup is best-effort */ }
  }
  return { active: subscription || purchases.length > 0, subscription, customerId, tier, email: clean, purchases };
}

// Paid Checkout Sessions, newest first — the source of truth for the sales
// ledger when the webhook hasn't delivered (or isn't registered yet).
export async function listPaidSessions(stripe, limit = 100) {
  const sessions = await stripe.checkout.sessions.list({ limit, expand: ["data.invoice"] });
  return sessions.data.filter((s) => s.payment_status === "paid" && s.status === "complete");
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
  // Monthly subscription — carry the searched scope through from metadata so
  // /result can immediately show the area the subscriber just searched.
  if (session.mode === "subscription") {
    const subId = typeof session.subscription === "string"
      ? session.subscription : session.subscription?.id;
    if (!subId) return { active: false, email };
    const sub = await stripe.subscriptions.retrieve(subId);
    return {
      active: ACTIVE_SUB.has(sub.status),
      email, customerId: sub.customer, status: sub.status,
      tier: md.tier || "monthly_starter",
      postcode: md.postcode || null,
      council: md.council || null,
      county: md.county || null,
    };
  }
  return { active: false, email };
}
