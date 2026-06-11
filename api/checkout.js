// POST /api/checkout  { postcode|council|county, tier, addTemplates }
// Creates a Stripe Checkout session for a one-off payment.
//   tier:           postcode £29.99 / county £49.99 (passed through from UI)
//   addTemplates:   adds £12.00 "3 Outreach Email Templates" as a second line item
// Scope (postcode / council / county) is kept in metadata so /result can fetch it.
import { PRICING } from "./_lib/match.js";
import { getStripe } from "./_lib/billing.js";
import { sendJson, readBody, originOf } from "./_lib/http.js";

const TEMPLATES_ADD_ON = {
  amount: 1200,
  currency: "gbp",
  name: "3 Outreach Email Templates",
  description: "Three proven email templates for approaching supported-living and social-housing providers — sent immediately after checkout.",
};

export default async function handler(req, res) {
  if (req.method !== "POST") return sendJson(res, 405, { error: "method_not_allowed" });
  const stripe = getStripe();
  if (!stripe) return sendJson(res, 503, { error: "payments_not_configured" });

  try {
    const body = await readBody(req);
    const pc      = (body.postcode || "").trim();
    const council = (body.council || body.borough || "").trim();
    const county  = (body.county || "").trim();
    const tierKey = String(body.tier || "postcode").toLowerCase();
    const tier = PRICING[tierKey];
    if (!tier) return sendJson(res, 400, { error: "invalid_tier" });
    if (!pc && !council && !county) return sendJson(res, 400, { error: "missing_scope" });

    const origin = originOf(req);
    const scopeLabel = pc || council || county;

    const line_items = [{
      quantity: 1,
      price_data: {
        currency: tier.currency,
        unit_amount: tier.amount,
        product_data: {
          name: `Find a Housing Provider — ${tier.name} (${tier.label})`,
          description: `${tier.description} (${scopeLabel})`,
        },
      },
    }];

    if (body.addTemplates) {
      line_items.push({
        quantity: 1,
        price_data: {
          currency: TEMPLATES_ADD_ON.currency,
          unit_amount: TEMPLATES_ADD_ON.amount,
          product_data: {
            name: TEMPLATES_ADD_ON.name,
            description: TEMPLATES_ADD_ON.description,
          },
        },
      });
    }

    const metadata = {
      postcode: pc, council, county,
      tier: tierKey, scope: tierKey,
      addTemplates: body.addTemplates ? "1" : "0",
    };
    const session = await stripe.checkout.sessions.create({
      mode: "payment",
      line_items,
      allow_promotion_codes: true,
      metadata,
      payment_intent_data: { metadata },
      success_url: `${origin}/result?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${origin}/?cancelled=1`,
    });
    return sendJson(res, 200, { url: session.url });
  } catch (e) {
    return sendJson(res, 500, { error: "checkout_failed", detail: String(e.message || e) });
  }
}
