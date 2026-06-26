// POST /api/affiliate/create?token=ADMIN_TOKEN
// Body: { name, email, code, rate_bps, max_months, notes }
// Creates a new affiliate record. Admin-only.
//
// rate_bps: basis points e.g. 2000 = 20%
// max_months: null = lifetime, 1 = first payment only, 12 = 12 renewals cap
import { sendJson, readBody, getQuery } from "../_lib/http.js";
import { createAffiliate, getAffiliate } from "../_lib/affiliate.js";

export default async function handler(req, res) {
  if (req.method !== "POST") return sendJson(res, 405, { error: "method_not_allowed" });
  const q = getQuery(req);
  if (!process.env.ADMIN_TOKEN || q.token !== process.env.ADMIN_TOKEN) {
    return sendJson(res, 401, { error: "unauthorized" });
  }
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
