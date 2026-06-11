// POST /api/notify-signup  { email, areas: [...] }
// Persists to Vercel KV via api/_lib/db.js (falls back to in-memory if KV not set).
import { sendJson, readBody } from "./_lib/http.js";
import { saveSignup } from "./_lib/db.js";

export default async function handler(req, res) {
  if (req.method !== "POST") return sendJson(res, 405, { error: "method_not_allowed" });
  try {
    const body = await readBody(req);
    const email = (body.email || "").trim().toLowerCase();
    const areas = Array.isArray(body.areas) ? body.areas : [];
    if (!email || !email.includes("@")) return sendJson(res, 400, { error: "invalid_email" });
    const row = await saveSignup(email, areas);
    return sendJson(res, 200, { ok: true, signup: { email: row.email, areas: row.areas } });
  } catch (e) {
    return sendJson(res, 500, { error: "signup_failed", detail: String(e.message || e) });
  }
}
