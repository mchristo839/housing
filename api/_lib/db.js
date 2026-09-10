// Database layer — Vercel KV (Upstash Redis).
//
// One file holds every persistent-data operation so we can swap providers later
// without touching the API endpoints.
//
// FALLBACK: when KV env vars aren't set (local dev or before user provisions),
// we fall back to a process-local in-memory map so the API still functions —
// data won't persist across deploys, but everything works for testing.
//
// SETUP (production):
//   1. Vercel dashboard → Storage → Create Database → KV
//   2. Connect to the findahousingprovider project
//   3. Vercel auto-adds these env vars:
//        KV_URL, KV_REST_API_URL, KV_REST_API_TOKEN, KV_REST_API_READ_ONLY_TOKEN
//   4. Redeploy. Done.
//
// Keys we use:
//   signup:<email>          → { email, areas, signed_up, last_updated }
//   signups_index           → set of all signup emails
//   purchase:<session_id>   → { email, scope, tier, paid_at }
//   purchases:<email>       → set of session_ids for one customer
//   lead:<id>               → { email, source, area, created_at }
//   leads_index             → set of lead ids
//
// Add new keys here as the product grows.

let _kv = null;
export async function getKv() {
  if (_kv) return _kv;
  // Preference order:
  //   1. Vercel KV REST vars (KV_REST_API_URL/TOKEN) → @vercel/kv
  //   2. REDIS_URL (what the Vercel Marketplace Redis integration actually
  //      provides — this is what production has) → ioredis over TCP
  //   3. In-memory fallback for local dev without either
  if (process.env.KV_REST_API_URL && process.env.KV_REST_API_TOKEN) {
    try {
      const { kv } = await import('@vercel/kv');
      _kv = kv;
      return _kv;
    } catch { /* fall through */ }
  }
  if (process.env.REDIS_URL) {
    try {
      _kv = await makeIoredisKv(process.env.REDIS_URL);
      return _kv;
    } catch { /* fall through */ }
  }
  _kv = makeMemoryKv();
  return _kv;
}

// ioredis adapter exposing the same get/set/sadd/smembers/del surface as
// @vercel/kv. Raw Redis stores strings, so values are JSON-encoded here —
// callers keep working with plain objects either way.
async function makeIoredisKv(url) {
  const { default: Redis } = await import('ioredis');
  // Reuse one connection across warm serverless invocations.
  const client = globalThis.__fahp_redis__ || (globalThis.__fahp_redis__ =
    new Redis(url, {
      maxRetriesPerRequest: 2,
      connectTimeout: 5000,
      lazyConnect: false,
      enableOfflineQueue: true,
      // Upstash/managed Redis URLs are rediss:// (TLS) — ioredis handles via URL scheme
    }));
  return {
    async get(key) {
      const raw = await client.get(key);
      if (raw == null) return null;
      try { return JSON.parse(raw); } catch { return raw; }
    },
    async set(key, val) {
      return client.set(key, typeof val === 'string' ? val : JSON.stringify(val));
    },
    async sadd(key, ...members) { return client.sadd(key, ...members); },
    async smembers(key) { return client.smembers(key); },
    async del(key) { return client.del(key); },
  };
}

function makeMemoryKv() {
  // Minimal in-process store with the subset of methods we use
  const store = globalThis.__fahp_kv_mem__ || (globalThis.__fahp_kv_mem__ = new Map());
  const sets  = globalThis.__fahp_kv_sets__ || (globalThis.__fahp_kv_sets__ = new Map());
  return {
    async get(key)      { return store.get(key) ?? null; },
    async set(key, val) { store.set(key, val); return "OK"; },
    async sadd(key, ...members) {
      let s = sets.get(key) || new Set();
      for (const m of members) s.add(m);
      sets.set(key, s); return members.length;
    },
    async smembers(key) { return [...(sets.get(key) || new Set())]; },
    async del(key) { store.delete(key); sets.delete(key); return 1; },
  };
}

