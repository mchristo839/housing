// Admin authentication — named users with passwords, KV-backed sessions.
//
// Users come from the ADMIN_USERS env var: "mario:secret1,paul:secret2"
// (comma-separated user:password pairs — usernames are case-insensitive).
// A successful login mints a session token stored in KV for 30 days:
//   admin_session:<token> → { username, expires }
//
// The legacy ADMIN_TOKEN env var is still accepted anywhere a session token
// is, so existing bookmarks/scripts keep working.

import { randomBytes, timingSafeEqual } from "node:crypto";
import { getKv } from "./db.js";

const SESSION_TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 days

function safeEqual(a, b) {
  const ba = Buffer.from(String(a)), bb = Buffer.from(String(b));
  if (ba.length !== bb.length) return false;
  return timingSafeEqual(ba, bb);
}

function parseUsers() {
  const raw = process.env.ADMIN_USERS || "";
  const users = {};
  for (const pair of raw.split(",")) {
    const i = pair.indexOf(":");
    if (i > 0) users[pair.slice(0, i).trim().toLowerCase()] = pair.slice(i + 1).trim();
  }
  return users;
}

export function verifyCredentials(username, password) {
  const users = parseUsers();
  const stored = users[String(username || "").trim().toLowerCase()];
  if (!stored || !password) return false;
  return safeEqual(stored, password);
}

export async function createAdminSession(username) {
  const kv = await getKv();
  const token = randomBytes(32).toString("hex");
  await kv.set(`admin_session:${token}`, { username: username.toLowerCase(), expires: Date.now() + SESSION_TTL_MS });
  return token;
}

// Returns the username for a valid session token (or "admin" for the legacy
// ADMIN_TOKEN), null otherwise.
export async function verifyAdminToken(token) {
  if (!token) return null;
  if (process.env.ADMIN_TOKEN && safeEqual(token, process.env.ADMIN_TOKEN)) return "admin";
  const kv = await getKv();
  const rec = await kv.get(`admin_session:${token}`);
  if (!rec || !rec.username) return null;
  if (rec.expires && Date.now() > rec.expires) { await kv.del(`admin_session:${token}`); return null; }
  return rec.username;
}
