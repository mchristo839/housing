// Server-side matching + pricing. Loads the gated data from api/_data (never
// served publicly) and resolves a postcode to tiered, hydrated providers.
import { readFileSync } from "node:fs";
import { normCouncil, COUNCIL_NORM_MAP, REGION_NORM, ASYLUM_MAP } from "../../src/engine_maps.js";

const providers = JSON.parse(readFileSync(new URL("../_data/providers.json", import.meta.url)));
const db = JSON.parse(readFileSync(new URL("../_data/db.json", import.meta.url)));
const lha = JSON.parse(readFileSync(new URL("../_data/lha.json", import.meta.url)));
// complete, data-generated council map (covers every council that has contracts)
const COUNCIL_MAP = JSON.parse(readFileSync(new URL("../_data/councilmap.json", import.meta.url)));
const byId = new Map(providers.map((p) => [p.id, p]));
const byNameLc = new Map(providers.map((p) => [p.name.toLowerCase(), p]));

const COUNCIL_DROP = new Set(["council","borough","county","city","district","the","of",
  "metropolitan","unitary","authority","corporation","mbc","mdc","cc"]);
function normCouncilKey(s) {
  return String(s || "").toLowerCase().replace(/&/g, " and ").replace(/[^a-z0-9 ]/g, " ")
    .split(/\s+/).filter((t) => t && !COUNCIL_DROP.has(t)).join(" ");
}
function lhaFor(adminDistrict) {
  return lha[normCouncilKey(adminDistrict)] || null;
}

// ── per-area one-off pricing ─────────────────────────────────────────────
// Three tiers. User pays once, downloads the PDF for that scope.
//   postcode → just that council area (Local + Regional + National)
//   county   → every postcode in the county (all Local councils + Regional + National)
//   region   → every postcode in the region (full regional dataset)
export const PRICING = {
  postcode: {
    key: "postcode",
    amount: 2999,
    currency: "gbp",
    label: "£29.99",
    name: "Postcode",
    blurb: "All providers for one postcode",
    description: "Providers commissioned in this council area + regional & national operators serving it.",
  },
  county: {
    key: "county",
    amount: 4999,
    currency: "gbp",
    label: "£49.99",
    name: "County",
    blurb: "Every provider in the county",
    description: "All providers across every council in this county + regional & national operators.",
  },
  region: {
    key: "region",
    amount: 7999,
    currency: "gbp",
    label: "£79.99",
    name: "Region",
    blurb: "Every provider in the region",
    description: "Every provider across every council in this English region + national operators.",
  },
};

// ── recurring monthly plans (Stripe subscription mode) ───────────────────
// Sold alongside the one-off purchase on the paywall. An active subscriber
// unlocks any area they search while their plan is live.
export const MONTHLY_PLANS = {
  monthly_starter: {
    key: "monthly_starter",
    amount: 4999,
    currency: "gbp",
    interval: "month",
    label: "£49.99",
    name: "Monthly · Starter",
    blurb: "10 area searches every month",
    description: "10 area unlocks every month — postcode, borough or county. Cancel anytime.",
    searches: 10,
  },
  monthly_full: {
    key: "monthly_full",
    amount: 7999,
    currency: "gbp",
    interval: "month",
    label: "£79.99",
    name: "Monthly · Full access",
    blurb: "Unlimited area searches",
    description: "Unlimited area unlocks — postcode, borough or county. Cancel anytime.",
    searches: Infinity,
  },
};

// Back-compat shim while we migrate any callers expecting SUBSCRIPTION shape
export const SUBSCRIPTION = PRICING.postcode;

// ── postcode → admin district + region (postcodes.io) ────────────────────────
export async function resolvePostcode(raw) {
  const clean = String(raw || "").trim().toUpperCase().replace(/\s+/g, "");
  if (!clean) { const e = new Error("empty"); e.code = "notfound"; throw e; }
  const res = await fetch(`https://api.postcodes.io/postcodes/${encodeURIComponent(clean)}`);
  const json = await res.json().catch(() => ({}));
  if (!res.ok || json.status !== 200 || !json.result) {
    const e = new Error("notfound"); e.code = "notfound"; throw e;
  }
  return json.result;
}

function findContractor(name) {
  const lc = name.toLowerCase();
  if (byNameLc.has(lc)) return byNameLc.get(lc);
  const first = lc.split(/\s+/)[0];
  for (const p of providers) if (p.name.toLowerCase().includes(first)) return p;
  return null;
}