// ── Signups (notification list) ───────────────────────────────────────────────
export async function saveSignup(email, areas) {
  const kv = await getKv();
  const now = new Date().toISOString();
  const existing = await kv.get(`signup:${email}`);
  let row;
  if (existing) {
    // merge in any new areas (dedup by stringified shape)
    const seen = new Set((existing.areas || []).map((a) => JSON.stringify(a)));
    for (const a of areas) seen.add(JSON.stringify(a));
    row = { ...existing, areas: [...seen].map((s) => JSON.parse(s)), last_updated: now };
  } else {
    row = { email, areas, signed_up: now, last_updated: now };
  }
  await kv.set(`signup:${email}`, row);
  await kv.sadd("signups_index", email);
  return row;
}
export async function listSignups() {
  const kv = await getKv();
  const emails = await kv.smembers("signups_index");
  const rows = [];
  for (const e of emails) {
    const r = await kv.get(`signup:${e}`);
    if (r) rows.push(r);
  }
  return rows;
}

// ── Purchases (cached for analytics / repeat unlock) ──────────────────────────
export async function savePurchase(sessionId, info) {
  const kv = await getKv();
  await kv.set(`purchase:${sessionId}`, { ...info, paid_at: new Date().toISOString() });
  if (info.email) await kv.sadd(`purchases:${info.email}`, sessionId);
  return true;
}
export async function getPurchasesByEmail(email) {
  const kv = await getKv();
  const ids = await kv.smembers(`purchases:${email}`);
  const out = [];
  for (const id of ids) {
    const r = await kv.get(`purchase:${id}`);
    if (r) out.push(r);
  }
  return out;
}

// ── Sales ledger (written by the Stripe webhook for every successful payment) ──
//   sale:<id>     → { id, stripe_id, email, amount_pence, type, tier, affiliate_code, created_at }
//   sales_index   → set of sale ids
export async function recordSale({ stripe_id, email = null, amount_pence = 0, type, tier = null, affiliate_code = null, created_at = null }) {
  const kv = await getKv();
  // Idempotent per Stripe object — webhooks can be delivered more than once.
  const id = `sale_${stripe_id}`;
  const existing = await kv.get(`sale:${id}`);
  // `fresh` tells callers whether this call created the row (so alerts fire once).
  if (existing) return { ...existing, fresh: false };
  const row = { id, stripe_id, email, amount_pence, type, tier, affiliate_code, created_at: created_at || new Date().toISOString() };
  await kv.set(`sale:${id}`, row);
  await kv.sadd("sales_index", id);
  return { ...row, fresh: true };
}
export async function listSales() {
  const kv = await getKv();
  const ids = await kv.smembers("sales_index");
  const rows = [];
  for (const id of ids) {
    const r = await kv.get(`sale:${id}`);
    if (r) rows.push(r);
  }
  return rows.sort((a, b) => b.created_at.localeCompare(a.created_at));
}

// ── One-shot flags (e.g. "receipt already emailed for this payment") ─────────
// Returns true the first time a key is claimed, false afterwards.
export async function claimOnce(key) {
  const kv = await getKv();
  const k = `once:${key}`;
  if (await kv.get(k)) return false;
  await kv.set(k, new Date().toISOString());
  return true;
}

// ── Unlock audit log, fair-use counters, block list ──────────────────────────
//   unlock:<id>                    → { id, email, kind: unlock|pdf, area, areaKey, tier, ip, ua, at }
//   unlocks_by_email:<email>       → set of unlock ids
//   customers_index                → set of emails that have ever unlocked
//   fair_day:<email>:<YYYY-MM-DD>  → set of distinct areaKeys unlocked that day
//   fair_month:<email>:<YYYY-MM>   → set of distinct areaKeys unlocked that month
//   blocked:<email>                → { at, reason }      blocked_index → set of emails
//   fair_override:<email>          → { daily, monthly }  (null = defaults)
export const FAIR_USE = { daily: 30, monthly: 150, flagAt: 20 };
const dayKey = (d = new Date()) => d.toISOString().slice(0, 10);
const monthKey = (d = new Date()) => d.toISOString().slice(0, 7);
const lc = (e) => String(e || "").trim().toLowerCase();

