import { useState, useEffect, useRef, useMemo } from "react";
import { getStats, getPreview, startCheckout, getResult, unlockByEmail, openPortal, savedEmail, notifySignup } from "./data.js";
import Results from "./components/Results.jsx";
import GuidePage from "./components/GuidePage.jsx";
import { GUIDES, GUIDE_BY_SLUG } from "./content/guides.js";
import { TEMPLATES } from "./message.js";

// Owner-only developer-unlock visibility.
// Sticky: once you visit any URL with ?dev=1 the flag is set in localStorage
// and the button stays available on that browser until you clear it.
// Pair with ALLOW_DEV_UNLOCK=1 on the server for the unlock to actually work.
function showDevUnlock() {
  if (import.meta.env.DEV) return true;
  if (typeof window === "undefined") return false;
  try {
    if (new URLSearchParams(window.location.search).has("dev")) {
      window.localStorage.setItem("fhp_dev", "1");
      return true;
    }
    return window.localStorage.getItem("fhp_dev") === "1";
  } catch { return false; }
}

const HOME_META = {
  title: "Find a Housing Provider — Connect with Supported Living & Social Housing providers in your area",
  description: "We help Property Developers & Landlords partner with Supported Living and Social Housing providers, direct. Search the directory free; subscribe from £49/month to unlock verified contacts.",
};
const ABOUT_META = {
  title: "About — Find a Housing Provider",
  description: "Find the housing associations, care companies and social housing providers commissioned in your area.",
};
const RESOURCES_META = {
  title: "Resources — Email templates for landlords | Find a Housing Provider",
  description: "Free email templates landlords can use to approach care and housing providers about leasing a property.",
};
const PRIVACY_META = {
  title: "Privacy Policy — Find a Housing Provider",
  description: "How we collect, use and protect personal data, and your rights under UK GDPR.",
};
const TERMS_META = {
  title: "Terms & Conditions — Find a Housing Provider",
  description: "The terms governing your use of Find a Housing Provider, including subscriptions, billing, data use and liability.",
};
function applyMeta({ title, description }) {
  if (title) document.title = title;
  const m = document.querySelector('meta[name="description"]');
  if (m && description) m.setAttribute("content", description);
}

