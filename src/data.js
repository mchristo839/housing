// API client. The gated provider data lives behind /api/* — the browser only
// ever receives counts/price (preview) or the full list after payment (result).

async function asJson(res) {
  const d = await res.json().catch(() => ({}));
  if (!res.ok) { const e = new Error(d.error || `http_${res.status}`); e.code = d.error; e.status = res.status; throw e; }
  return d;
}

export async function getStats() {
  return fetch("/stats.json").then((r) => r.json()).catch(() => null);
}

// scope = { postcode } | { council } | { county }  — one of these
export async function getPreview(scope) {
  const qs = new URLSearchParams(scope).toString();
  const res = await fetch(`/api/preview?${qs}`);
  if (res.status === 404) { const e = new Error("notfound"); e.code = "not_found"; throw e; }
  return asJson(res);
}

export async function startCheckout(scope, opts = {}) {
  // scope = { postcode } | { council } | { county }
  // opts  = { tier, addTemplates, ref }
  const body = { ...scope, tier: opts.tier || (scope.county ? "county" : "postcode"),
                 addTemplates: !!opts.addTemplates, ref: opts.ref || affiliateRef.get() || undefined };
  const res = await fetch("/api/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return asJson(res); // { url }
}

export async function requestAffiliateLink(email) {
  return asJson(await fetch("/api/affiliate/send-link", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  }));
}

export async function getAffiliatePortal(token) {
  return asJson(await fetch(`/api/affiliate/portal?token=${encodeURIComponent(token)}`));
}

// Affiliate referral code — persisted for the browser session via sessionStorage.
export const affiliateRef = {
  get() { try { return sessionStorage.getItem("fahp_ref") || ""; } catch { return ""; } },
  set(code) { try { if (code) sessionStorage.setItem("fahp_ref", code.toUpperCase()); } catch { /* ignore */ } },
};

export async function getResult(params) {
  const qs = new URLSearchParams(params).toString();
  return asJson(await fetch(`/api/result?${qs}`));
}

export async function unlockByEmail(email, scope) {
  return getResult({ email, ...scope });
}

// Notification signup — saves email + areas to /api/notify-signup
export async function notifySignup(email, areas) {
  return asJson(await fetch("/api/notify-signup", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, areas }),
  }));
}

export async function openPortal(email) {
  return asJson(await fetch("/api/portal", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  }));
}

// remember the subscriber's email so future searches unlock automatically
export const savedEmail = {
  get() { try { return localStorage.getItem("fahp_email") || ""; } catch { return ""; } },
  set(e) { try { if (e) localStorage.setItem("fahp_email", e); } catch { /* ignore */ } },
  clear() { try { localStorage.removeItem("fahp_email"); } catch { /* ignore */ } },
};

export const SECTORS = [
  "Supported living",
  "Supported accommodation",
  "Community accommodation",
  "Emergency accommodation",
  "Emergency housing",
  "Asylum housing",
  "Homecare",
  "Housing",
];

export function formatEmployees(n) {
  if (n == null) return null;
  if (n >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k`.replace(".0k", "k");
  return `${n}`;
}
