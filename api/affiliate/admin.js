// /api/affiliate/admin?token=ADMIN_TOKEN&action=...
// All admin-only affiliate operations, dispatched by ?action=
//   GET  ?action=list             → list all affiliates with totals
//   POST ?action=create           → create affiliate { name, email, code, rate_bps, max_months, notes }
//   POST ?action=mark-paid        → mark commissions paid { affiliate_code, commission_ids, notes }
import { sendJson, readBody, getQuery } from "../_lib/http.js";
import { createAffiliate, getAffiliate, listAffiliates, affiliateSummary, markCommissionsPaid, savePayoutRecord } from "../_lib/affiliate.js";

function checkAdmin(q, res) {
  if (!process.env.ADMIN_TOKEN || q.token !== process.env.ADMIN_TOKEN) {
    sendJson(res, 401, { error: "unauthorized" });
    return false;
  }
  return true;
}

export default async function handler(req, res) {
  const q = getQuery(req);
  if (!checkAdmin(q, res)) return;

  const action = q.action;

  if (action === "list") {
    if (req.method !== "GET") return sendJson(res, 405, { error: "method_not_allowed" });
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

  if (action === "create") {
    if (req.method !== "POST") return sendJson(res, 405, { error: "method_not_allowed" });
    try {
      const body = await readBody(req);
      const { name, email, code, rate_bps, max_months = null, notes = "" } = body;
      if (!name || !email || !code || rate_bps == null) {
        return sendJson(res, 400, { error: "missing_fields", required: ["name", "email", "code", "rate_bps"] });
      }
      const normCode = String(code).toUpperCase().replace(/[^A-Z0-9_-]/g, "");
      if (!normCode) return sendJson(res, 400, { error: "invalid_code" });
      const existing = await getAffiliate(normCode);
      if (existing) return sendJson(res, 409, { error: "code_taken", code: normCode });
      const row = await createAffiliate({ name, email, code: normCode, rate_bps: Number(rate_bps), max_months: max_months == null ? null : Number(max_months), notes });
      return sendJson(res, 201, { ok: true, affiliate: row });
    } catch (e) {
      return sendJson(res, 500, { error: "create_failed", detail: String(e.message || e) });
    }
  }

  if (action === "mark-paid") {
    if (req.method !== "POST") return sendJson(res, 405, { error: "method_not_allowed" });
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

  return sendJson(res, 400, { error: "unknown_action", valid: ["list", "create", "mark-paid"] });
}
