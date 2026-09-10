// GET  /api/preview?postcode=... OR ?council=... OR ?county=...
//   Returns counts + price for any of three search modes.
// POST /api/preview  { postcode|council|county, name, email, phone }
//   Free sample: 3 full provider entries for the area, the rest as anonymised
//   stubs, plus pricing. One per business email AND one per mobile, ever;
//   a small daily cap per IP stops throwaway identities.
import { resolvePostcode, matchResolved, matchByCouncil, matchByCounty, previewOf, priceForCount, SINGLE_POSTCODE_PRICE, MONTHLY_PLANS } from "./_lib/match.js";
import { sendJson, getQuery, readBody } from "./_lib/http.js";
import { claimSample } from "./_lib/db.js";
import { notifyLead } from "./_lib/alerts.js";

const SAMPLE_SIZE = 3;

// Consumer mailbox providers — we want a business address.
const FREE_MAIL = new Set(["gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "ymail.com", "rocketmail.com", "hotmail.com", "hotmail.co.uk",
  "outlook.com", "outlook.co.uk", "live.com", "live.co.uk", "msn.com", "icloud.com", "me.com", "mac.com", "aol.com", "aol.co.uk", "protonmail.com",
  "proton.me", "pm.me", "mail.com", "gmx.com", "gmx.co.uk", "gmx.de", "yandex.com", "yandex.ru", "zoho.com", "fastmail.com", "hey.com",
  "btinternet.com", "btopenworld.com", "sky.com", "talktalk.net", "virginmedia.com", "ntlworld.com", "blueyonder.co.uk", "tiscali.co.uk", "hushmail.com"]);
const DISPOSABLE_HINT = /(mailinator|guerrillamail|10minutemail|tempmail|temp-mail|trashmail|yopmail|dispostable|getnada|maildrop|sharklasers|throwaway)/i;
export function isBusinessEmail(email) {
  const e = String(email || "").trim().toLowerCase();
  const m = e.match(/^[^\s@]+@([^\s@]+\.[a-z]{2,})$/);
  if (!m) return false;
  const domain = m[1];
  if (FREE_MAIL.has(domain) || DISPOSABLE_HINT.test(domain)) return false;
  // yahoo.fr, hotmail.de, outlook.es …
  const label = domain.split(".")[0];
  if (["gmail", "googlemail", "yahoo", "hotmail", "outlook", "live", "icloud", "aol", "protonmail", "gmx", "yandex"].includes(label)) return false;
  return true;
}

// UK mobile → canonical key "447xxxxxxxxx" (or null if not a plausible mobile).
export function ukMobileKey(phone) {
  let d = String(phone || "").replace(/\D/g, "");
  if (d.startsWith("0044")) d = d.slice(2);
  if (d.startsWith("0")) d = "44" + d.slice(1);
  if (!/^447\d{9}$/.test(d)) return null;
  if (/^(\d)\1{8}$/.test(d.slice(3))) return null; // 07777777777 etc.
  return d;
}

function pickSample(m) {
  // Most useful first: local contracts by size, then county, regional, national.
  const byC = (a, b) => (b.contracts || 0) - (a.contracts || 0);
  const tiers = [["local", m.local], ["county", m.county], ["regional", m.regional], ["national", m.national]];
  const visible = [], hidden = [];
  for (const [tier, list] of tiers) {
    for (const p of [...(list || [])].sort(byC)) {
      if (visible.length < SAMPLE_SIZE) visible.push({ ...p, tier });
      else hidden.push({ tier, sector: p.sector || [], client_groups: p.client_groups || [], is_housing_association: !!p.is_housing_association, contracts: p.contracts || 0 });
    }
  }
  return { visible, hidden };
}

async function matchFor(pc, council, county) {
  if (pc) return matchResolved(await resolvePostcode(pc));
  if (council) return matchByCouncil(council);
  if (county) return matchByCounty(county);
  return null;
}

export default async function handler(req, res) {
  try {
    if (req.method === "POST") {
      const body = await readBody(req);
      const pc = String(body.postcode || "").trim();
      const council = String(body.council || body.borough || "").trim();
      const county = String(body.county || "").trim();
      const name = String(body.name || "").trim();
      const email = String(body.email || "").trim().toLowerCase();
      const phoneRaw = String(body.phone || "").trim();
      if (!pc && !council && !county) return sendJson(res, 400, { error: "missing_query" });
      if (name.length < 2) return sendJson(res, 400, { error: "invalid_name" });
      if (!isBusinessEmail(email)) return sendJson(res, 400, { error: "business_email_required" });
      const phoneKey = ukMobileKey(phoneRaw);
      if (!phoneKey) return sendJson(res, 400, { error: "invalid_mobile" });

      const m = await matchFor(pc, council, county);
      if (!m || !m.total) return sendJson(res, 400, { error: "nothing_to_sample" });
      const area = pc || council || county;
      const ip = String(req.headers["x-forwarded-for"] || "").split(",")[0].trim() || null;

      const claim = await claimSample({ name, email, phone: "+" + phoneKey, phoneKey, area, scope: { postcode: pc, council, county }, ip, ua: req.headers["user-agent"] });
      if (!claim.ok) return sendJson(res, claim.reason === "ip_limit" ? 429 : 409, { error: claim.reason });
      try { await notifyLead(claim.row); } catch {}

      const { visible, hidden } = pickSample(m);
      return sendJson(res, 200, {
        ok: true,
        area, council: m.council, countyName: m.countyName, region: m.region, postcode: m.postcode, total: m.total,
        visible, hidden,
        pricing: {
          oneOff: priceForCount(m.total),
          singlePostcode: pc ? SINGLE_POSTCODE_PRICE : null,
          monthly: MONTHLY_PLANS,
        },
        lead: { name, email },
      });
    }

    const q = getQuery(req);
    const pc = (q.postcode || "").trim();
    const council = (q.council || q.borough || "").trim();
    const county = (q.county || "").trim();
    const m = await matchFor(pc, council, county);
    if (!m) return sendJson(res, 400, { error: "missing_query" });
    return sendJson(res, 200, previewOf(m));
  } catch (e) {
    if (e.code === "notfound") return sendJson(res, 404, { error: "not_found" });
    return sendJson(res, 500, { error: "server_error", detail: e.message });
  }
}
