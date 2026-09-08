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
