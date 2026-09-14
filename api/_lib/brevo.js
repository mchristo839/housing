// Brevo as the customer record.
//
// Until now Brevo was only a post office: we handed it one email at a time and
// it kept nothing. This module makes it the address book. Every lead, alert
// signup and buyer becomes a contact with what we know about them, sits in the
// right list, and gets an event fired for anything an automation might act on.
//
// Nothing in here sends an email. Contacts and events are silent unless an
// automation in Brevo is switched on, and none are created by code (Brevo has
// no API for that; they are built in its UI from the events named below).
//
// Every call is best-effort: a Brevo outage must never break a purchase.
import { getKv, isBlocked, getPurchasesByEmail } from "./db.js";

const API = "https://api.brevo.com/v3";
const lc = (e) => String(e || "").trim().toLowerCase();

// Contact attributes we maintain. Names are what Brevo shows in its UI and what
// the workflow build sheet refers to, so change them together or not at all.
export const ATTRIBUTES = {
  SOURCE: "text",        // sample | alert | purchase
  STATUS: "text",        // lead | customer | cancelled | blocked
  PLAN: "text",          // none | one_off | starter | unlimited
  AREA: "text",          // the area they first searched or bought
  LAST_AREA: "text",     // the most recent area they opened
  FIRST_SEEN: "date",
  LAST_PURCHASE: "date",
  LAST_UNLOCK: "date",
  PURCHASES: "float",    // count
};

export const LISTS = {
  leads: "Leads (free sample)",
  alerts: "Alert signups",
  oneoff: "One-off buyers",
  subscribers: "Subscribers",
  cancelled: "Cancelled",
};
const FOLDER = "Find a Housing Provider";

// Events an automation can be triggered by. Alphanumerics, - and _ only.
export const EVENTS = {
  sampleTaken: "sample_taken",
  alertSignup: "alert_signup",
  purchased: "purchased",
  unlocked: "unlocked_area",
  cancelled: "subscription_cancelled",
  paymentFailed: "payment_failed",
};

export function enabled() {
  return !!process.env.BREVO_API_KEY && process.env.BREVO_CRM !== "off";
}

