// Postcode → council → region → provider matching.
// Ported from CareProviderSearch.jsx, with the paywall/unlock flow and the
// api.anthropic.com ping removed. Data comes from public/db.json (built by build_data.py).

import { normCouncil, COUNCIL_NORM_MAP, REGION_NORM, ASYLUM_MAP } from "./engine_maps.js";

// Resolve a UK postcode to its admin district + ONS region via postcodes.io.
export async function resolvePostcode(raw) {
  const clean = raw.trim().toUpperCase().replace(/\s+/g, "");
  if (!clean) throw new Error("empty");
  const res = await fetch(`https://api.postcodes.io/postcodes/${encodeURIComponent(clean)}`);
  const json = await res.json().catch(() => ({}));
  if (!res.ok || json.status !== 200 || !json.result) {
    const err = new Error("notfound");
    err.code = "notfound";
    throw err;
  }
  return json.result;
}

// Build the tiered provider list for a postcodes.io result, using the prebuilt db
// ({ c: council->[[name,cat,contracts]], r: region->[...], n: [...] }).
export function buildProviderList(apiData, db) {
  const adminDistrict = apiData.admin_district || "";
  const regionRaw = (apiData.region || "").toLowerCase().trim();
  const region = REGION_NORM[regionRaw] || null;
  const normDistrict = normCouncil(adminDistrict);

  // ── local: council-specific providers ──────────────────────────────────────
  let local = [];
  for (const [normKey, dbKeys] of Object.entries(COUNCIL_NORM_MAP)) {
    if (normDistrict && (normDistrict.includes(normKey) || normKey.includes(normDistrict))) {
      for (const dbKey of dbKeys) {
        if (db.c && db.c[dbKey]) {
          for (const p of db.c[dbKey]) local.push({ name: p[0], cat: p[1], contracts: p[2], tier: "local" });
        }
      }
    }
  }
  local = dedupe(local);

  // ── regional: providers covering this ONS region ───────────────────────────
  let regional = [];
  if (region && db.r && db.r[region]) {
    const seen = new Set(local.map((p) => p.name));
    for (const p of db.r[region]) {
      if (!seen.has(p[0])) { regional.push({ name: p[0], cat: p[1], contracts: p[2], tier: "regional" }); seen.add(p[0]); }
    }
  }

  // ── national: UK-wide providers + the region's Home Office asylum contractor ─
  const asylumContractor = region ? ASYLUM_MAP[region] : null;
  const seenNat = new Set([...local, ...regional].map((p) => p.name));
  let national = [];
  if (asylumContractor) {
    national.push({ name: asylumContractor, cat: "Asylum housing", contracts: null, tier: "national", badge: "Home Office contract" });
    seenNat.add(asylumContractor);
  }
  if (db.n) {
    for (const p of db.n) {
      if (!seenNat.has(p[0])) { national.push({ name: p[0], cat: p[1], contracts: p[2], tier: "national" }); seenNat.add(p[0]); }
    }
  }

  return {
    council: adminDistrict,
    region,
    postcode: apiData.postcode,
    local,
    regional,
    national,
    total: local.length + regional.length + national.length,
  };
}

function dedupe(list) {
  const seen = new Set();
  return list.filter((p) => (seen.has(p.name) ? false : (seen.add(p.name), true)));
}
