// GET /api/admin?token=...&q=signups|purchases
// Light admin readout for the owner. Gated by ADMIN_TOKEN env var.
//   ?q=signups   → list of {email, areas, signed_up}
//   ?q=count     → counts of signups + purchases
import { sendJson, getQuery } from "./_lib/http.js";
import { listSignups } from "./_lib/db.js";

export default async function handler(req, res) {
  const q = getQuery(req);
  const token = q.token || "";
  if (!process.env.ADMIN_TOKEN || token !== process.env.ADMIN_TOKEN) {
    return sendJson(res, 401, { error: "unauthorized" });
  }
  try {
    if (q.q === "signups") {
      const rows = await listSignups();
      return sendJson(res, 200, { count: rows.length, rows });
    }
    if (q.q === "count" || !q.q) {
      const rows = await listSignups();
      return sendJson(res, 200, { signups: rows.length });
    }
    return sendJson(res, 400, { error: "unknown_query" });
  } catch (e) {
    return sendJson(res, 500, { error: "admin_failed", detail: String(e.message || e) });
  }
}
