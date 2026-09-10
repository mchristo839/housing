// Owner alerts. Recipients come from SALE_ALERT_EMAILS (comma-separated);
// falls back to the site's hello@ mailbox so alerts always go somewhere.
import { sendEmail, FROM_EMAIL } from "./email.js";

const TIER_LABEL = {
  single_postcode: "One-off — single postcode (£26.99)",
  postcode: "One-off — area unlock",
  county: "One-off — county unlock",
  monthly_starter: "Subscription — Starter (£49/mo)",
  monthly_plus: "Subscription — Plus (£99/mo)",
  monthly_full: "Subscription — Unlimited (£199/mo)",
};

const gbp = (pence) => `£${((pence || 0) / 100).toFixed(2)}`;
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// Customer-facing confirmation + receipt. Sent by the webhook for every
// payment so buyers get a receipt even if Stripe's own emails are off.
// links: { receiptUrl, invoiceUrl, invoicePdf }
export async function sendCustomerReceipt(sale, { area = "", renewal = false, receiptUrl, invoiceUrl, invoicePdf } = {}) {
  if (!sale.email) return { ok: false, error: "no customer email" };
  const what = TIER_LABEL[sale.tier] || sale.tier || (sale.type === "subscription" ? "Subscription" : "One-off purchase");
  const isSub = sale.type === "subscription";
  const subject = renewal
    ? `Your Find a Housing Provider renewal — ${gbp(sale.amount_pence)}`
    : `Your Find a Housing Provider receipt — ${gbp(sale.amount_pence)}`;
  const links = [
    receiptUrl && `<a href="${esc(receiptUrl)}">View receipt</a>`,
    invoiceUrl && `<a href="${esc(invoiceUrl)}">View invoice</a>`,
    invoicePdf && `<a href="${esc(invoicePdf)}">Download invoice PDF</a>`,
  ].filter(Boolean).join(" &nbsp;·&nbsp; ");
  const access = isSub
    ? `Search any postcode, borough or county at <a href="https://www.findahousingprovider.co.uk">findahousingprovider.co.uk</a> — your plan unlocks it automatically. Manage or cancel any time via "Manage subscription" in the site footer.`
    : `Go to <a href="https://www.findahousingprovider.co.uk">findahousingprovider.co.uk</a>, search ${area ? `<b>${esc(area)}</b>` : "your area"} and the list unlocks. Coming back later? Use "Already bought? Unlock with your email" and enter <b>${esc(sale.email)}</b>.`;
  const html = `
    <div style="font-family:sans-serif;max-width:560px;color:#1a1a1a">
      <h2 style="margin:0 0 12px">${renewal ? "Thanks — your subscription has renewed" : "Thanks for your purchase"}</h2>
      <table style="border-collapse:collapse;margin-bottom:16px">
        <tr><td style="padding:4px 12px 4px 0;color:#666">Item</td><td style="padding:4px 0"><b>${esc(what)}</b></td></tr>
        ${area ? `<tr><td style="padding:4px 12px 4px 0;color:#666">Area</td><td style="padding:4px 0"><b>${esc(area)}</b></td></tr>` : ""}
        <tr><td style="padding:4px 12px 4px 0;color:#666">Amount</td><td style="padding:4px 0"><b>${esc(gbp(sale.amount_pence))}</b></td></tr>
        <tr><td style="padding:4px 12px 4px 0;color:#666">Date</td><td style="padding:4px 0">${esc(new Date(sale.created_at || Date.now()).toUTCString().slice(0, 16))}</td></tr>
        <tr><td style="padding:4px 12px 4px 0;color:#666">Reference</td><td style="padding:4px 0">${esc(sale.stripe_id)}</td></tr>
      </table>
      ${links ? `<p style="margin:0 0 16px">${links}</p>` : ""}
      <h3 style="margin:16px 0 6px;font-size:15px">How to access your list</h3>
      <p style="margin:0 0 16px;line-height:1.5">${access}</p>
      <p style="margin:0 0 16px;line-height:1.5">If you have trouble downloading the PDF or anything else isn't working, just reply to this email and we'll sort it.</p>
      <p style="color:#666;font-size:13px;margin:0">Find a Housing Provider · <a href="mailto:${esc(FROM_EMAIL)}">${esc(FROM_EMAIL)}</a></p>
    </div>`;
  try {
    const r = await sendEmail({ to: sale.email, subject, html });
    if (!r.ok) console.error("customer receipt not sent:", r);
    return r;
  } catch (e) {
    console.error("customer receipt failed:", e);
    return { ok: false, error: String(e.message || e) };
  }
}

