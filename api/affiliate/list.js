// GET /api/affiliate/list?token=ADMIN_TOKEN
// Returns all affiliates with earned/paid/balance totals. Admin-only.
import { sendJson, getQuery } from "../_lib/http.js";
import { listAffiliates, affiliateSummary } from "../_lib/affiliate.js";

export default async function handler(req, res) {
  if (req.method !== "GET") return sendJson(res, 405, { error: "method_not_allowed" });
  const q = getQuery(req);
  if (!process.env.ADMIN_TOKEN || q.token !== process.env.ADMIN_TOKEN) {
    return sendJson(res, 401, { error: "unauthorized" });
  }
  try {
    const affiliates = await listAffiliates();
    const rows = await Promise.all(
      affiliates.map(async (a) => {
        const { total_earned, total_paid, balance_owed } = await affiliateSummary(a.code);
        return { ...a, total_earned, total_paid, balance_owed };
      })
    );
    return sendJson(res, 200, { count: rows.length, affiliates: rows });
  } catch (e) {
    return sendJson(res, 500, { error: "list_failed", detail: String(e.message || e) });
  }
}
