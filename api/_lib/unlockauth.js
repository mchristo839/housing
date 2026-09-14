// Verifying that someone actually owns the email address they type into
// "Already bought? Unlock with your email".
//
// Before this, that box asked for an address and checked nothing: anyone who
// knew a subscriber's email got the whole directory. Now we email a six-digit
// code to the address, and only a correct code mints a token that unlocks.
//
// The token is an HMAC over the address and an expiry, so nothing needs to be
// looked up to check it, and it cannot be forged without the server secret.
import { createHmac, randomInt, timingSafeEqual } from "node:crypto";
import { getKv } from "./db.js";
import { sendEmail, FROM_EMAIL } from "./email.js";

export const CODE_TTL_MS = 10 * 60 * 1000;        // a code is good for 10 minutes
export const TOKEN_TTL_MS = 30 * 24 * 60 * 60 * 1000;  // then 30 days of not re-typing
const MAX_ATTEMPTS = 5;                            // wrong guesses before a code dies
const MAX_SENDS_PER_HOUR = 5;                      // codes we will email one address

const lc = (e) => String(e || "").trim().toLowerCase();

function secret() {
  // A dedicated secret is preferred, but fall back to something that already
  // exists in production so the protection works before anything is configured.
  const s = process.env.UNLOCK_TOKEN_SECRET || process.env.ADMIN_TOKEN || process.env.STRIPE_SECRET_KEY;
  if (!s) throw new Error("no signing secret available");
  return createHmac("sha256", "fahp-unlock-v1").update(s).digest();
}

const b64url = (buf) => Buffer.from(buf).toString("base64url");

export function issueToken(email, now = Date.now()) {
  const exp = now + TOKEN_TTL_MS;
  const payload = `${lc(email)}|${exp}`;
  const sig = createHmac("sha256", secret()).update(payload).digest();
  return `${b64url(payload)}.${b64url(sig)}`;
}

export function verifyToken(token, email, now = Date.now()) {
  try {
    const [p, s] = String(token || "").split(".");
    if (!p || !s) return false;
    const payload = Buffer.from(p, "base64url").toString("utf8");
    const [tokEmail, expRaw] = payload.split("|");
    if (lc(tokEmail) !== lc(email)) return false;
    if (!Number(expRaw) || Number(expRaw) < now) return false;
    const want = createHmac("sha256", secret()).update(payload).digest();
    const got = Buffer.from(s, "base64url");
    return want.length === got.length && timingSafeEqual(want, got);
  } catch {
    return false;
  }
}

// Returns { sent: true } when a code went out, or { sent: false, reason } when
// it did not. Callers must NOT pass the reason to the browser: telling a
// stranger whether an address is a customer is its own leak.
export async function sendCode(email, { hasPurchase }) {
  const e = lc(email);
  if (!e || !e.includes("@")) return { sent: false, reason: "invalid_email" };
  const kv = await getKv();

  const hourKey = `unlockcode_sent:${e}:${new Date().toISOString().slice(0, 13)}`;
  const sentThisHour = Number(await kv.get(hourKey)) || 0;
  if (sentThisHour >= MAX_SENDS_PER_HOUR) return { sent: false, reason: "rate_limited" };
  await kv.set(hourKey, sentThisHour + 1);

  // Never email an address that has nothing to unlock.
  if (!hasPurchase) return { sent: false, reason: "no_purchase" };

  const code = String(randomInt(0, 1000000)).padStart(6, "0");
  await kv.set(`unlockcode:${e}`, { code, exp: Date.now() + CODE_TTL_MS, attempts: 0 });

  const html = `
    <div style="font-family:sans-serif;max-width:520px;color:#1a1a1a">
      <h2 style="margin:0 0 12px">Your sign-in code</h2>
      <p style="margin:0 0 16px;line-height:1.5">Enter this code to open your provider lists:</p>
      <p style="font-size:32px;font-weight:800;letter-spacing:6px;margin:0 0 16px">${code}</p>
      <p style="margin:0 0 16px;line-height:1.5;color:#666">It expires in 10 minutes and can only be used once.</p>
      <p style="margin:0 0 16px;line-height:1.5;color:#666">If you did not ask for this, you can ignore it. Someone may have typed your address by mistake; nothing has been opened.</p>
      <p style="color:#666;font-size:13px;margin:0">Find a Housing Provider · <a href="mailto:${FROM_EMAIL}">${FROM_EMAIL}</a></p>
    </div>`;
  try {
    const r = await sendEmail({ to: e, subject: `${code} is your Find a Housing Provider code`, html });
    if (!r.ok) { console.error("unlock code not sent:", r); return { sent: false, reason: "send_failed" }; }
    return { sent: true };
  } catch (err) {
    console.error("unlock code failed:", err);
    return { sent: false, reason: "send_failed" };
  }
}

// { ok: true, token } on success, otherwise { ok: false, error }.
export async function checkCode(email, supplied) {
  const e = lc(email);
  const entered = String(supplied || "").replace(/\D/g, "");
  if (entered.length !== 6) return { ok: false, error: "bad_code" };
  const kv = await getKv();
  const key = `unlockcode:${e}`;
  const row = await kv.get(key);
  if (!row || !row.code) return { ok: false, error: "bad_code" };
  if (Date.now() > Number(row.exp || 0)) { await kv.del(key); return { ok: false, error: "code_expired" }; }
  if (Number(row.attempts || 0) >= MAX_ATTEMPTS) { await kv.del(key); return { ok: false, error: "bad_code" }; }

  const a = Buffer.from(String(row.code)), b = Buffer.from(entered);
  const match = a.length === b.length && timingSafeEqual(a, b);
  if (!match) {
    await kv.set(key, { ...row, attempts: Number(row.attempts || 0) + 1 });
    return { ok: false, error: "bad_code" };
  }
  await kv.del(key);                       // single use
  return { ok: true, token: issueToken(e) };
}
