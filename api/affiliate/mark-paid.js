// POST /api/affiliate/mark-paid?token=ADMIN_TOKEN
// Body: { affiliate_code, commission_ids: [...], notes }
// Marks the given commissions as paid and creates a payout record.
import { sendJson, readBody, getQuery } from "../_lib/http.js";
import { markCommissionsPaid, savePayoutRecord, getCommissions } from "../_lib/affiliate.js";

export default async function handler(req, res) {
  if (req.method !== "POST") return sendJson(res, 405, { error: "method_not_allowed" });
  const q = getQuery(req);
  if (!process.env.ADMIN_TOKEN || q.token !== process.env.ADMIN_TOKEN) {
    return sendJson(res, 401, { error: "unauthorized" });
  }
  try {
    const body = await readBody(req);
    const { affiliate_code, commission_ids, notes = "" } = body;
    if (!affiliate_code || !Array.isArray(commission_ids) || commission_ids.length === 0) {
      return sendJson(res, 400, { error: "missing_fields", required: ["affiliate_code", "commission_ids"] });
    }
    const updated = await markCommissionsPaid(commission_ids);
    const amount_pence = updated.reduce((s, c) => s + c.commission_pence, 0);
    const payout = amount_pence > 0 ? await savePayoutRecord({ affiliate_code, amount_pence, notes }) : null;
    return sendJson(res, 200, { ok: true, marked_paid: updated.length, amount_pence, payout });
  } catch (e) {
    return sendJson(res, 500, { error: "mark_paid_failed", detail: String(e.message || e) });
  }
}
