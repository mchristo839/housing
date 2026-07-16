// /api/affiliate/admin?token=ADMIN_TOKEN&action=...
// All admin-only affiliate operations, dispatched by ?action=
//   GET  ?action=list             → list all affiliates with totals
//   GET  ?action=detail&code=X    → one affiliate's full statement (commissions + payouts)
//   POST ?action=create           → create affiliate { name, email, code, rate_bps, max_months, notes }
//   POST ?action=update           → edit affiliate { code, rate_bps?, max_months?, name?, email?, notes? }
//   POST ?action=mark-paid        → mark commissions paid { affiliate_code, commission_ids, notes }
// token = admin session token (from /api/admin?action=login) or legacy ADMIN_TOKEN.
import { sendJson, readBody, getQuery } from "../_lib/http.js";
import { createAffiliate, getAffiliate, updateAffiliate, listAffiliates, affiliateSummary, markCommissionsPaid, savePayoutRecord } from "../_lib/affiliate.js";
import { verifyAdminToken } from "../_lib/adminAuth.js";

export default async function handler(req, res) {
  const q = getQuery(req);
  const who = await verifyAdminToken(q.token);
  if (!who) return sendJson(res, 401, { error: "unauthorized" });

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

  if (action === "detail") {
    if (req.method !== "GET") return sendJson(res, 405, { error: "method_not_allowed" });
    try {
      if (!q.code) return sendJson(res, 400, { error: "missing_code" });
      const affiliate = await getAffiliate(q.code);
      if (!affiliate) return sendJson(res, 404, { error: "not_found" });
      const summary = await affiliateSummary(affiliate.code);
      return sendJson(res, 200, { affiliate, ...summary });
    } catch (e) {
      return sendJson(res, 500, { error: "detail_failed", detail: String(e.message || e) });
    }
  }

  if (action === "update") {
    if (req.method !== "POST") return sendJson(res, 405, { error: "method_not_allowed" });
    try {
      const body = await readBody(req);
      const { code, ...patch } = body;
      if (!code) return sendJson(res, 400, { error: "missing_code" });
      if (patch.rate_bps != null && !(Number(patch.rate_bps) >= 0 && Number(patch.rate_bps) <= 10000)) {
        return sendJson(res, 400, { error: "invalid_rate", hint: "rate_bps must be 0–10000 (basis points, 2000 = 20%)" });
      }
      const row = await updateAffiliate(code, patch);
      if (!row) return sendJson(res, 404, { error: "not_found" });
      return sendJson(res, 200, { ok: true, affiliate: row });
    } catch (e) {
      return sendJson(res, 500, { error: "update_failed", detail: String(e.message || e) });
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

  return sendJson(res, 400, { error: "unknown_action", valid: ["list", "detail", "create", "update", "mark-paid"] });
}
