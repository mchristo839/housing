// Affiliate system — KV data layer.
//
// KV key schema:
//   affiliate:<code>              → { id, code, name, email, rate_bps, max_months, created_at }
//   affiliates_index              → set of codes
//   affiliate_email:<email>       → code  (reverse lookup for magic-link)
//   commission:<id>               → { id, affiliate_code, stripe_id, gross_pence, commission_pence, type, month_num, created_at, paid_at }
//   commissions:<code>            → set of commission ids
//   commission_months:<code>:<stripe_customer> → number of renewal months already credited
//   payout:<id>                   → { id, affiliate_code, amount_pence, paid_at, notes }
//   payouts:<code>                → set of payout ids
//   affiliate_token:<token>       → { code, expires }
//
// rate_bps: commission rate in basis points (e.g. 2000 = 20%).
// max_months: null = lifetime; 1 = first payment only; 12 = 12 renewals cap, etc.

import { randomBytes } from "node:crypto";

// ── shared KV access (reuse the same backend as db.js) ───────────────────────
let _kv = null;
async function getKv() {
  if (_kv) return _kv;
  if (process.env.KV_REST_API_URL && process.env.KV_REST_API_TOKEN) {
    try { const { kv } = await import("@vercel/kv"); _kv = kv; return _kv; } catch { /* fall through */ }
  }
  if (process.env.REDIS_URL) {
    try {
      const { default: Redis } = await import("ioredis");
      const client = globalThis.__fahp_redis__ || (globalThis.__fahp_redis__ =
        new Redis(process.env.REDIS_URL, { maxRetriesPerRequest: 2, connectTimeout: 5000, lazyConnect: false, enableOfflineQueue: true }));
      _kv = {
        async get(key) { const raw = await client.get(key); if (raw == null) return null; try { return JSON.parse(raw); } catch { return raw; } },
        async set(key, val) { return client.set(key, typeof val === "string" ? val : JSON.stringify(val)); },
        async sadd(key, ...members) { return client.sadd(key, ...members); },
        async smembers(key) { return client.smembers(key); },
        async del(key) { return client.del(key); },
        async incr(key) { return client.incr(key); },
        async get_int(key) { const v = await client.get(key); return v == null ? 0 : parseInt(v, 10) || 0; },
      };
      return _kv;
    } catch { /* fall through */ }
  }
  // in-memory fallback
  const store = globalThis.__fahp_kv_mem__ || (globalThis.__fahp_kv_mem__ = new Map());
  const sets  = globalThis.__fahp_kv_sets__ || (globalThis.__fahp_kv_sets__ = new Map());
  _kv = {
    async get(key)      { return store.get(key) ?? null; },
    async set(key, val) { store.set(key, val); return "OK"; },
    async sadd(key, ...members) { let s = sets.get(key) || new Set(); for (const m of members) s.add(m); sets.set(key, s); return members.length; },
    async smembers(key) { return [...(sets.get(key) || new Set())]; },
    async del(key) { store.delete(key); sets.delete(key); return 1; },
    async incr(key) { const v = (store.get(key) || 0) + 1; store.set(key, v); return v; },
    async get_int(key) { return store.get(key) || 0; },
  };
  return _kv;
}

function uid() {
  return `${Date.now()}_${randomBytes(4).toString("hex")}`;
}

// ── Affiliates ────────────────────────────────────────────────────────────────
export async function createAffiliate({ name, email, code, rate_bps, max_months = null, notes = "" }) {
  const kv = await getKv();
  const id = uid();
  const row = { id, code: code.toUpperCase(), name, email: email.toLowerCase(), rate_bps: Number(rate_bps), max_months: max_months == null ? null : Number(max_months), notes, created_at: new Date().toISOString() };
  await kv.set(`affiliate:${row.code}`, row);
  await kv.sadd("affiliates_index", row.code);
  await kv.set(`affiliate_email:${row.email}`, row.code);
  return row;
}

export async function getAffiliate(code) {
  const kv = await getKv();
  return kv.get(`affiliate:${code.toUpperCase()}`);
}

export async function getAffiliateByEmail(email) {
  const kv = await getKv();
  const code = await kv.get(`affiliate_email:${email.toLowerCase()}`);
  if (!code) return null;
  return kv.get(`affiliate:${code}`);
}

export async function listAffiliates() {
  const kv = await getKv();
  const codes = await kv.smembers("affiliates_index");
  const rows = [];
  for (const code of codes) {
    const r = await kv.get(`affiliate:${code}`);
    if (r) rows.push(r);
  }
  return rows;
}