export async function recordUnlock({ email, kind = "unlock", area = "", areaKey = "", tier = null, ip = null, ua = null }) {
  const kv = await getKv();
  const e = lc(email);
  if (!e) return null;
  const id = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const row = { id, email: e, kind, area, areaKey, tier, ip, ua: ua ? String(ua).slice(0, 160) : null, at: new Date().toISOString() };
  await kv.set(`unlock:${id}`, row);
  await kv.sadd(`unlocks_by_email:${e}`, id);
  await kv.sadd("customers_index", e);
  if (kind === "unlock" && areaKey) {
    await kv.sadd(`fair_day:${e}:${dayKey()}`, areaKey);
    await kv.sadd(`fair_month:${e}:${monthKey()}`, areaKey);
  }
  return row;
}

export async function fairUseStatus(email) {
  const kv = await getKv();
  const e = lc(email);
  const [day, month, override] = await Promise.all([
    kv.smembers(`fair_day:${e}:${dayKey()}`),
    kv.smembers(`fair_month:${e}:${monthKey()}`),
    kv.get(`fair_override:${e}`),
  ]);
  const limits = { daily: override?.daily ?? FAIR_USE.daily, monthly: override?.monthly ?? FAIR_USE.monthly };
  return { day: day.length, month: month.length, dayAreas: day, monthAreas: month, limits, override: override || null };
}

export async function setFairUseOverride(email, override) {
  const kv = await getKv();
  const e = lc(email);
  if (!override) { await kv.del(`fair_override:${e}`); return null; }
  const row = { daily: Number(override.daily) || FAIR_USE.daily, monthly: Number(override.monthly) || FAIR_USE.monthly };
  await kv.set(`fair_override:${e}`, row);
  return row;
}

export async function listUnlocks(email) {
  const kv = await getKv();
  const ids = await kv.smembers(`unlocks_by_email:${lc(email)}`);
  const rows = [];
  for (const id of ids) { const r = await kv.get(`unlock:${id}`); if (r) rows.push(r); }
  return rows.sort((a, b) => b.at.localeCompare(a.at));
}

export async function setBlocked(email, blocked, reason = "") {
  const kv = await getKv();
  const e = lc(email);
  if (blocked) { await kv.set(`blocked:${e}`, { at: new Date().toISOString(), reason }); await kv.sadd("blocked_index", e); }
  else { await kv.del(`blocked:${e}`); }
  return blocked;
}
export async function isBlocked(email) {
  const kv = await getKv();
  return !!(await kv.get(`blocked:${lc(email)}`));
}

// Per-customer summary for the admin Customers tab.
export async function listCustomers() {
  const kv = await getKv();
  const emails = await kv.smembers("customers_index");
  const out = [];
  for (const e of emails) {
    const rows = await listUnlocks(e);
    const unlocks = rows.filter((r) => r.kind === "unlock");
    const pdfs = rows.filter((r) => r.kind === "pdf");
    const [blocked, fair] = await Promise.all([kv.get(`blocked:${e}`), fairUseStatus(e)]);
    out.push({
      email: e,
      unlocks: unlocks.length, pdfs: pdfs.length,
      distinct_areas: new Set(unlocks.map((r) => r.areaKey).filter(Boolean)).size,
      today: fair.day, this_month: fair.month, limits: fair.limits, override: fair.override,
      last_seen: rows[0]?.at || null, last_ip: rows.find((r) => r.ip)?.ip || null,
      tier: rows.find((r) => r.tier)?.tier || null,
      blocked: blocked ? { at: blocked.at, reason: blocked.reason } : null,
    });
  }
  return out.sort((a, b) => String(b.last_seen).localeCompare(String(a.last_seen)));
}

