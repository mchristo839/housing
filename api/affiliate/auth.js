// /api/affiliate/auth?action=...
// Public affiliate auth operations, dispatched by ?action=
//   POST ?action=send-link  { email }   → email a 7-day magic-link token
//   GET  ?action=portal&token=TOKEN     → return portal dashboard data
import { sendJson, readBody, getQuery, originOf } from "../_lib/http.js";
import { getAffiliateByEmail, createToken, verifyToken, getAffiliate, affiliateSummary } from "../_lib/affiliate.js";

async function sendEmail({ to, subject, html }) {
  const apiKey = process.env.BREVO_API_KEY;
  if (!apiKey) return { ok: false, error: "BREVO_API_KEY not set" };
  const res = await fetch("https://api.brevo.com/v3/smtp/email", {
    method: "POST",
    headers: { "api-key": apiKey, "Content-Type": "application/json" },
    body: JSON.stringify({
      sender: { name: "Find a Housing Provider", email: process.env.AFFILIATE_FROM_EMAIL || "hello@findahousingprovider.co.uk" },
      to: [{ email: to }],
      subject,
      htmlContent: html,
    }),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    return { ok: false, status: res.status, body };
  }
  return { ok: true };
}

export default async function handler(req, res) {
  const q = getQuery(req);
  const action = q.action;

  if (action === "send-link") {
    if (req.method !== "POST") return sendJson(res, 405, { error: "method_not_allowed" });
    try {
      const body = await readBody(req);
      const email = String(body.email || "").trim().toLowerCase();
      if (!email || !email.includes("@")) return sendJson(res, 400, { error: "invalid_email" });

      const affiliate = await getAffiliateByEmail(email);
      // Always respond 200 to avoid email enumeration
      if (!affiliate) return sendJson(res, 200, { ok: true });

      const token = await createToken(affiliate.code);
      const origin = originOf(req);
      const link = `${origin}/affiliate/portal?token=${token}`;

      await sendEmail({
        to: email,
        subject: "Your affiliate portal link",
        html: `
          <p>Hi ${affiliate.name},</p>
          <p>Here is your link to access the affiliate portal:</p>
          <p><a href="${link}">${link}</a></p>
          <p>This link is valid for 7 days.</p>
          <p>— Find a Housing Provider</p>
        `,
      });

      return sendJson(res, 200, { ok: true });
    } catch (e) {
      return sendJson(res, 500, { error: "send_failed", detail: String(e.message || e) });
    }
  }

  if (action === "portal") {
    if (req.method !== "GET") return sendJson(res, 405, { error: "method_not_allowed" });
    const { token } = q;
    if (!token) return sendJson(res, 401, { error: "missing_token" });
    try {
      const code = await verifyToken(token);
      if (!code) return sendJson(res, 401, { error: "invalid_or_expired_token" });

      const affiliate = await getAffiliate(code);
      if (!affiliate) return sendJson(res, 404, { error: "affiliate_not_found" });

      const { commissions, payouts, total_earned, total_paid, balance_owed } = await affiliateSummary(code);

      return sendJson(res, 200, {
        affiliate: { name: affiliate.name, email: affiliate.email, code: affiliate.code, rate_bps: affiliate.rate_bps, max_months: affiliate.max_months },
        commissions,
        payouts,
        total_earned,
        total_paid,
        balance_owed,
      });
    } catch (e) {
      return sendJson(res, 500, { error: "portal_failed", detail: String(e.message || e) });
    }
  }

  return sendJson(res, 400, { error: "unknown_action", valid: ["send-link", "portal"] });
}
