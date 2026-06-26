// POST /api/affiliate/send-link  { email }
// Looks up an affiliate by email, generates a 7-day magic-link token, emails it.
// Uses Brevo transactional email (BREVO_API_KEY + AFFILIATE_FROM_EMAIL env vars).
import { sendJson, readBody, originOf } from "../_lib/http.js";
import { getAffiliateByEmail, createToken } from "../_lib/affiliate.js";

async function sendEmail({ to, subject, html, from, fromName }) {
  const apiKey = process.env.BREVO_API_KEY;
  if (!apiKey) return { ok: false, error: "BREVO_API_KEY not set" };
  const res = await fetch("https://api.brevo.com/v3/smtp/email", {
    method: "POST",
    headers: { "api-key": apiKey, "Content-Type": "application/json" },
    body: JSON.stringify({
      sender: { name: fromName || "Find a Housing Provider", email: from || process.env.AFFILIATE_FROM_EMAIL || "hello@findahousingprovider.co.uk" },
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