// Customer follow-up after a free sample: recap + link to buy the full list.
export async function sendSampleFollowUp(lead, { area, council, total, scope = {}, pricing = {} }) {
  if (!lead.email) return { ok: false, error: "no email" };
  const site = "https://www.findahousingprovider.co.uk";
  const qs = scope.postcode ? `postcode=${encodeURIComponent(scope.postcode)}` : scope.council ? `council=${encodeURIComponent(scope.council)}` : `county=${encodeURIComponent(scope.county || area)}`;
  const link = `${site}/?${qs}`;
  const first = String(lead.name || "").trim().split(/\s+/)[0] || "there";
  const sp = pricing.singlePostcode;
  const plans = Object.values(pricing.monthly || {});
  const options = [
    sp && `<li><b>${esc(sp.label)} one-off</b> — every provider covering ${esc(area)}, pay once and download once. No subscription.</li>`,
    plans.length && `<li><b>Subscribe from ${esc(plans[0].label)}/month</b> — ${plans.map((p) => `${esc(p.name)} ${esc(p.label)}/mo (${esc(p.blurb.toLowerCase())})`).join(", ")}. Cancel anytime.</li>`,
  ].filter(Boolean).join("");
  const subject = `Your free sample for ${area} — get all ${total} providers`;
  const html = `
    <div style="font-family:sans-serif;max-width:560px;color:#1a1a1a">
      <h2 style="margin:0 0 12px">Thanks, ${esc(first)} — here's how to get the rest</h2>
      <p style="margin:0 0 16px;line-height:1.5">Your free sample shows 3 of the <b>${esc(String(total))}</b> supported-living and social-housing providers covering <b>${esc(council || area)}</b>, with names, contracts and verified contacts.</p>
      <p style="margin:0 0 8px;line-height:1.5">To get all ${esc(String(total))}:</p>
      <ul style="margin:0 0 20px;padding-left:20px;line-height:1.6">${options}</ul>
      <p style="margin:0 0 24px"><a href="${esc(link)}" style="display:inline-block;background:#2D6BFF;color:#fff;text-decoration:none;font-weight:700;padding:12px 20px;border-radius:8px">Get the full list for ${esc(area)} →</a></p>
      <p style="margin:0 0 16px;line-height:1.5;color:#666;font-size:13px">Or search any postcode, borough or county at <a href="${esc(site)}">findahousingprovider.co.uk</a>. Reply to this email if you have any questions.</p>
      <p style="color:#666;font-size:13px;margin:0">Find a Housing Provider · <a href="mailto:${esc(FROM_EMAIL)}">${esc(FROM_EMAIL)}</a></p>
    </div>`;
  try {
    const r = await sendEmail({ to: lead.email, subject, html });
    if (!r.ok) console.error("sample follow-up not sent:", r);
    return r;
  } catch (e) { console.error("sample follow-up failed:", e); return { ok: false, error: String(e.message || e) }; }
}

