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
async function getKv() {
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

// ── Leads (free-tier sign-ups from the home page, future) ─────────────────────
export async function saveLead(email, source, area) {
  const kv = await getKv();
  const id = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  await kv.set(`lead:${id}`, { id, email, source, area, created_at: new Date().toISOString() });
  await kv.sadd("leads_index", id);
  return id;
}
