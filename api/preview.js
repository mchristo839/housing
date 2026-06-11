// GET /api/preview?postcode=... OR ?council=... OR ?county=...
// Returns counts + price for any of three search modes.
import { resolvePostcode, matchResolved, matchByCouncil, matchByCounty, previewOf } from "./_lib/match.js";
import { sendJson, getQuery } from "./_lib/http.js";

export default async function handler(req, res) {
  try {
    const q = getQuery(req);
    const pc = (q.postcode || "").trim();
    const council = (q.council || q.borough || "").trim();
    const county = (q.county || "").trim();

    let m;
    if (pc) {
      const api = await resolvePostcode(pc);
      m = matchResolved(api);
    } else if (council) {
      m = matchByCouncil(council);
    } else if (county) {
      m = matchByCounty(county);
    } else {
      return sendJson(res, 400, { error: "missing_query" });
    }
    return sendJson(res, 200, previewOf(m));
  } catch (e) {
    if (e.code === "notfound") return sendJson(res, 404, { error: "not_found" });
    return sendJson(res, 500, { error: "server_error", detail: e.message });
  }
}