export default function App() {
  const [route, setRoute] = useState(typeof window !== "undefined" ? window.location.pathname : "/");
  const [stats, setStats] = useState(null);
  const [searchMode, setSearchMode] = useState("postcode"); // postcode | borough | county
  const [postcode, setPostcode] = useState("");
  const [borough, setBorough] = useState("");
  const [county, setCounty] = useState("");
  const [status, setStatus] = useState("idle");      // idle | loading | error | verifying
  const [error, setError] = useState("");
  const [preview, setPreview] = useState(null);       // counts + price
  const [unlocked, setUnlocked] = useState(null);     // full provider list
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [emailBusy, setEmailBusy] = useState(false);
  const [addTemplates, setAddTemplates] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => { getStats().then(setStats); }, []);

  useEffect(() => {
    const onPop = () => { setRoute(window.location.pathname); };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const slug = route.replace(/^\//, "");
  const guide = GUIDE_BY_SLUG[slug];

  useEffect(() => {
    if (guide) applyMeta(guide.meta);
    else if (route === "/about") applyMeta(ABOUT_META);
    else if (route === "/privacy") applyMeta(PRIVACY_META);
    else if (route === "/terms") applyMeta(TERMS_META);
    else applyMeta(HOME_META);
  }, [route, guide]);

  // Stripe success redirect lands on /result?session_id=...
  useEffect(() => {
    if (route !== "/result") return;
    const sid = new URLSearchParams(window.location.search).get("session_id");
    if (!sid) { setStatus("error"); setNotice("Missing checkout session."); return; }
    setStatus("verifying"); setNotice("");
    getResult({ session_id: sid })
      .then((full) => {
        if (full.email) savedEmail.set(full.email);
        if (full.needPostcode) { setStatus("idle"); setNotice("subscribed-no-postcode"); navigate("/"); return; }
        setUnlocked(full); setStatus("idle");
      })
      .catch((e) => {
        setStatus("error");
        setNotice(e.code === "not_active" ? "Your subscription isn't active yet." : "We couldn't confirm your subscription. If you were charged, contact hello@findahousingprovider.co.uk.");
      });
  }, [route]);

  function navigate(path) {
    if (path !== window.location.pathname) window.history.pushState({}, "", path);
    setRoute(path);
    setPreview(null); setUnlocked(null); setNotice("");
    window.scrollTo({ top: 0 });
  }

  function activeScope() {
    if (searchMode === "postcode" && postcode) return { postcode: postcode.trim() };
    if (searchMode === "borough" && borough)   return { council: borough.trim() };
    if (searchMode === "county"  && county)    return { county:  county.trim() };
    return null;
  }

  async function search(overrideValue) {
    const raw = String(
      overrideValue != null ? overrideValue
      : searchMode === "postcode" ? postcode
      : searchMode === "borough" ? borough
      : county
    ).trim();
    if (!raw) return;

    // Try the active tab's interpretation first, then fall back to the others
    // so a term like "Manchester" (a council, not a county) still resolves
    // whatever tab the user happens to be on. Postcodes contain a digit, so we
    // only attempt a postcode lookup for digit-bearing terms.
    const asPostcode = { postcode: raw }, asCouncil = { council: raw }, asCounty = { county: raw };
    const hasDigit = /\d/.test(raw);
    let candidates;
    if (searchMode === "postcode")      candidates = [asPostcode, asCouncil, asCounty];
    else if (searchMode === "borough")  candidates = [asCouncil, ...(hasDigit ? [asPostcode] : []), asCounty];
    else                                candidates = [asCounty, asCouncil, ...(hasDigit ? [asPostcode] : [])];

    setStatus("loading"); setError(""); setNotice("");
    setPreview(null); setUnlocked(null);

    let lastErr = null;
    for (const scope of candidates) {
      try {
        const pv = await getPreview(scope);
        pv._scope = scope; // remember which query produced these counts
        // Reflect the interpretation that actually worked, so the tab + field match.
        const mode = scope.postcode ? "postcode" : scope.council ? "borough" : "county";
        setSearchMode(mode);
        if (scope.postcode) setPostcode(scope.postcode);
        if (scope.council)  setBorough(scope.council);
        if (scope.county)   setCounty(scope.county);
        const em = savedEmail.get();
        if (em) {
          try {
            const full = await unlockByEmail(em, scope);
            savedEmail.set(full.email); setUnlocked(full); setStatus("idle");
            window.scrollTo({ top: 0, behavior: "smooth" });
            return;
          } catch (e) {
            // Subscriber hit their monthly area allowance — show the paywall with a note.
            if (e.code === "monthly_limit") setNotice("You've used all your area unlocks for this month. Upgrade for more, or your allowance resets next month.");
            /* fall through to subscribe gate */
          }
        }
        setPreview(pv); setStatus("idle");
        window.scrollTo({ top: 0, behavior: "smooth" });
        return;
      } catch (e) { lastErr = e; }
    }
    setStatus("error");
    setError(lastErr && (lastErr.code === "not_found" || lastErr.code === "postcode_not_found")
      ? `We couldn't find “${raw}”. Try a postcode, council or county in England.`
      : "Something went wrong. Please try again.");
  }

  async function subscribe(tier) {
    if (!preview) return;
    setCheckoutBusy(true); setNotice("");
    try {
      const scope = preview._scope || { postcode: preview.postcode };
      const t = tier || (scope.county ? "county" : "postcode");
      const { url } = await startCheckout(scope, { tier: t, addTemplates });
      window.location.href = url;
    } catch (e) {
      setCheckoutBusy(false);
      setNotice(e.code === "payments_not_configured"
        ? "Payments aren't switched on yet — add a Stripe key to enable purchases."
        : "Couldn't start checkout. Please try again.");
    }
  }

  async function emailUnlock(email) {
    if (!preview || !email) return;
    setEmailBusy(true); setNotice("");
    try {
      const scope = preview._scope || { postcode: preview.postcode };
      const full = await unlockByEmail(email, scope);
      savedEmail.set(full.email); setUnlocked(full);
    } catch (e) {
      setNotice(e.code === "no_purchase"
        ? "No active purchase found for that email. Buy below, or check the email you used."
        : e.code === "monthly_limit"
        ? "You've used all your area unlocks for this month. Upgrade to Plus or Unlimited for more — or your allowance resets next month."
        : "Couldn't verify that email. Please try again.");
    }
    setEmailBusy(false);
  }

  async function manageSubscription() {
    const em = savedEmail.get() || window.prompt("Enter the email on your subscription:");
    if (!em) return;
    try { const { url } = await openPortal(em); window.location.href = url; }
    catch { window.alert("No active subscription found for that email."); }
  }

  async function devUnlock() {
    try { setUnlocked(await getResult({ dev: "1", postcode: preview.postcode })); }
    catch { setNotice("Dev unlock failed (set ALLOW_DEV_UNLOCK=1)."); }
  }

  const isHome = route === "/" || (!guide && !["/about", "/result", "/privacy", "/terms"].includes(route));

  return (
    <>
      <Header route={route} navigate={navigate} />

      {unlocked ? (
        <Results result={unlocked} onNewSearch={() => { setUnlocked(null); setPreview(null); navigate("/"); }} />
      ) : route === "/result" ? (
        <Verifying status={status} notice={notice} navigate={navigate} />
      ) : isHome && preview ? (
        <SubscribeGate preview={preview} onSubscribe={subscribe} busy={checkoutBusy} notice={notice}
                 onEmailUnlock={emailUnlock} emailBusy={emailBusy} onDev={devUnlock} onBack={() => setPreview(null)}
                 addTemplates={addTemplates} setAddTemplates={setAddTemplates} />
      ) : isHome ? (
        <Home searchMode={searchMode} setSearchMode={setSearchMode}
              postcode={postcode} setPostcode={setPostcode}
              borough={borough} setBorough={setBorough}
              county={county} setCounty={setCounty}
              onSearch={search}
              status={status} error={error} stats={stats} navigate={navigate} />
      ) : route === "/about" ? (
        <About navigate={navigate} />
      ) : route === "/privacy" ? (
        <Privacy />
      ) : route === "/terms" ? (
        <Terms />
      ) : guide ? (
        <GuidePage guide={guide} onNav={navigate} onSearchCta={() => navigate("/")} />
      ) : null}

      <Footer navigate={navigate} onManage={manageSubscription} />
    </>
  );
}

/* ── Header ──────────────────────────────────────────────────────────────── */
function Header({ route, navigate }) {
  const [menu, setMenu] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setMenu(false); };
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, []);
  const go = (p) => { setMenu(false); navigate(p); };
  return (
    <header className="site-header">
      <div className="wrap">
        <button className="brand" onClick={() => go("/")} aria-label="Find a Housing Provider — home">
          <span className="mark" aria-hidden="true">F</span>
          Find a Housing Provider
        </button>
        <nav className="nav">
          <button className={route === "/" ? "active" : ""} onClick={() => go("/")}>Search</button>
          <div className="dropdown" ref={ref}>
            <button className={GUIDE_BY_SLUG[route.replace(/^\//, "")] ? "active" : ""}
              onClick={(e) => { e.stopPropagation(); setMenu((v) => !v); }} aria-expanded={menu}>
              Guides <span className="caret" aria-hidden="true">▾</span>
            </button>
            {menu && (
              <div className="dropdown-menu">
                {GUIDES.map((g) => <button key={g.slug} onClick={() => go(`/${g.slug}`)}>{g.nav}</button>)}
              </div>
            )}
          </div>
          <button className={route === "/about" ? "active" : ""} onClick={() => go("/about")}>About</button>
          <button className="nav-cta" onClick={() => { go("/"); setTimeout(() => window.scrollTo({ top: 0 }), 50); }}>
            Search a postcode
          </button>
        </nav>
      </div>
    </header>
  );
}

/* ── Resources (email templates) ─────────────────────────────────────────── */
function Resources({ navigate }) {
  return (
    <main className="page">
      <div className="wrap narrow">
        <h1>Resources for landlords</h1>
        <div className="prose">
          <p>Two email templates you can copy and adapt when approaching a care or housing provider.
            Fill in the <span className="bracket">[bracketed]</span> details. When you unlock a postcode,
            each provider's listing shows the specific contract they hold with your council — drop that
            into Template 1 for a stronger, more relevant approach.</p>
        </div>
        {TEMPLATES.map((t) => <TemplateCard key={t.id} t={t} />)}
        <div className="guide-cta">
          <h3>Find providers near you</h3>
          <p>See which providers hold contracts with your council, then use these templates to reach out.</p>
          <button className="btn btn-primary" onClick={() => navigate("/")}>Search by postcode</button>
        </div>
      </div>
    </main>
  );
}

function TemplateCard({ t }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(`Subject: ${t.subject}\n\n${t.body}`);
      setCopied(true); setTimeout(() => setCopied(false), 2000);
    } catch { /* ignore */ }
  }
  return (
    <div className="template-card">
      <div className="template-head">
        <h3>{t.title}</h3>
        <button className="msg-copy" onClick={copy}>{copied ? "Copied ✓" : "Copy email"}</button>
      </div>
      <p className="template-blurb">{t.blurb}</p>
      <p className="template-subject"><span>Subject:</span> {t.subject}</p>
      <pre className="msg-text">{t.body}</pre>
    </div>
  );
}

/* ── Home ────────────────────────────────────────────────────────────────── */
function Home({ searchMode, setSearchMode, postcode, setPostcode, borough, setBorough, county, setCounty, onSearch, status, error, stats, navigate }) {
  const inputRef = useRef(null);
  useEffect(() => { inputRef.current?.focus(); }, [searchMode]);

  const placeholders = {
    postcode: "e.g. M1 1AE or SW1A 1AA",
    borough:  "e.g. Camden, Brighton, Manchester",
    county:   "e.g. Kent, Greater Manchester, Devon",
  };
  const examples = {
    postcode: ["M1 1AE", "LS1 4AW", "SW1A 1AA", "DE1 1AA"],
    borough:  ["Camden", "Brighton and Hove", "Manchester", "Leeds"],
    county:   ["Kent", "Hertfordshire", "Greater Manchester", "West Yorkshire"],
  };
  const value = searchMode === "postcode" ? postcode : searchMode === "borough" ? borough : county;
  const setValue = (v) => searchMode === "postcode" ? setPostcode(v)
                       : searchMode === "borough" ? setBorough(v)
                       : setCounty(v);

  return (
    <main className="v2home" id="top">
      <section className="hero">
        <div className="wrap">
          <span className="hero-eyebrow"><span className="dot" /> Online directory · England · Updated monthly</span>
          <h1 className="display">The directory of <span className="mark">supported living</span> &amp; social housing providers.</h1>
          <p className="lead">Search any postcode, borough or county and see every commissioned provider operating there — the commissioners behind them, the care they deliver, and verified contact details. England-wide, refreshed every month.</p>

          <div className="searchbox">
            <div className="tabs" role="tablist" aria-label="Search by">
              {["postcode","borough","county"].map((m) => (
                <button key={m} role="tab" aria-selected={searchMode === m}
                  className={`tab ${searchMode === m ? "on" : ""}`}
                  onClick={() => setSearchMode(m)}>
                  {m === "postcode" ? "Postcode" : m === "borough" ? "Borough / Council" : "County"}
                </button>
              ))}
            </div>
            <div className="searchrow" role="search">
              <input ref={inputRef} value={value}
                onChange={(e) => setValue(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && onSearch()}
                placeholder={placeholders[searchMode]}
                aria-label={`Search the directory by ${searchMode}`}
                spellCheck={false}
                autoCapitalize={searchMode === "postcode" ? "characters" : "words"} />
              <button className="btn btn-blue" onClick={() => onSearch()} disabled={status === "loading"}>
                {status === "loading" ? <span className="spinner" aria-label="Searching" /> : "Search"}
              </button>
            </div>
            {error ? <p className="searcherror">{error}</p> : (
              <p className="hint">
                Free to search — see how many providers are listed before you pay. Try{" "}
                {examples[searchMode].map((ex, i) => (
                  <span key={ex}><span className="ex" onClick={() => onSearch(ex)}>{ex}</span>{i < examples[searchMode].length - 1 ? " · " : ""}</span>
                ))}
              </p>
            )}
          </div>
        </div>
      </section>

      {/* ────── Stat band ────── */}
      <div className="band">
        <div className="wrap">
          <div className="stat"><b className="tnum">{stats ? stats.providers.toLocaleString() + "+" : "1,900+"}</b><span>providers listed</span></div>
          <div className="stat"><b className="tnum">{stats ? stats.councils + "+" : "300+"}</b><span>councils covered</span></div>
          <div className="stat"><b className="tnum">{stats && stats.contracts ? stats.contracts.toLocaleString() + "+" : "1,300+"}</b><span>supported-living contracts processed</span></div>
          <div className="stat"><b className="tnum">Monthly</b><span>data refresh</span></div>
        </div>
      </div>

      {/* ────── What's in every listing ────── */}
      <section className="pad" id="listing">
        <div className="wrap">
          <div className="sec-head">
            <span className="eyebrow">What&rsquo;s in every listing</span>
            <h2>One entry. Everything you need to make contact.</h2>
            <p className="lead">Each provider in the directory comes with the detail that turns a name into a conversation.</p>
          </div>
          <div className="fields">
            <div className="field"><div className="ic">◉</div><h3>Providers active in the area</h3><p>The supported-living and social-housing operators commissioned where you&rsquo;re searching.</p></div>
            <div className="field"><div className="ic">⚐</div><h3>The commissioners behind them</h3><p>Which councils, NHS bodies and consortia fund each provider.</p></div>
            <div className="field"><div className="ic">⌂</div><h3>Type of care or housing</h3><p>What each provider delivers — client groups and accommodation type.</p></div>
            <div className="field"><div className="ic">✉</div><h3>Verified contact details</h3><p>Phone, email and website, checked against live sources — not a stale scrape.</p></div>
            <div className="field"><div className="ic">✦</div><h3>Outreach templates &amp; guide</h3><p>Proven email templates and a usage guide, included with every search.</p></div>
          </div>
        </div>
      </section>

      {/* ────── Who uses the directory ────── */}
      <section className="pad">
        <div className="wrap">
          <div className="sec-head">
            <span className="eyebrow">Who uses the directory</span>
            <h2>Anyone who needs to reach providers — fast.</h2>
          </div>
          <div className="who">
            <div className="whocard"><b>Property developers</b><span>Find which providers are active before committing to a scheme, and build for a buyer already in the area.</span></div>
            <div className="whocard"><b>Landlords &amp; investors</b><span>Identify the operators who lease whole properties on long, guaranteed-rent terms near your stock.</span></div>
            <div className="whocard"><b>Agents &amp; brokers</b><span>Match property to the right commissioned providers without cold-guessing who operates where.</span></div>
          </div>
        </div>
      </section>

      {/* ────── Pricing ────── */}
      <section className="pad alt" id="pricing">
        <div className="wrap">
          <div className="sec-head" style={{ textAlign: "center", margin: "0 auto" }}>
            <span className="eyebrow">Pricing</span>
            <h2>Simple monthly plans.</h2>
            <p className="lead" style={{ marginLeft: "auto", marginRight: "auto" }}>Subscribe to unlock provider listings across the areas you search. Search the directory free — you only pay to reveal the names and verified contacts. Cancel anytime.</p>
          </div>
          <div className="prices">
            <div className="price-card">
              <span className="tag">Monthly · Starter</span>
              <div className="amt">£49<span className="amt-per">/mo</span></div>
              <div className="per">5 area unlocks a month</div>
              <ul>
                <li>Unlock up to 5 areas / month</li>
                <li>Postcode, borough or county</li>
                <li>Cancel anytime</li>
              </ul>
              <button className="btn btn-out" onClick={() => { window.scrollTo({ top: 0, behavior: "smooth" }); inputRef.current?.focus(); }}>Search an area</button>
            </div>
            <div className="price-card feat">
              <span className="ribbon">Most popular</span>
              <span className="tag">Monthly · Plus</span>
              <div className="amt">£99<span className="amt-per">/mo</span></div>
              <div className="per">10 area unlocks a month</div>
              <ul>
                <li>Unlock up to 10 areas / month</li>
                <li>Postcode, borough or county</li>
                <li>Cancel anytime</li>
              </ul>
              <button className="btn btn-blue" onClick={() => { window.scrollTo({ top: 0, behavior: "smooth" }); inputRef.current?.focus(); }}>Start monthly</button>
            </div>
            <div className="price-card">
              <span className="tag">Monthly · Unlimited</span>
              <div className="amt">£199<span className="amt-per">/mo</span></div>
              <div className="per">unlimited unlocks</div>
              <ul>
                <li>Unlock as many areas as you like</li>
                <li>Best for active sourcing</li>
                <li>Cancel anytime</li>
              </ul>
              <button className="btn btn-out" onClick={() => { window.scrollTo({ top: 0, behavior: "smooth" }); inputRef.current?.focus(); }}>Go unlimited</button>
            </div>
          </div>
        </div>
      </section>

      {/* ────── FAQ ────── */}
      <section className="pad">
        <div className="wrap">
          <div className="sec-head"><span className="eyebrow">FAQ</span><h2>Straight answers.</h2></div>
          <div className="faq">
            <details><summary>What is the directory?</summary><p>A searchable, England-wide directory of the supported-living and social-housing providers commissioned in each area — with the commissioners behind them, the care they deliver, and verified contact details. Search by postcode, borough or county.</p></details>
            <details><summary>How much does it cost?</summary><p>Searching the directory is free — you see how many providers cover an area before paying anything. To unlock the names and verified contacts you subscribe: Starter £49/month (5 area unlocks), Plus £99/month (10 unlocks), or Unlimited £199/month. Re-opening an area you've already unlocked that month doesn't count against your allowance. Cancel anytime.</p></details>
            <details><summary>How current is the data?</summary><p>The directory is refreshed monthly and contacts are verified against live websites and Companies House before listing.</p></details>
            <details><summary>Do you broker deals between me and a provider?</summary><p>No — we&rsquo;re a directory and research tool, not a broker. We show you who&rsquo;s active and how to reach them; any agreement is between you and the provider.</p></details>
          </div>
        </div>
      </section>

      {/* ────── Closing CTA ────── */}
      <section className="closing">
        <div className="wrap">
          <h2>Search the directory free.</h2>
          <p>Enter any postcode, borough or county and see how many providers are listed before you pay a penny.</p>
          <button className="btn btn-blue btn-lg" onClick={() => { window.scrollTo({ top: 0, behavior: "smooth" }); inputRef.current?.focus(); }}>Search the directory →</button>
        </div>
      </section>
    </main>
  );
}

/* ── Subscribe gate (preview → buy a tier / unlock by email) ──────────────── */
function SubscribeGate({ preview, onSubscribe, busy, notice, onEmailUnlock, emailBusy, onDev, onBack, addTemplates, setAddTemplates }) {
  const { council, countyName, region, total, tiers, pricing, monthly, postcode, _scope } = preview;
  const [email, setEmail] = useState("");
  const [showEmail, setShowEmail] = useState(false);
  const P = { ...(pricing || {}), monthly: monthly || {} };
  const scope = _scope || {};
  const isCounty = !!scope.county;
  const scopeLabel = scope.county || scope.council || scope.postcode || council;
  return (
    <main className="paywall">
      <div className="wrap narrow">
        <button className="guide-back" onClick={onBack}>← Search another area</button>
        <div className="paywall-card">
          <span className="eyebrow"><span className="dot" /> {scopeLabel}{council && council !== scopeLabel ? ` · ${council}` : ""}{region ? ` · ${region}` : ""}</span>
          {total === 0 ? (
            <>
              <h1 className="paywall-count">No providers found here yet</h1>
              <p className="sub">We don't currently hold provider contracts for {council}. Try a nearby postcode — coverage is strongest in towns and cities.</p>
              <button className="btn btn-secondary" onClick={onBack}>Try another postcode</button>
            </>
          ) : (
            <>
              <h1 className="paywall-count"><b className="tnum">{total}</b> {total === 1 ? "provider" : "providers"} cover {council}</h1>
              <p className="sub">Subscribe to unlock every provider here — and every other area you search — with names, contracts and verified direct contacts.</p>

              <ul className="paywall-tiers">
                <li><b className="tnum">{tiers.local}</b> hold a contract with {council}</li>
                {countyName && tiers.county ? <li><b className="tnum">{tiers.county}</b> county-wide across {countyName}</li> : null}
                <li><b className="tnum">{tiers.regional}</b> active across {region || "the region"}</li>
                <li><b className="tnum">{tiers.national}</b> UK-wide providers</li>
              </ul>

              {/* Subscription-only — choose a plan to unlock. */}
              <div className="paywall-monthly paywall-plans">
                <div className="pm-divider"><span>Choose a plan to unlock</span></div>
                <div className="pm-grid pm-grid-3">
                  <button className="pm-card" onClick={() => onSubscribe("monthly_starter")} disabled={busy}>
                    <span className="pm-name">{P.monthly?.monthly_starter?.name || "Starter"}</span>
                    <span className="pm-price"><b>{P.monthly?.monthly_starter?.label || "£49"}</b>/mo</span>
                    <span className="pm-blurb">{P.monthly?.monthly_starter?.blurb || "5 area unlocks every month"}</span>
                  </button>
                  <button className="pm-card featured" onClick={() => onSubscribe("monthly_plus")} disabled={busy}>
                    <span className="pm-flag">Most popular</span>
                    <span className="pm-name">{P.monthly?.monthly_plus?.name || "Plus"}</span>
                    <span className="pm-price"><b>{P.monthly?.monthly_plus?.label || "£99"}</b>/mo</span>
                    <span className="pm-blurb">{P.monthly?.monthly_plus?.blurb || "10 area unlocks every month"}</span>
                  </button>
                  <button className="pm-card" onClick={() => onSubscribe("monthly_full")} disabled={busy}>
                    <span className="pm-name">{P.monthly?.monthly_full?.name || "Unlimited"}</span>
                    <span className="pm-price"><b>{P.monthly?.monthly_full?.label || "£199"}</b>/mo</span>
                    <span className="pm-blurb">{P.monthly?.monthly_full?.blurb || "Unlimited area unlocks"}</span>
                  </button>
                </div>
                <p className="paywall-fine">Starter unlocks 5 areas a month, Plus 10, Unlimited as many as you like. Re-opening an area you've already unlocked this month doesn't count. Cancel anytime. Secure billing via Stripe. By subscribing you agree to our <a href="/terms" onClick={(e) => { e.preventDefault(); window.history.pushState({}, "", "/terms"); window.dispatchEvent(new PopStateEvent("popstate")); }}>Terms &amp; Conditions</a>.</p>
              </div>

              <NotifySignup scope={_scope} scopeLabel={scopeLabel} />

              {showEmail ? (
                <div className="email-unlock">
                  <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                    placeholder="Email on your purchase"
                    onKeyDown={(e) => e.key === "Enter" && onEmailUnlock(email)} />
                  <button className="btn btn-secondary" onClick={() => onEmailUnlock(email)} disabled={emailBusy}>
                    {emailBusy ? <span className="spinner" /> : "Unlock"}
                  </button>
                </div>
              ) : (
                <button className="clear" onClick={() => setShowEmail(true)}>Already bought? Unlock with your email →</button>
              )}
              {notice ? <p className="searcherror" style={{ marginTop: 12 }}>{notice}</p> : null}
              {showDevUnlock() ? (
                <button className="clear" style={{ marginTop: 12 }} onClick={onDev}>Developer: unlock without paying</button>
              ) : null}
            </>
          )}
        </div>
      </div>
    </main>
  );
}

function NotifySignup({ scope, scopeLabel }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState("");
  async function submit() {
    if (!email || !email.includes("@")) { setErr("Enter a valid email"); return; }
    setBusy(true); setErr("");
    try {
      await notifySignup(email, [scope || {}]);
      setDone(true);
    } catch (e) {
      setErr("Couldn't sign up. Try again later.");
    }
    setBusy(false);
  }
  if (done) {
    return (
      <div className="notify-card notify-done">
        <b>✓ You're on the list</b>
        <p>We'll email <b>{email}</b> whenever new providers commission contracts in <b>{scopeLabel}</b>. Data refreshes monthly.</p>
      </div>
    );
  }
  return (
    <div className="notify-card">
      <b>Get alerted when new providers land</b>
      <p className="notify-sub">We refresh the data monthly. Tell us where you're looking and we'll email you when new providers are commissioned in <b>{scopeLabel}</b>. Free — no purchase required.</p>
      <div className="notify-input">
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
          placeholder="your-email@example.com"
          onKeyDown={(e) => e.key === "Enter" && submit()} />
        <button className="btn btn-secondary" onClick={submit} disabled={busy}>
          {busy ? <span className="spinner" /> : "Notify me"}
        </button>
      </div>
      <p className="notify-consent">By signing up you consent to monthly provider-update emails for your chosen areas. Unsubscribe anytime. See our <a href="/privacy">privacy policy</a>.</p>
      {err ? <p className="searcherror">{err}</p> : null}
    </div>
  );
}

/* ── Verifying (after Stripe redirect) ───────────────────────────────────── */
function Verifying({ status, notice, navigate }) {
  return (
    <main className="paywall">
      <div className="wrap narrow">
        <div className="paywall-card" style={{ textAlign: "center" }}>
          {status === "verifying" ? (
            <>
              <span className="spinner" style={{ borderColor: "var(--accent-soft)", borderTopColor: "var(--accent)", width: 28, height: 28, margin: "0 auto 16px" }} />
              <h1 className="paywall-count">Confirming your payment…</h1>
              <p className="sub">One moment while we unlock your provider list.</p>
            </>
          ) : (
            <>
              <h1 className="paywall-count">We hit a snag</h1>
              <p className="sub">{notice || "Couldn't load your list."}</p>
              <button className="btn btn-primary" onClick={() => navigate("/")}>Back to search</button>
            </>
          )}
        </div>
      </div>
    </main>
  );
}

/* ── About ───────────────────────────────────────────────────────────────── */
function About({ navigate }) {
  return (
    <main className="page">
      <div className="wrap narrow">
        <h1>About</h1>
        <div className="prose">
          <h2>Who it&rsquo;s for</h2>
          <p>Landlords, estate agencies and property professionals looking to connect with housing associations, care companies and social housing providers in their area.</p>

          <h2>What you get</h2>
          <ul>
            <li>Who holds the contracts</li>
            <li>Direct contact details</li>
            <li>Which contracts they&rsquo;re approved on</li>
            <li>Which councils they work with</li>
            <li>Which service users they support</li>
          </ul>

          <h2>How it works</h2>
          <p>Enter a postcode. We show you the providers commissioned there. You reach out about your property.</p>

          <h2>What we don&rsquo;t guarantee</h2>
          <p>We can&rsquo;t promise a provider has an active housing need on the day you call — demand shifts daily. But you&rsquo;ll be talking to the right people: the ones actually commissioned to deliver.</p>

          <h2>Get in touch</h2>
          <p>Providers wanting to be listed, updated or removed: <a href="mailto:hello@findahousingprovider.co.uk">hello@findahousingprovider.co.uk</a>.</p>

          <p className="prose-note"><em>Independent directory. Not a letting agent, broker or property manager.</em></p>
        </div>
        <div className="guide-cta">
          <h3>Ready to find providers near you?</h3>
          <button className="btn btn-primary" onClick={() => navigate("/")}>Search by postcode</button>
        </div>
      </div>
    </main>
  );
}

/* ── Privacy Policy (UK GDPR) ─────────────────────────────────────────────── */
function Privacy() {
  return (
    <main className="page">
      <div className="wrap narrow">
        <h1>Privacy Policy</h1>
        <div className="prose">
          <p className="prose-note"><em>Last updated: 12 June 2026</em></p>

          <h2>Who we are</h2>
          <p>Find a Housing Provider (&ldquo;we&rdquo;, &ldquo;us&rdquo;) operates findahousingprovider.co.uk, a directory
            service for property developers, landlords and agents. We are the data controller for the
            personal data described in this policy. Contact: <a href="mailto:hello@findahousingprovider.co.uk">hello@findahousingprovider.co.uk</a>.</p>

          <h2>What we collect and why</h2>
          <ul>
            <li><b>Purchase details.</b> When you buy a report, our payment provider Stripe collects your
              email address and payment details. We receive your email address and the area you purchased,
              so we can deliver your report and let you re-access it later. We never see or store your card
              details. <i>Lawful basis: performance of a contract.</i></li>
            <li><b>Alert sign-ups.</b> If you ask to be notified about new providers in an area, we store
              your email address and the areas you chose. <i>Lawful basis: consent — you can withdraw it at
              any time by emailing us or replying to any alert.</i></li>
            <li><b>Searches.</b> Postcode, borough and county searches are processed to return results.
              We do not build profiles of individual visitors.</li>
            <li><b>Provider listings.</b> Our directory contains business contact information for housing
              and care organisations — organisation names, business addresses, business phone numbers,
              business email addresses and websites. <i>Lawful basis: legitimate interests, in connecting
              the supported-housing sector with property suppliers.</i> If you represent a listed
              organisation, you can ask us to update or remove your details at any time.</li>
          </ul>

          <h2>Cookies and local storage</h2>
          <p>We do not use advertising or analytics cookies. We use browser local storage for one purpose:
            remembering the email address you purchased with, so your reports unlock automatically on
            return visits. You can clear this at any time through your browser settings.</p>

          <h2>Who we share data with</h2>
          <ul>
            <li><b>Stripe</b> — payment processing.</li>
            <li><b>Vercel</b> — website hosting and data storage.</li>
          </ul>
          <p>We do not sell personal data. Our processors may process data outside the UK; where they do,
            transfers are protected by appropriate safeguards such as the UK International Data Transfer
            Agreement or adequacy regulations.</p>

          <h2>How long we keep data</h2>
          <p>Purchase records are kept for 6 years to meet accounting obligations. Alert sign-ups are kept
            until you unsubscribe. Provider listings are reviewed and refreshed monthly.</p>

          <h2>Your rights (UK GDPR)</h2>
          <p>You have the right to access, correct, delete, restrict or object to our processing of your
            personal data, the right to data portability, and the right to withdraw consent at any time.
            To exercise any right, email <a href="mailto:hello@findahousingprovider.co.uk">hello@findahousingprovider.co.uk</a> —
            we respond within one month. You also have the right to complain to the Information
            Commissioner&rsquo;s Office (ico.org.uk).</p>

          <h2>Changes</h2>
          <p>We will post any changes to this policy on this page and update the date at the top.</p>
        </div>
      </div>
    </main>
  );
}

function Terms() {
  return (
    <main className="page">
      <div className="wrap narrow">
        <h1>Terms &amp; Conditions</h1>
        <div className="prose">
          <p className="prose-note"><em>Last updated: 15 June 2026</em></p>

          <p>These terms govern your use of findahousingprovider.co.uk (the &ldquo;Service&rdquo;), operated by
            Find a Housing Provider (&ldquo;we&rdquo;, &ldquo;us&rdquo;, &ldquo;our&rdquo;). By searching the directory or
            subscribing, you agree to these terms. If you do not agree, do not use the Service.</p>

          <h2>1. What we provide</h2>
          <p>The Service is an online directory of supported-living and social-housing providers operating in
            England, compiled from publicly available information and our own research. We provide
            <b> information only</b>. We are not a broker, agent or introducer; we do not arrange, negotiate or
            guarantee any lease, contract or transaction, and we take no commission or success fee on any deal
            you reach with a provider.</p>

          <h2>2. Searching and subscriptions</h2>
          <ul>
            <li>Searching the directory and seeing provider counts is free.</li>
            <li>To unlock provider names and contact details you take a monthly subscription:
              <b> Starter</b> (£49/month, unlock up to 5 areas per month), <b>Plus</b> (£99/month, up to 10 areas)
              or <b>Unlimited</b> (£199/month, no limit). An &ldquo;area&rdquo; is one postcode, borough or county you
              unlock. Re-opening an area you have already unlocked in the same monthly billing period does not
              count again toward your allowance.</li>
            <li>Allowances are per monthly billing period and do not roll over.</li>
          </ul>

          <h2>3. Billing, renewal and cancellation</h2>
          <ul>
            <li>Subscriptions are billed monthly in advance through our payment provider, Stripe, and renew
              automatically until cancelled. Prices are in GBP.</li>
            <li>You can cancel at any time; cancellation takes effect at the end of your current billing period,
              and you keep access until then. We do not provide pro-rata refunds for part-months except where
              required by law.</li>
            <li>The Service supplies digital content and access immediately on subscribing. Where you have a
              statutory 14-day right to cancel, you expressly request that we begin providing it straight away and
              acknowledge that you lose that right once you unlock any area. This does not affect your right to
              cancel future renewals as set out above, or any rights you have where the data is faulty.</li>
            <li>We may change prices or plan features on at least 30 days&rsquo; notice before your next renewal.
              Continued use after a change takes effect constitutes acceptance.</li>
          </ul>

          <h2>4. Acceptable use</h2>
          <p>Your subscription is for your own business use. You must not resell, sub-licence, publish,
            redistribute or bulk-export the directory data, nor scrape, harvest or systematically copy it, nor
            use it to build or train a competing product or database. You must not use the data to send unlawful
            communications, and you are responsible for complying with UK GDPR, PECR and any marketing rules when
            you contact providers.</p>

          <h2>5. Data accuracy</h2>
          <p>Provider information is compiled from public sources and refreshed monthly. While we verify contact
            details where we can, we provide the data <b>&ldquo;as is&rdquo; and make no warranty that it is complete,
            accurate or up to date</b>. The directory is a research aid, not a substitute for your own due
            diligence — you should independently verify any provider and confirm commissioned demand with the
            relevant local authority before relying on it or entering any agreement. Any guides on the Service are
            general information, not legal, financial or professional advice.</p>

          <h2>6. Intellectual property</h2>
          <p>The Service, its compilation of data, design and content are owned by us or our licensors and are
            protected by law. Your subscription grants you a limited, non-exclusive, non-transferable right to
            access and use the data for your own business purposes only, subject to section 4.</p>

          <h2>7. Liability</h2>
          <p>Nothing in these terms limits liability for death or personal injury caused by negligence, for fraud,
            or for anything that cannot be limited by law. Subject to that, we are not liable for any indirect or
            consequential loss, or for loss of profit, business, opportunity or data, arising from your use of the
            Service or reliance on the data; and our total liability to you in any 12-month period is limited to
            the subscription fees you paid us in that period.</p>

          <h2>8. Suspension and termination</h2>
          <p>We may suspend or terminate your access if you breach these terms (in particular section 4), without
            refund where the breach is material. You may stop using the Service and cancel at any time.</p>

          <h2>9. Governing law</h2>
          <p>These terms are governed by the laws of England and Wales, and the courts of England and Wales have
            exclusive jurisdiction.</p>

          <h2>10. Contact</h2>
          <p>Questions about these terms: <a href="mailto:hello@findahousingprovider.co.uk">hello@findahousingprovider.co.uk</a>.
            See also our <a href="/privacy" onClick={(e) => { e.preventDefault(); window.history.pushState({}, "", "/privacy"); window.dispatchEvent(new PopStateEvent("popstate")); }}>Privacy Policy</a>.</p>

          <p className="prose-note"><em>These terms are provided as a starting point and do not constitute legal
            advice. We recommend having them reviewed by a solicitor before relying on them.</em></p>
        </div>
      </div>
    </main>
  );
}

/* ── Footer ──────────────────────────────────────────────────────────────── */
function Footer({ navigate, onManage }) {
  return (
    <footer className="site-footer">
      <div className="wrap">
        <div className="foot-col">
          <button className="brand small" onClick={() => navigate("/")}>
            <span className="mark" aria-hidden="true">F</span> Find a Housing Provider
          </button>
          <p className="foot-note">An independent directory connecting landlords and developers with supported living and social housing providers. Search free; subscribe from £49/month to unlock verified contacts.</p>
        </div>
        <div className="foot-col">
          <h4>Guides</h4>
          {GUIDES.map((g) => <button key={g.slug} className="foot-link" onClick={() => navigate(`/${g.slug}`)}>{g.nav}</button>)}
        </div>
        <div className="foot-col">
          <h4>Site</h4>
          <button className="foot-link" onClick={() => navigate("/")}>Search by postcode</button>
          <button className="foot-link" onClick={() => navigate("/about")}>About &amp; get listed</button>
          <button className="foot-link" onClick={() => navigate("/privacy")}>Privacy policy &amp; GDPR</button>
          <button className="foot-link" onClick={() => navigate("/terms")}>Terms &amp; Conditions</button>
          <button className="foot-link" onClick={onManage}>Manage subscription</button>
        </div>
      </div>
      <div className="wrap foot-base"><span>© {new Date().getFullYear()} findahousingprovider.co.uk · Operated by M.S. Project Zeus CY Limited (Cyprus reg. no. HE 430641)</span></div>
    </footer>
  );
}

/* ── Hero skyline (mixed housing + city, gentle parallax) ─────────────────── */
/* ── Deal-flow diagram: how the four parties connect ─────────────────────── */
function DealFlowDiagram() {
  return (
    <figure className="dealflow" role="img"
      aria-label="Diagram: commissioners refer service users and fund care to supported living providers, who bring in a registered provider, who leases your property. Rent flows back to you on a long fixed-term lease.">
      <svg viewBox="0 0 1120 330" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <marker id="df-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" fill="var(--accent)" />
          </marker>
          <marker id="df-arrow-soft" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" fill="#D49AA4" />
          </marker>
        </defs>

        {/* connecting arrows (top row) */}
        <g fontFamily="Inter, sans-serif" fontSize="13" fill="var(--muted)">
          <line x1="252" y1="120" x2="306" y2="120" stroke="var(--accent)" strokeWidth="2" markerEnd="url(#df-arrow)" />
          <text x="279" y="100" textAnchor="middle" fontWeight="600" fontSize="12">refers &amp;</text>
          <text x="279" y="115" textAnchor="middle" fontWeight="600" fontSize="12">funds care</text>

          <line x1="562" y1="120" x2="616" y2="120" stroke="var(--accent)" strokeWidth="2" markerEnd="url(#df-arrow)" />
          <text x="589" y="100" textAnchor="middle" fontWeight="600" fontSize="12">brings in</text>

          <line x1="872" y1="120" x2="926" y2="120" stroke="var(--accent)" strokeWidth="2" markerEnd="url(#df-arrow)" />
          <text x="899" y="93" textAnchor="middle" fontWeight="600" fontSize="12">leases</text>
          <text x="899" y="108" textAnchor="middle" fontWeight="600" fontSize="12">your property</text>
        </g>

        {/* node 1 — Commissioner */}
        <g>
          <rect x="20" y="68" width="232" height="104" rx="14" fill="#fff" stroke="var(--border)" strokeWidth="1.5" />
          <rect x="20" y="68" width="232" height="6" rx="3" fill="var(--accent)" opacity=".25" />
          <text x="136" y="106" textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="15" fontWeight="700" fill="var(--text)">Care Commissioner</text>
          <text x="136" y="128" textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="12.5" fill="var(--muted)">Council · NHS · consortium</text>
          <text x="136" y="148" textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="12.5" fill="var(--muted)">Funds the care package</text>
        </g>

        {/* node 2 — SL Provider */}
        <g>
          <rect x="310" y="68" width="248" height="104" rx="14" fill="#fff" stroke="var(--border)" strokeWidth="1.5" />
          <rect x="310" y="68" width="248" height="6" rx="3" fill="var(--accent)" opacity=".5" />
          <text x="434" y="106" textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="15" fontWeight="700" fill="var(--text)">Supported Living Provider</text>
          <text x="434" y="128" textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="12.5" fill="var(--muted)">Delivers the care</text>
          <text x="434" y="148" textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="12.5" fill="var(--muted)">Needs housing for referrals</text>
        </g>

        {/* node 3 — RP */}
        <g>
          <rect x="620" y="68" width="248" height="104" rx="14" fill="#fff" stroke="var(--border)" strokeWidth="1.5" />
          <rect x="620" y="68" width="248" height="6" rx="3" fill="var(--accent)" opacity=".75" />
          <text x="744" y="106" textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="15" fontWeight="700" fill="var(--text)">Registered Provider</text>
          <text x="744" y="128" textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="12.5" fill="var(--muted)">Leases &amp; maintains the property</text>
          <text x="744" y="148" textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="12.5" fill="var(--muted)">Handles housing benefit</text>
        </g>

        {/* node 4 — YOU (highlighted) */}
        <g>
          <rect x="930" y="68" width="170" height="104" rx="14" fill="var(--accent)" />
          <text x="1015" y="110" textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="16" fontWeight="800" fill="#fff">Your property</text>
          <text x="1015" y="132" textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="12.5" fill="rgba(255,255,255,.85)">Developer · Landlord</text>
        </g>

        {/* return arrow — rent */}
        <path d="M 1015 180 L 1015 232 L 136 232 L 136 186"
          fill="none" stroke="#D49AA4" strokeWidth="2" strokeDasharray="7 6" markerEnd="url(#df-arrow-soft)" opacity=".0" />
        <path d="M 1015 180 L 1015 232 L 460 232"
          fill="none" stroke="#D49AA4" strokeWidth="2" strokeDasharray="7 6" />
        <path d="M 460 232 L 136 232 L 136 190"
          fill="none" stroke="#D49AA4" strokeWidth="2" strokeDasharray="7 6" markerEnd="url(#df-arrow-soft)" opacity="0" />
        <rect x="330" y="212" width="460" height="40" rx="20" fill="var(--accent-soft)" />
        <text x="560" y="237" textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="13.5" fontWeight="700" fill="var(--accent)">
          Rent paid to you on a long fixed-term lease — occupied or not
        </text>

        {/* baseline caption */}
        <text x="560" y="300" textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="12.5" fill="var(--muted)" fontStyle="italic">
          Care and housing always sit under separate agreements
        </text>
      </svg>
    </figure>
  );
}

function Skyline() {
  return (
    <div className="skyline" aria-hidden="true">
      <div className="sky-row sky-back">
        {Array.from({ length: 7 }).map((_, i) => <BuildingsBack key={i} />)}
      </div>
      <div className="sky-row sky-front">
        {Array.from({ length: 9 }).map((_, i) => <BuildingsFront key={i} />)}
      </div>
    </div>
  );
}

// Back layer: taller, simpler city towers. Tile = 600 wide.
function BuildingsBack() {
  return (
    <svg viewBox="0 0 600 200" width="600" height="200" preserveAspectRatio="xMidYMax meet">
      <g fill="currentColor">
        <rect x="20" y="64" width="52" height="136" />
        <rect x="84" y="34" width="40" height="166" /><rect x="101" y="20" width="6" height="16" />
        <rect x="132" y="98" width="60" height="102" />
        <rect x="200" y="22" width="56" height="178" /><rect x="224" y="8" width="6" height="16" />
        <rect x="268" y="112" width="44" height="88" />
        <rect x="320" y="56" width="50" height="144" />
        <rect x="380" y="90" width="66" height="110" />
        <rect x="456" y="42" width="46" height="158" /><rect x="476" y="28" width="5" height="16" />
        <rect x="512" y="106" width="74" height="94" />
      </g>
    </svg>
  );
}

// Front layer: houses, low blocks, a tower and a crane. Tile = 480 wide.
function BuildingsFront() {
  return (
    <svg viewBox="0 0 480 160" width="480" height="160" preserveAspectRatio="xMidYMax meet">
      <g fill="currentColor">
        <rect x="0" y="120" width="64" height="40" />
        <polygon points="-2,121 32,97 66,121" />
        <rect x="70" y="104" width="44" height="56" />
        <rect x="118" y="72" width="34" height="88" />
        <rect x="156" y="32" width="40" height="128" /><rect x="174" y="16" width="4" height="16" />
        <rect x="200" y="118" width="60" height="42" />
        <polygon points="198,119 230,96 262,119" />
        <rect x="264" y="86" width="40" height="74" />
        <rect x="308" y="58" width="50" height="102" />
        <rect x="366" y="44" width="6" height="116" />
        <rect x="338" y="44" width="86" height="6" />
        <rect x="356" y="38" width="22" height="6" />
        <rect x="410" y="50" width="3" height="26" />
        <rect x="424" y="120" width="56" height="40" />
        <polygon points="422,121 452,99 482,121" />
      </g>
    </svg>
  );
}
