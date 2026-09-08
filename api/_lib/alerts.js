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
