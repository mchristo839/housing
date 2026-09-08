// POST /api/webhook
// Stripe webhook handler. Register this URL in the Stripe dashboard.
// Required env vars: STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
//
// Handles:
//   checkout.session.completed  → one-off payments with affiliate ref
//   invoice.payment_succeeded   → subscription renewals with affiliate ref
//
// For each attributed payment, records a commission row and checks max_months cap.
import { getStripe } from "./_lib/billing.js";
import { getAffiliate, saveCommission, getRenewalCount, incrementRenewalCount } from "./_lib/affiliate.js";
import { recordSale } from "./_lib/db.js";
import { notifySale } from "./_lib/alerts.js";

const areaOf = (md = {}) => md.postcode || md.council || md.county || "";

function readRawBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(typeof c === "string" ? Buffer.from(c) : c));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.statusCode = 405;
    res.end("Method not allowed");
    return;
  }

  const stripe = getStripe();
  if (!stripe) {
    res.statusCode = 503;
    res.end(JSON.stringify({ error: "payments_not_configured" }));
    return;
  }

  let rawBody;
  if (req.body) {
    // Vercel may pre-parse; re-serialise for signature verification.
    rawBody = Buffer.from(typeof req.body === "string" ? req.body : JSON.stringify(req.body));
  } else {
    rawBody = await readRawBody(req);
  }

  const sig = req.headers["stripe-signature"];
  const secret = process.env.STRIPE_WEBHOOK_SECRET;

  let event;
  try {
    if (secret) {
      if (!sig) {
        res.statusCode = 400;
        res.end("Missing stripe-signature header");
        return;
      }
      event = stripe.webhooks.constructEvent(rawBody, sig, secret);
    } else {
      // No webhook secret set — parse the raw body directly (dev / initial setup only).
      event = JSON.parse(rawBody.toString());
    }
  } catch (e) {
    res.statusCode = 400;
    res.end(`Webhook signature error: ${e.message}`);
    return;
  }

  try {
    if (event.type === "checkout.session.completed") {
      await handleCheckoutSession(stripe, event.data.object);
    } else if (event.type === "invoice.payment_succeeded") {
      await handleInvoice(stripe, event.data.object);
    }
    res.statusCode = 200;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ received: true }));
  } catch (e) {
    console.error("Webhook handler error:", e);
    res.statusCode = 500;
    res.end(JSON.stringify({ error: "handler_failed", detail: String(e.message || e) }));
  }
}

async function handleCheckoutSession(stripe, session) {
  // Only attribute completed payments
  if (session.payment_status !== "paid" && session.mode !== "subscription") return;
  const md = session.metadata || {};
  const affiliate_code = md.affiliate_code;

  // Record every one-off sale in the admin ledger (subscription revenue is
  // recorded from invoice.payment_succeeded to avoid double-counting).
  if (session.mode !== "subscription") {
    try {
      const sale = await recordSale({
        stripe_id: session.payment_intent || session.id,
        email: session.customer_details?.email || session.customer_email || null,
        amount_pence: session.amount_total || 0,
        type: "one_off",
        tier: md.tier || null,
        affiliate_code: affiliate_code || null,
      });
      if (sale.fresh) await notifySale(sale, { area: areaOf(md) });
    } catch (e) { console.error("recordSale failed:", e); }
  }

  if (!affiliate_code) return;
  const affiliate = await getAffiliate(affiliate_code);
  if (!affiliate) return;

  // For subscriptions the first invoice is handled here, subsequent via invoice event.
  if (session.mode === "subscription") {
    // The first invoice is already handled by invoice.payment_succeeded; skip to avoid double-counting.
    return;
  }

  // One-off payment
  const gross_pence = session.amount_total || 0;
  const commission_pence = Math.round(gross_pence * affiliate.rate_bps / 10000);

  await saveCommission({
    affiliate_code,
    stripe_id: session.payment_intent || session.id,
    stripe_customer: session.customer || null,
    gross_pence,
    commission_pence,
    type: "one_off",
    month_num: 1,
  });
}

async function handleInvoice(stripe, invoice) {
  if (invoice.status !== "paid" || !invoice.subscription) return;
  const md = invoice.subscription_details?.metadata || {};
  const affiliate_code = md.affiliate_code;

  try {
    const sale = await recordSale({
      stripe_id: invoice.id,
      email: invoice.customer_email || null,
      amount_pence: invoice.amount_paid || 0,
      type: "subscription",
      tier: md.tier || null,
      affiliate_code: affiliate_code || null,
    });
    if (sale.fresh) await notifySale(sale, { area: areaOf(md), renewal: invoice.billing_reason === "subscription_cycle" });
  } catch (e) { console.error("recordSale failed:", e); }

  if (!affiliate_code) return;

  const affiliate = await getAffiliate(affiliate_code);
  if (!affiliate) return;

  const stripe_customer = invoice.customer;
  const current_count = await getRenewalCount(affiliate_code, stripe_customer);

  // Enforce max_months cap (null = lifetime)
  if (affiliate.max_months != null && current_count >= affiliate.max_months) return;

  const new_count = await incrementRenewalCount(affiliate_code, stripe_customer);
  const gross_pence = invoice.amount_paid || 0;
  const commission_pence = Math.round(gross_pence * affiliate.rate_bps / 10000);
  const type = new_count === 1 ? "subscription_first" : "subscription_renewal";

  await saveCommission({
    affiliate_code,
    stripe_id: invoice.id,
    stripe_customer,
    gross_pence,
    commission_pence,
    type,
    month_num: new_count,
  });
}