// ── Commissions ───────────────────────────────────────────────────────────────
// type: "one_off" | "subscription_first" | "subscription_renewal"
// month_num: 1-based renewal count for this stripe_customer (used to enforce max_months)
export async function saveCommission({ affiliate_code, stripe_id, stripe_customer, gross_pence, commission_pence, type, month_num }) {
  const kv = await getKv();
  const id = uid();
  const row = { id, affiliate_code: affiliate_code.toUpperCase(), stripe_id, stripe_customer, gross_pence, commission_pence, type, month_num: month_num || 1, created_at: new Date().toISOString(), paid_at: null };
  await kv.set(`commission:${id}`, row);
  await kv.sadd(`commissions:${affiliate_code.toUpperCase()}`, id);
  return row;
}

export async function getCommissions(affiliate_code) {
  const kv = await getKv();
  const ids = await kv.smembers(`commissions:${affiliate_code.toUpperCase()}`);
  const rows = [];
  for (const id of ids) {
    const r = await kv.get(`commission:${id}`);
    if (r) rows.push(r);
  }
  return rows.sort((a, b) => b.created_at.localeCompare(a.created_at));
}

export async function markCommissionsPaid(commission_ids) {
  const kv = await getKv();
  const now = new Date().toISOString();
  const updated = [];
  for (const id of commission_ids) {
    const row = await kv.get(`commission:${id}`);
    if (row && !row.paid_at) {
      const updated_row = { ...row, paid_at: now };
      await kv.set(`commission:${id}`, updated_row);
      updated.push(updated_row);
    }
  }
  return updated;
}

// Track how many renewal months have been credited for a given affiliate+customer pair.
export async function incrementRenewalCount(affiliate_code, stripe_customer) {
  const kv = await getKv();
  const key = `commission_months:${affiliate_code.toUpperCase()}:${stripe_customer}`;
  return kv.incr(key);
}

export async function getRenewalCount(affiliate_code, stripe_customer) {
  const kv = await getKv();
  const key = `commission_months:${affiliate_code.toUpperCase()}:${stripe_customer}`;
  const v = await kv.get(key);
  return v == null ? 0 : parseInt(v, 10) || 0;
}

// ── Payouts ───────────────────────────────────────────────────────────────────
export async function savePayoutRecord({ affiliate_code, amount_pence, notes = "" }) {
  const kv = await getKv();
  const id = uid();
  const row = { id, affiliate_code: affiliate_code.toUpperCase(), amount_pence, notes, paid_at: new Date().toISOString() };
  await kv.set(`payout:${id}`, row);
  await kv.sadd(`payouts:${affiliate_code.toUpperCase()}`, id);
  return row;
}

export async function getPayouts(affiliate_code) {
  const kv = await getKv();
  const ids = await kv.smembers(`payouts:${affiliate_code.toUpperCase()}`);
  const rows = [];
  for (const id of ids) {
    const r = await kv.get(`payout:${id}`);
    if (r) rows.push(r);
  }
  return rows.sort((a, b) => b.paid_at.localeCompare(a.paid_at));
}

// ── Summary helpers ───────────────────────────────────────────────────────────
export async function affiliateSummary(code) {
  const [commissions, payouts] = await Promise.all([getCommissions(code), getPayouts(code)]);
  const total_earned = commissions.reduce((s, c) => s + c.commission_pence, 0);
  const total_paid   = payouts.reduce((s, p) => s + p.amount_pence, 0);
  return { commissions, payouts, total_earned, total_paid, balance_owed: total_earned - total_paid };
}

// ── Auth tokens (magic links) ─────────────────────────────────────────────────
const TOKEN_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

export async function createToken(affiliate_code) {
  const kv = await getKv();
  const token = randomBytes(32).toString("hex");
  const expires = Date.now() + TOKEN_TTL_MS;
  await kv.set(`affiliate_token:${token}`, { code: affiliate_code.toUpperCase(), expires });
  return token;
}

export async function verifyToken(token) {
  if (!token) return null;
  const kv = await getKv();
  const rec = await kv.get(`affiliate_token:${token}`);
  if (!rec || !rec.code) return null;
  if (rec.expires && Date.now() > rec.expires) { await kv.del(`affiliate_token:${token}`); return null; }
  return rec.code;
}

export async function revokeToken(token) {
  const kv = await getKv();
  await kv.del(`affiliate_token:${token}`);
}
