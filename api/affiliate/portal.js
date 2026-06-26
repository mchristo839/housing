// GET /api/affiliate/portal?token=TOKEN
// Returns the affiliate's dashboard data — their info, commissions, payouts, and totals.
// Authenticated via 7-day magic-link token issued by /api/affiliate/send-link.
import { sendJson, getQuery } from "../_lib/http.js";
import { verifyToken, getAffiliate, affiliateSummary } from "../_lib/affiliate.js";

export default async function handler(req, res) {
  if (req.method !== "GET") return sendJson(res, 405, { error: "method_not_allowed" });
  const { token } = getQuery(req);
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