// Owner alert for a new free-sample lead (name, business email, mobile, area).
export async function notifyLead(lead) {
  const to = process.env.SALE_ALERT_EMAILS || FROM_EMAIL;
  const subject = `New lead: ${lead.name} (${lead.email}) — sample for ${lead.area}`;
  const rows = [["Name", lead.name], ["Business email", lead.email], ["Mobile", lead.phone], ["Area searched", lead.area], ["When", new Date(lead.at).toUTCString()], ["IP", lead.ip || "—"]];
  const html = `
    <h2 style="font-family:sans-serif;margin:0 0 12px">New free-sample lead</h2>
    <table style="font-family:sans-serif;border-collapse:collapse">
      ${rows.map(([k, v]) => `<tr><td style="padding:4px 12px 4px 0;color:#666">${esc(k)}</td><td style="padding:4px 0"><b>${esc(v)}</b></td></tr>`).join("")}
    </table>
    <p style="font-family:sans-serif;color:#666;font-size:13px;margin-top:16px">They downloaded a 3-provider sample and saw the prices. All leads: <a href="https://www.findahousingprovider.co.uk/admin">findahousingprovider.co.uk/admin</a> → Leads.</p>`;
  try {
    const r = await sendEmail({ to, subject, html });
    if (!r.ok) console.error("lead alert not sent:", r);
    return r;
  } catch (e) { console.error("lead alert failed:", e); return { ok: false }; }
}

// Owner alert when an account is unlocking areas unusually fast.
export async function notifyFairUse(email, { day, month, limits, area, tier, ip }) {
  const to = process.env.SALE_ALERT_EMAILS || FROM_EMAIL;
  const subject = `Heavy usage: ${email} has unlocked ${day} areas today`;
  const rows = [["Customer", email], ["Plan", tier || "—"], ["Areas today", `${day} (cap ${limits.daily})`], ["Areas this month", `${month} (cap ${limits.monthly})`], ["Latest area", area || "—"], ["IP", ip || "—"]];
  const html = `
    <h2 style="font-family:sans-serif;margin:0 0 12px">${esc(subject)}</h2>
    <table style="font-family:sans-serif;border-collapse:collapse">
      ${rows.map(([k, v]) => `<tr><td style="padding:4px 12px 4px 0;color:#666">${esc(k)}</td><td style="padding:4px 0"><b>${esc(v)}</b></td></tr>`).join("")}
    </table>
    <p style="font-family:sans-serif;color:#666;font-size:13px;margin-top:16px">They will be stopped automatically at the daily cap. To cut them off now or raise their limit: <a href="https://www.findahousingprovider.co.uk/admin">findahousingprovider.co.uk/admin</a> → Customers.</p>`;
  try {
    const r = await sendEmail({ to, subject, html });
    if (!r.ok) console.error("fair-use alert not sent:", r);
    return r;
  } catch (e) { console.error("fair-use alert failed:", e); return { ok: false }; }
}

// sale: a row from recordSale(); extra: { area, renewal }
export async function notifySale(sale, extra = {}) {
  const to = process.env.SALE_ALERT_EMAILS || FROM_EMAIL;
  const what = TIER_LABEL[sale.tier] || sale.tier || (sale.type === "subscription" ? "Subscription" : "One-off");
  const kind = extra.renewal ? "Renewal" : "New sale";
  const subject = `${kind}: ${gbp(sale.amount_pence)} — ${what}${extra.area ? ` — ${extra.area}` : ""}`;
  const rows = [
    ["Amount", gbp(sale.amount_pence)],
    ["Product", what],
    ["Customer", sale.email || "—"],
    ["Area", extra.area || "—"],
    ["Affiliate", sale.affiliate_code || "—"],
    ["Stripe ref", sale.stripe_id],
    ["When", new Date(sale.created_at || Date.now()).toUTCString()],
  ];
  const html = `
    <h2 style="font-family:sans-serif;margin:0 0 12px">${esc(kind)}: ${esc(gbp(sale.amount_pence))}</h2>
    <table style="font-family:sans-serif;border-collapse:collapse">
      ${rows.map(([k, v]) => `<tr><td style="padding:4px 12px 4px 0;color:#666">${esc(k)}</td><td style="padding:4px 0"><b>${esc(v)}</b></td></tr>`).join("")}
    </table>
    <p style="font-family:sans-serif;color:#666;font-size:13px;margin-top:16px">Full list: <a href="https://www.findahousingprovider.co.uk/admin">findahousingprovider.co.uk/admin</a></p>`;
  try {
    const r = await sendEmail({ to, subject, html });
    if (!r.ok) console.error("sale alert not sent:", r);
    return r;
  } catch (e) {
    console.error("sale alert failed:", e);
    return { ok: false, error: String(e.message || e) };
  }
}
