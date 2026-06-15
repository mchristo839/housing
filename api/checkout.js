// POST /api/checkout  { postcode|council|county, tier, addTemplates }
// Creates a Stripe Checkout session.
//   tier "postcode"/"county"           → one-off payment for that area
//   tier "monthly_starter"/"monthly_full" → recurring monthly subscription
//   addTemplates                       → £12 add-on (one-off purchases only)
// The searched scope is kept in metadata so /result can load it after payment.
import { MONTHLY_PLANS, priceForCount, resolvePostcode, matchResolved, matchByCouncil, matchByCounty } from "./_lib/match.js";
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
    if (!pc && !council && !county) return sendJson(res, 400, { error: "missing_scope" });

    const origin = originOf(req);
    const scopeLabel = pc || council || county;
    const metadata = {
      postcode: pc, council, county,
      tier: tierKey, scope: tierKey,
      addTemplates: body.addTemplates ? "1" : "0",
    };

    // ── recurring monthly subscription ──────────────────────────────────────
    const plan = MONTHLY_PLANS[tierKey];
    if (plan) {
      const session = await stripe.checkout.sessions.create({
        mode: "subscription",
        line_items: [{
          quantity: 1,
          price_data: {
            currency: plan.currency,
            unit_amount: plan.amount,
            recurring: { interval: plan.interval },
            product_data: {
              name: `Find a Housing Provider — ${plan.name} (${plan.label}/mo)`,
              description: plan.description,
            },
          },
        }],
        allow_promotion_codes: true,
        metadata,
        subscription_data: { metadata },
        success_url: `${origin}/result?session_id={CHECKOUT_SESSION_ID}`,
        cancel_url: `${origin}/?cancelled=1`,
      });
      return sendJson(res, 200, { url: session.url });
    }

    // ── one-off area purchase — price scales with the result count ───────────
    // Recompute the area's provider count server-side so the charge always
    // matches what the buyer saw on the free preview (and can't be tampered with).
    let m;
    try {
      if (pc) m = matchResolved(await resolvePostcode(pc));
      else if (council) m = matchByCouncil(council);
      else if (county) m = matchByCounty(county);
    } catch (e) {
      return sendJson(res, 404, { error: "area_not_found" });
    }
    const price = priceForCount(m && m.total);
    if (!price) return sendJson(res, 400, { error: "nothing_to_unlock" });
    metadata.count = String(price.count);
    metadata.price = price.label;

    const line_items = [{
      quantity: 1,
      price_data: {
        currency: price.currency,
        unit_amount: price.amount,
        product_data: {
          name: `Find a Housing Provider — ${scopeLabel} (${price.count} providers)`,
          description: `Unlock all ${price.count} providers in ${scopeLabel} — names, commissioners, contracts and verified direct contacts.`,
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