// ── resolve → tiered hydrated providers ──────────────────────────────────────
export function matchResolved(api) {
  const adminDistrict = api.admin_district || "";
  const regionRaw = (api.region || "").toLowerCase().trim();
  const region = REGION_NORM[regionRaw] || null;
  const normDistrict = normCouncil(adminDistrict);

  const used = new Set();
  const take = (ids) => {
    const out = [];
    for (const id of ids || []) if (!used.has(id)) { used.add(id); out.push(id); }
    return out;
  };

  // local: council-specific — use the complete generated map, with the hardcoded
  // COUNCIL_NORM_MAP as a fallback for any naming variants.
  //
  // EXACT-match on normalised council keys ONLY. The previous substring matcher
  // (normDistrict.includes(normKey) || normKey.includes(normDistrict)) leaked
  // county-council providers into Local — e.g. admin_district "Cambridge"
  // substring-matched the council key "cambridgeshire" (Cambridgeshire County
  // Council) and pulled in 123 county-level providers; "North East Lincolnshire"
  // matched "lincolnshire" the same way. Those county-tier providers correctly
  // surface via the County tier (db.county[admin_county]) — they shouldn't
  // double-up at Local.
  const localIds = [];
  const seenKey = new Set();
  const addFrom = (map) => {
    if (!normDistrict) return;
    for (const [normKey, dbKeys] of Object.entries(map)) {
      if (normKey === normDistrict) {
        for (const dbKey of dbKeys) if (db.c[dbKey] && !seenKey.has(dbKey)) { seenKey.add(dbKey); localIds.push(...db.c[dbKey]); }
      }
    }
  };
  addFrom(COUNCIL_MAP);
  addFrom(COUNCIL_NORM_MAP);
  const local = take(localIds);
  const adminCounty = api.admin_county || "";
  const cty = normCouncilKey(adminCounty);            // counties normalise like councils
  const countyIds = cty ? take(db.county[cty]) : [];
  const regional = region ? take(db.r[region]) : [];
  const national = take(db.n);

  // trim each provider's contract list to ONLY the postcode-relevant entries:
  //  • a contract with THIS council, or
  //  • a Regional-scope contract covering this region (pan-region, not a single other council), or
  //  • a National-scope contract.
  const ck = normCouncilKey(adminDistrict);
  const relevant = (list) => (list || []).filter((g) => {
    const gk = normCouncilKey(g.council);
    const councilMatch = ck && (gk.includes(ck) || ck.includes(gk));
    const countyMatch = g.scope === "County" && cty && normCouncilKey(g.county || "") === cty;
    const regionalMatch = g.scope === "Regional" && region && g.region === region;
    const nationalMatch = g.scope === "National";
    return councilMatch || countyMatch || regionalMatch || nationalMatch;
  });
  const hyd = (ids, tier) => ids.map((id) => {
    const p = byId.get(id);
    return { ...p, tier, contracts_list: relevant(p.contracts_list) };
  });
  const nat = hyd(national, "national");

  // Home Office asylum contractor for the region, pinned to the top of national
  const contractorName = region ? ASYLUM_MAP[region] : null;
  if (contractorName) {
    const p = findContractor(contractorName);
    if (p && !used.has(p.id)) {
      used.add(p.id);
      nat.unshift({ ...p, tier: "national", badge: "Home Office contract" });
    } else if (!p) {
      nat.unshift({
        id: `asylum-${contractorName.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
        name: contractorName, primary_cat: "Asylum housing", sector: ["Asylum housing"],
        scope: "National", tier: "national", badge: "Home Office contract",
        contracts: null, councils: [], regions: [], contracts_list: [],
        email: "", phone: "", website: "", description: `${contractorName} is the Home Office AASC accommodation contractor for ${region}.`,
      });
    }
  }

  return {
    council: adminDistrict,
    countyName: adminCounty,
    region,
    postcode: api.postcode,
    lha: lhaFor(adminDistrict),
    local: hyd(local, "local"),
    county: hyd(countyIds, "county"),
    regional: hyd(regional, "regional"),
    national: nat,
    total: local.length + countyIds.length + regional.length + nat.length,
  };
}

// ── Council-name → db key resolution (shared) ──────────────────────────────
// Two passes: exact match wins outright; only fall back to substring fuzz
// if nothing matched exactly (otherwise iteration order picks a wrong
// fuzzy hit before reaching the exact one).
function resolveCouncilDbKey(q) {
  let matchedKey = null, dbKeyHit = null;
  const findIn = (map, exactOnly) => {
    for (const [normKey, dbKeys] of Object.entries(map)) {
      const hit = exactOnly ? normKey === q : (normKey.includes(q) || q.includes(normKey));
      if (hit) {
        for (const k of dbKeys) if (db.c[k]) { matchedKey = normKey; dbKeyHit = k; return; }
      }
    }
  };
  findIn(COUNCIL_MAP, true);
  if (!dbKeyHit) findIn(COUNCIL_NORM_MAP, true);
  if (!dbKeyHit) findIn(COUNCIL_MAP, false);
  if (!dbKeyHit) findIn(COUNCIL_NORM_MAP, false);
  return { matchedKey, dbKeyHit };
}

// Metropolitan "counties" are groupings of unitary councils, not admin
// counties — they never appear in db.county. Resolve them as a union of
// their constituent councils so "Greater Manchester" or "West Yorkshire"
// behave the way a customer expects.
const METRO_COUNTIES = {
  "greater manchester": { region: "North West",
    councils: ["Manchester","Bolton","Bury","Oldham","Rochdale","Salford","Stockport","Tameside","Trafford","Wigan"] },
  "west yorkshire": { region: "Yorkshire & The Humber",
    councils: ["Leeds","Bradford","Calderdale","Kirklees","Wakefield"] },
  "south yorkshire": { region: "Yorkshire & The Humber",
    councils: ["Sheffield","Barnsley","Doncaster","Rotherham"] },
  "west midlands": { region: "West Midlands",
    councils: ["Birmingham","Coventry","Dudley","Sandwell","Solihull","Walsall","Wolverhampton"] },
  "merseyside": { region: "North West",
    councils: ["Liverpool","Knowsley","Sefton","St Helens","Wirral"] },
  "tyne and wear": { region: "North East",
    councils: ["Newcastle upon Tyne","Gateshead","North Tyneside","South Tyneside","Sunderland"] },
  "greater london": { region: "London", councils: [] },
  "london": { region: "London", councils: [] },
};

// ── Borough / Council direct lookup (no postcode needed) ───────────────────
// User types a council/borough name e.g. "Camden" or "Brighton and Hove" and
// we return everyone who holds a contract there, plus the relevant
// county/regional/national operators.
export function matchByCouncil(councilQuery) {
  const q = normCouncilKey(councilQuery);
  if (!q) { const e = new Error("empty"); e.code = "notfound"; throw e; }

  const { matchedKey, dbKeyHit } = resolveCouncilDbKey(q);
  if (!dbKeyHit) { const e = new Error("notfound"); e.code = "notfound"; throw e; }

  const used = new Set();
  const take = (ids) => { const out=[]; for (const id of ids||[]) if (!used.has(id)) { used.add(id); out.push(id); } return out; };
  const local = take(db.c[dbKeyHit] || []);

  // Derive region + county from this council's OWN contract entries.
  // (The previous approach — "which county list shares any provider with this
  // council" — leaked unrelated counties: a provider serving both Hounslow and
  // an Essex framework made Hounslow report countyName "essex" and pull in all
  // 112 Essex county providers.)
  const regionVotes = new Map(), countyVotes = new Map();
  for (const id of local) {
    const p = byId.get(id);
    for (const g of (p?.contracts_list || [])) {
      const gk = normCouncilKey(g.council);
      if (!(gk === matchedKey || gk.includes(matchedKey) || matchedKey.includes(gk))) continue;
      if (g.region) regionVotes.set(g.region, (regionVotes.get(g.region) || 0) + 1);
      if (g.county) countyVotes.set(g.county, (countyVotes.get(g.county) || 0) + 1);
    }
  }
  const top = (m) => [...m.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || "";
  const regionKey = top(regionVotes);
  const countyName = top(countyVotes);
  const countyKey = normCouncilKey(countyName);

  const countyIds = countyKey ? take(db.county[countyKey] || []) : [];
  const regional = regionKey ? take(db.r[regionKey] || []) : [];
  const national = take(db.n);

  const ck = matchedKey;
  const relevant = (list) => (list || []).filter((g) => {
    const gk = normCouncilKey(g.council);
    const councilMatch = ck && (gk.includes(ck) || ck.includes(gk));
    const countyMatch = g.scope === "County" && countyKey && normCouncilKey(g.county || "") === countyKey;
    const regionalMatch = g.scope === "Regional" && regionKey && g.region === regionKey;
    return councilMatch || countyMatch || regionalMatch || g.scope === "National";
  });
  const hyd = (ids, tier) => ids.map((id) => {
    const p = byId.get(id);
    return { ...p, tier, contracts_list: relevant(p.contracts_list) };
  });
  return {
    council: councilQuery, countyName, region: regionKey, postcode: "",
    local: hyd(local, "local"), county: hyd(countyIds, "county"),
    regional: hyd(regional, "regional"), national: hyd(national, "national"),
    total: local.length + countyIds.length + regional.length + national.length,
    lha: lhaFor(councilQuery),
  };
}

// ── County lookup ──────────────────────────────────────────────────────────
// User types a county e.g. "Kent" or "Greater Manchester" → all providers
// across every council in that county.
export function matchByCounty(countyQuery) {
  const cty = normCouncilKey(countyQuery);
  if (!cty) { const e = new Error("empty"); e.code = "notfound"; throw e; }

  // Metropolitan counties: union the constituent councils' local providers.
  const metro = METRO_COUNTIES[cty];
  if (metro && !db.county[cty]) {
    const used = new Set();
    const take = (ids) => { const out=[]; for (const id of ids||[]) if (!used.has(id)) { used.add(id); out.push(id); } return out; };
    const local = [];
    const memberKeys = [];
    for (const name of metro.councils) {
      const { matchedKey, dbKeyHit } = resolveCouncilDbKey(normCouncilKey(name));
      if (dbKeyHit) { memberKeys.push(matchedKey); local.push(...take(db.c[dbKeyHit] || [])); }
    }
    const regionKey = metro.region;
    const regional = regionKey ? take(db.r[regionKey] || []) : [];
    const national = take(db.n);
    const relevant = (list) => (list || []).filter((g) => {
      const gk = normCouncilKey(g.council);
      const councilMatch = memberKeys.some((mk) => gk === mk || gk.includes(mk) || mk.includes(gk));
      const regionalMatch = g.scope === "Regional" && g.region === regionKey;
      return councilMatch || regionalMatch || g.scope === "National";
    });
    const hyd = (ids, tier) => ids.map((id) => {
      const p = byId.get(id);
      return { ...p, tier, contracts_list: relevant(p.contracts_list) };
    });
    return {
      council: "", countyName: countyQuery, region: regionKey, postcode: "",
      local: hyd(local, "local"), county: [],
      regional: hyd(regional, "regional"), national: hyd(national, "national"),
      total: local.length + regional.length + national.length,
      lha: null,
    };
  }

  if (!db.county[cty]) {
    // Tolerant: look for the closest county key
    const keys = Object.keys(db.county || {});
    const fuzzy = keys.find((k) => k.includes(cty) || cty.includes(k));
    if (!fuzzy) { const e = new Error("notfound"); e.code = "notfound"; throw e; }
    return matchByCounty(fuzzy);
  }

  const used = new Set();
  const take = (ids) => { const out=[]; for (const id of ids||[]) if (!used.has(id)) { used.add(id); out.push(id); } return out; };
  const countyIds = take(db.county[cty]);

  // No Local tier on a county search: Local contract entries don't carry a
  // county field, so any council→county inference would be provider-overlap
  // guesswork (the same class of bug that made Hounslow report Essex).
  // County search = county-wide + regional + national; borough-level detail
  // comes from the postcode and borough searches.
  const local = [];

  // Region: vote from the county providers' own County-scope contract entries.
  const regionVotes = new Map();
  for (const id of countyIds) {
    const p = byId.get(id);
    for (const g of (p?.contracts_list || [])) {
      if (g.scope !== "County" || normCouncilKey(g.county || "") !== cty) continue;
      if (g.region) regionVotes.set(g.region, (regionVotes.get(g.region) || 0) + 1);
    }
  }
  const regionKey = [...regionVotes.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || "";
  const regional = regionKey ? take(db.r[regionKey] || []) : [];
  const national = take(db.n);

  const relevant = (list) => (list || []).filter((g) =>
    g.scope === "National" ||
    (g.scope === "Regional" && regionKey && g.region === regionKey) ||
    (g.scope === "County" && normCouncilKey(g.county || "") === cty) ||
    (g.scope === "Local"));
  const hyd = (ids, tier) => ids.map((id) => {
    const p = byId.get(id);
    return { ...p, tier, contracts_list: relevant(p.contracts_list) };
  });
  return {
    council: "", countyName: countyQuery, region: regionKey, postcode: "",
    local: hyd(local, "local"), county: hyd(countyIds, "county"),
    regional: hyd(regional, "regional"), national: hyd(national, "national"),
    total: local.length + countyIds.length + regional.length + national.length,
    lha: null,
  };
}

// counts + (public) LHA rates + subscription price — safe to return before payment
export function previewOf(m) {
  return {
    council: m.council,
    countyName: m.countyName,
    region: m.region,
    postcode: m.postcode,
    total: m.total,
    tiers: { local: m.local.length, county: m.county.length, regional: m.regional.length, national: m.national.length },
    pricing: PRICING,
    monthly: MONTHLY_PLANS,
    subscription: SUBSCRIPTION,  // back-compat for any older clients
    lha: m.lha,
  };
}

// full hydrated lists — only after payment is verified
export function fullResultOf(m) {
  return {
    council: m.council, countyName: m.countyName, region: m.region, postcode: m.postcode, total: m.total, lha: m.lha,
    local: m.local, county: m.county, regional: m.regional, national: m.national,
  };
}
