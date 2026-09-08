// Transactional email via Brevo. Shared by affiliate magic links and sale alerts.
// Requires BREVO_API_KEY. Sender defaults to the site's hello@ mailbox.

export const FROM_EMAIL = process.env.AFFILIATE_FROM_EMAIL || "hello@findahousingprovider.co.uk";

export async function sendEmail({ to, subject, html }) {
  const apiKey = process.env.BREVO_API_KEY;
  if (!apiKey) return { ok: false, error: "BREVO_API_KEY not set" };
  const recipients = (Array.isArray(to) ? to : String(to).split(","))
    .map((e) => e.trim()).filter(Boolean).map((email) => ({ email }));
  if (!recipients.length) return { ok: false, error: "no recipients" };
  const res = await fetch("https://api.brevo.com/v3/smtp/email", {
    method: "POST",
    headers: { "api-key": apiKey, "Content-Type": "application/json" },
    body: JSON.stringify({
      sender: { name: "Find a Housing Provider", email: FROM_EMAIL },
      to: recipients,
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