// ── Free sample leads (one per email AND one per phone, ever) ────────────────
//   sample:<id>              → { id, name, email, phone, area, scope, ip, ua, at }
//   samples_index            → set of ids
//   sample_email:<email>     → id      sample_phone:<phoneKey> → id
//   sample_ip:<ip>:<day>     → set of ids (daily cap per IP against throwaway identities)
export const SAMPLE_IP_DAILY = 3;
export async function claimSample({ name, email, phone, phoneKey, area, scope, ip, ua }) {
  const kv = await getKv();
  const e = lc(email);
  const [byEmail, byPhone] = await Promise.all([kv.get(`sample_email:${e}`), kv.get(`sample_phone:${phoneKey}`)]);
  if (byEmail || byPhone) return { ok: false, reason: "already_used" };
  const ipKey = ip ? `sample_ip:${ip}:${dayKey()}` : null;
  if (ipKey && (await kv.smembers(ipKey)).length >= SAMPLE_IP_DAILY) return { ok: false, reason: "ip_limit" };
  const id = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const row = { id, name: String(name).slice(0, 80), email: e, phone, area, scope, ip, ua: ua ? String(ua).slice(0, 160) : null, at: new Date().toISOString() };
  await kv.set(`sample:${id}`, row);
  await kv.sadd("samples_index", id);
  await kv.set(`sample_email:${e}`, id);
  await kv.set(`sample_phone:${phoneKey}`, id);
  if (ipKey) await kv.sadd(ipKey, id);
  return { ok: true, row };
}
export async function listSamples() {
  const kv = await getKv();
  const ids = await kv.smembers("samples_index");
  const rows = [];
  for (const id of ids) { const r = await kv.get(`sample:${id}`); if (r) rows.push(r); }
  return rows.sort((a, b) => b.at.localeCompare(a.at));
}

// ── Monthly unlock metering (enforces capped subscription allowances) ─────────
// Tracks the DISTINCT areas a subscriber unlocks in a calendar month so we can
// enforce plan allowances (Starter 5 / Plus 10 / Unlimited ∞). Re-opening an
// area you already unlocked this month does not count again.
//   usage:<customer>:<YYYY-MM> → set of area keys unlocked that month
function currentMonth() {
  const d = new Date();
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}
export function areaKeyOf(scope) {
  // One unlock = one area. Postcodes collapse to their council so re-opening the
  // same area via a different postcode doesn't burn a second allowance.
  const raw = scope.council || scope.county || scope.postcode || "";
  return String(raw).toLowerCase().replace(/\s+/g, " ").trim();
}
// Returns { count, areas, has } for the customer's current month.
export async function unlockUsage(customer, month = currentMonth()) {
  const kv = await getKv();
  const areas = await kv.smembers(`usage:${customer}:${month}`);
  return { count: areas.length, areas, month };
}
// Decide + record an unlock against a monthly allowance.
//   allowance = Infinity for unlimited plans.
// Returns { allowed, count, allowance, repeat } where `repeat` means the area
// was already unlocked this month (always allowed, never recounted).
export async function meterUnlock(customer, allowance, areaKey, month = currentMonth()) {
  const kv = await getKv();
  const key = `usage:${customer}:${month}`;
  const existing = await kv.smembers(key);
  const repeat = existing.includes(areaKey);
  if (repeat) return { allowed: true, count: existing.length, allowance, repeat: true };
  if (existing.length >= allowance) {
    return { allowed: false, count: existing.length, allowance, repeat: false };
  }
  if (areaKey) await kv.sadd(key, areaKey);
  return { allowed: true, count: existing.length + 1, allowance, repeat: false };
}

// ── Health probe ──────────────────────────────────────────────────────────────
// Verifies the active KV backend can round-trip a value, so /api/health can tell
// us whether persistence is real (Vercel KV / Redis) or the in-memory fallback
// (which does NOT survive across serverless invocations — fine for local dev,
// not acceptable in production because subscription metering would silently reset).
export async function kvHealth() {
  const backend = (process.env.KV_REST_API_URL && process.env.KV_REST_API_TOKEN) ? "vercel-kv"
    : process.env.REDIS_URL ? "redis" : "memory";
  const kv = await getKv();
  const token = `probe-${Date.now()}`;
  let ok = false;
  try {
    await kv.set("health:probe", token);
    const back = await kv.get("health:probe");
    ok = String(back) === token;
    await kv.del("health:probe");
  } catch { ok = false; }
  return { backend, persistent: backend !== "memory", ok };
}

// ── Leads (free-tier sign-ups from the home page, future) ─────────────────────
export async function saveLead(email, source, area) {
  const kv = await getKv();
  const id = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  await kv.set(`lead:${id}`, { id, email, source, area, created_at: new Date().toISOString() });
  await kv.sadd("leads_index", id);
  return id;
}