async function call(method, path, body) {
  const res = await fetch(API + path, {
    method,
    headers: { "api-key": process.env.BREVO_API_KEY, "Content-Type": "application/json", Accept: "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text().catch(() => "");
  let json = null; try { json = text ? JSON.parse(text) : null; } catch { /* not json */ }
  return { ok: res.ok, status: res.status, json, text };
}

// ── One-time setup: attributes, folder, lists. Idempotent. ───────────────────
export async function ensureSetup({ force = false } = {}) {
  if (!enabled()) return { ok: false, error: "brevo_disabled" };
  const kv = await getKv();
  const cached = force ? null : await kv.get("brevo:setup_v1");
  if (cached && cached.lists) return { ok: true, cached: true, ...cached };

  const problems = [];
  for (const [name, type] of Object.entries(ATTRIBUTES)) {
    const r = await call("POST", `/contacts/attributes/normal/${name}`, { type });
    // 400 "already exists" is the normal case after the first run.
    if (!r.ok && !/exist/i.test(r.text)) problems.push(`attribute ${name}: ${r.status} ${r.text.slice(0, 120)}`);
  }

  let folderId = null;
  const f = await call("GET", "/contacts/folders?limit=50&offset=0");
  const found = (f.json?.folders || []).find((x) => x.name === FOLDER);
  if (found) folderId = found.id;
  else {
    const c = await call("POST", "/contacts/folders", { name: FOLDER });
    if (c.ok && c.json?.id) folderId = c.json.id;
    else problems.push(`folder: ${c.status} ${c.text.slice(0, 120)}`);
  }

  const lists = {};
  const l = await call("GET", "/contacts/lists?limit=50&offset=0");
  const existing = l.json?.lists || [];
  for (const [key, name] of Object.entries(LISTS)) {
    const hit = existing.find((x) => x.name === name);
    if (hit) { lists[key] = hit.id; continue; }
    const c = await call("POST", "/contacts/lists", { name, folderId });
    if (c.ok && c.json?.id) lists[key] = c.json.id;
    else problems.push(`list ${name}: ${c.status} ${c.text.slice(0, 120)}`);
  }

  const out = { lists, folderId, at: new Date().toISOString() };
  if (!problems.length && Object.keys(lists).length === Object.keys(LISTS).length) {
    await kv.set("brevo:setup_v1", out);
    return { ok: true, cached: false, ...out };
  }
  return { ok: false, problems, ...out };
}

// ── Contacts ─────────────────────────────────────────────────────────────────
// A blocked account is written to Brevo as blacklisted and removed from every
// list, so an automation can never reach it, and no event is fired for it.
export async function upsertContact(email, { attributes = {}, lists: addKeys = [], unlink: unlinkKeys = [], sms = null } = {}) {
  if (!enabled()) return { ok: false, skipped: "disabled" };
  const e = lc(email);
  if (!e.includes("@")) return { ok: false, skipped: "invalid_email" };
  const setup = await ensureSetup();
  if (!setup.ok) return { ok: false, skipped: "setup", setup };

  const blocked = await isBlocked(e);
  const attrs = { ...attributes };
  if (blocked) attrs.STATUS = "blocked";
  if (sms && /^\+44\d{10}$/.test(sms)) attrs.SMS = sms;

  const body = {
    email: e,
    attributes: attrs,
    updateEnabled: true,
    listIds: blocked ? [] : addKeys.map((k) => setup.lists[k]).filter(Boolean),
    unlinkListIds: (blocked ? Object.keys(LISTS) : unlinkKeys).map((k) => setup.lists[k]).filter(Boolean),
    emailBlacklisted: blocked ? true : undefined,
  };
  let r = await call("POST", "/contacts", body);
  // An SMS number Brevo rejects (in use by another contact, or oddly formed)
  // fails the whole write. Drop it and keep the rest rather than lose the contact.
  if (!r.ok && attrs.SMS && /sms|phone/i.test(r.text)) {
    delete body.attributes.SMS;
    r = await call("POST", "/contacts", body);
  }
  return { ok: r.ok, status: r.status, blocked, error: r.ok ? null : r.text.slice(0, 200) };
}

export async function trackEvent(email, name, { contact = {}, props = {}, at = null } = {}) {
  if (!enabled()) return { ok: false, skipped: "disabled" };
  const e = lc(email);
  if (!e.includes("@")) return { ok: false, skipped: "invalid_email" };
  if (await isBlocked(e)) return { ok: false, skipped: "blocked" };
  const body = { event_name: name, identifiers: { email_id: e } };
  if (Object.keys(contact).length) body.contact_properties = contact;
  if (Object.keys(props).length) body.event_properties = props;
  if (at) body.event_date = at;
  const r = await call("POST", "/events", body);
  return { ok: r.ok, status: r.status, error: r.ok ? null : r.text.slice(0, 200) };
}

// ── What each thing that happens on the site means for the contact ──────────
const day = (iso) => String(iso || new Date().toISOString()).slice(0, 10);
const areaOfScope = (s) => (s && (s.postcode || s.council || s.county)) || "";

function planFor(tier) {
  if (!tier) return "none";
  if (/^monthly_full/.test(tier)) return "unlimited";
  if (/^monthly_plus/.test(tier)) return "plus";
  if (/^monthly/.test(tier)) return "starter";
  return "one_off";
}

export async function syncLead(row) {
  const first = String(row.name || "").trim().split(/\s+/)[0] || "";
  const attributes = { SOURCE: "sample", STATUS: "lead", PLAN: "none", AREA: row.area || "", FIRST_SEEN: day(row.at) };
  if (first) attributes.FIRSTNAME = first;
  const c = await upsertContact(row.email, { attributes, lists: ["leads"], sms: row.phone || null });
  if (!c.ok) return c;
  return trackEvent(row.email, EVENTS.sampleTaken, { props: { area: row.area || "", source: "sample" }, at: row.at || null });
}

export async function syncSignup(row) {
  const areas = (row.areas || []).map(areaOfScope).filter(Boolean);
  const attributes = { SOURCE: "alert", STATUS: "lead", PLAN: "none", FIRST_SEEN: day(row.signed_up) };
  if (areas[0]) attributes.AREA = areas[0];
  const c = await upsertContact(row.email, { attributes, lists: ["alerts"] });
  if (!c.ok) return c;
  return trackEvent(row.email, EVENTS.alertSignup, { props: { areas: areas.join(", ") }, at: row.signed_up || null });
}

// sale: a recordSale row. area: from Stripe metadata when the caller has it.
export async function syncPurchase(sale, { area = "", renewal = false } = {}) {
  if (!sale?.email) return { ok: false, skipped: "no_email" };
  const plan = planFor(sale.tier);
  const sub = sale.type === "subscription";
  let areaGuess = area;
  if (!areaGuess) {
    try { const p = await getPurchasesByEmail(sale.email); areaGuess = areaOfScope(p?.[0]?.scope) || ""; } catch { /* fine */ }
  }
  const attributes = { SOURCE: "purchase", STATUS: "customer", PLAN: plan, LAST_PURCHASE: day(sale.created_at) };
  if (areaGuess) attributes.AREA = areaGuess;
  const c = await upsertContact(sale.email, {
    attributes,
    // A purchase ends the lead sequence. A subscription supersedes a one-off.
    lists: [sub ? "subscribers" : "oneoff"],
    unlink: sub ? ["leads", "oneoff", "cancelled"] : ["leads", "cancelled"],
  });
  if (!c.ok) return c;
  if (renewal) return { ok: true, renewal: true };   // a renewal is not a new purchase event
  return trackEvent(sale.email, EVENTS.purchased, {
    props: { plan, tier: sale.tier || "", amount_pence: sale.amount_pence || 0, area: areaGuess, type: sale.type || "" },
    at: sale.created_at || null,
  });
}

export async function syncUnlock(email, area) {
  const c = await upsertContact(email, { attributes: { LAST_AREA: area || "", LAST_UNLOCK: day() } });
  if (!c.ok) return c;
  return trackEvent(email, EVENTS.unlocked, { props: { area: area || "" } });
}

export async function syncCancellation(email) {
  const c = await upsertContact(email, { attributes: { STATUS: "cancelled", PLAN: "none" }, lists: ["cancelled"], unlink: ["subscribers"] });
  if (!c.ok) return c;
  return trackEvent(email, EVENTS.cancelled);
}

export async function syncPaymentFailed(email, { amount_pence = 0 } = {}) {
  return trackEvent(email, EVENTS.paymentFailed, { props: { amount_pence } });
}

// Blocked in admin: make sure Brevo can never email them either.
export async function syncBlocked(email) {
  return upsertContact(email, { attributes: { STATUS: "blocked" } });
}
