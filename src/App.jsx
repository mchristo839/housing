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
  title: "Find a Housing Provider — Find out who's commissioned to deliver social housing & supported living in your postcode",
  description: "Type a postcode. See the count for free. Unlock the names, contracts and direct contacts when you're ready. Built for landlords, property developers and estate agencies.",
};
const ABOUT_META = {
  title: "About — Find a Housing Provider",
  description: "Find the housing associations, care companies and social housing providers commissioned in your area.",
};
const RESOURCES_META = {
  title: "Resources — Email templates for landlords | Find a Housing Provider",
  description: "Free email templates landlords can use to approach care and housing providers about leasing a property.",
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
    else if (route === "/resources") applyMeta(RESOURCES_META);
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
    const scope = overrideValue
      ? (searchMode === "postcode" ? { postcode: overrideValue }
         : searchMode === "borough" ? { council: overrideValue }
         : { county: overrideValue })
      : activeScope();
    if (!scope) return;
    if (scope.postcode) setPostcode(scope.postcode);
    if (scope.council)  setBorough(scope.council);
    if (scope.county)   setCounty(scope.county);
    setStatus("loading"); setError(""); setNotice("");
    setPreview(null); setUnlocked(null);
    try {
      const pv = await getPreview(scope);
      pv._scope = scope; // remember which query produced these counts
      const em = savedEmail.get();
      if (em) {
        try {
          const full = await unlockByEmail(em, scope);
          savedEmail.set(full.email); setUnlocked(full); setStatus("idle");
          window.scrollTo({ top: 0, behavior: "smooth" });
          return;
        } catch { /* fall through to subscribe gate */ }
      }
      setPreview(pv); setStatus("idle");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setStatus("error");
      setError(e.code === "not_found" || e.code === "postcode_not_found"
        ? `We couldn't find ${scope.postcode ? "that postcode" : "that area"}. Check it and try again.`
        : "Something went wrong. Please try again.");
    }
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

  const isHome = route === "/" || (!guide && !["/about", "/result", "/resources"].includes(route));

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
      ) : route === "/resources" ? (
        <Resources navigate={navigate} />
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
          <span className="mark" aria-hidden="true" />
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
          <button className={route === "/resources" ? "active" : ""} onClick={() => go("/resources")}>Resources</button>
          <button className={route === "/about" ? "active" : ""} onClick={() => go("/about")}>About</button>
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
    <main>
      <section className="hero">
        <div className="wrap hero-grid">
          <div className="hero-left">
          <div className="pillars" aria-label="Built for">
            <span className="pillar">Property Developers</span>
            <span className="pillar">Landlords</span>
            <span className="pillar">Estate Agencies</span>
          </div>
          <h1 className="display">
            Partner with social-housing &amp; supported-living operators
            <span className="em"> direct</span>
          </h1>
          <p className="sub">
            Every provider commissioned in your area, contract-by-contract,
            with verified contact details. £29.99 per postcode — £41.99 with
            our 3 outreach email templates.
          </p>

          <div className="search-tabs" role="tablist" aria-label="Search by">
            {["postcode","borough","county"].map((m) => (
              <button key={m}
                role="tab"
                aria-selected={searchMode === m}
                className={`search-tab ${searchMode === m ? "on" : ""}`}
                onClick={() => setSearchMode(m)}>
                {m === "postcode" ? "Postcode" : m === "borough" ? "Borough / Council" : "County"}
              </button>
            ))}
          </div>

          <div className="searchbar" role="search">
            <input ref={inputRef} value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onSearch()}
              placeholder={placeholders[searchMode]}
              aria-label={`Search by ${searchMode}`}
              spellCheck={false}
              autoCapitalize={searchMode === "postcode" ? "characters" : "words"} />
            <button className="btn btn-primary" onClick={() => onSearch()} disabled={status === "loading"}>
              {status === "loading" ? <span className="spinner" aria-label="Searching" /> : "Find providers"}
            </button>
          </div>
          {error ? <p className="searcherror">{error}</p> : (
            <p className="searchhint">
              Try {examples[searchMode].map((ex, i) => (
                <span key={ex}><span className="ex" onClick={() => onSearch(ex)}>{ex}</span>{i < examples[searchMode].length - 1 ? " · " : ""}</span>
              ))}
            </p>
          )}

          {stats && (
            <div className="trust">
              <div className="stat"><b className="tnum">{stats.providers.toLocaleString()}</b><span>Housing providers</span></div>
              <div className="stat"><b className="tnum">{stats.councils}</b><span>Councils covered</span></div>
              <div className="stat"><b className="tnum">Direct</b><span>Contacts, no agents</span></div>
            </div>
          )}
          </div>
          <div className="hero-right" aria-hidden="true"><Skyline /></div>
        </div>
      </section>

      {/* ────── Who is this for? Three personas, each with pain → mechanism → outcome ────── */}
      <section className="personas">
        <div className="wrap">
          <h2 className="personas-title">Who&rsquo;s asking this question</h2>
          <p className="personas-lead">If you&rsquo;re one of these three, you&rsquo;re in the right place:</p>

          <div className="persona-grid">
            <div className="persona">
              <div className="persona-tag">Property developers</div>
              <h3>Lock in the operator before you break ground</h3>
              <p className="persona-pain">
                Banks want a forward-lease committed before drawdown.
                You don&rsquo;t know which operators are commissioned in the borough
                and the only commercial agent who claims to does charge 1.5% just for an intro.
              </p>
              <p className="persona-outcome">
                Type the postcode of the site. See every provider commissioned by that
                council with the specific contracts they hold — supported living,
                extra care, temporary accommodation, mental health pathway, you name it.
                Email five of them this afternoon. Sign the forward-lease this quarter.
              </p>
            </div>

            <div className="persona">
              <div className="persona-tag">Estate agents</div>
              <h3>Turn the property nobody wants into a 10-year lease</h3>
              <p className="persona-pain">
                You&rsquo;ve got an HMO, a large family home or an ex-care home that
                won&rsquo;t shift. The landlord&rsquo;s losing patience. Every week empty is fee margin gone
                and your reputation chipped.
              </p>
              <p className="persona-outcome">
                Search the postcode. Find the supported-housing operator that needs exactly
                that kind of stock right now — and the dozens more in the council area beside them.
                Introduce them on a 5-15 year FRI lease. Be the hero. Earn the management fee
                for the lifetime of the agreement.
              </p>
            </div>

            <div className="persona">
              <div className="persona-tag">Landlords</div>
              <h3>Cut out the agent. Lease direct.</h3>
              <p className="persona-pain">
                12% management fees. 6 weeks of voids between tenants. Late rent.
                Wall damage. Section 21 reform tightening the screws.
                You bought property for cashflow, not for the headaches.
              </p>
              <p className="persona-outcome">
                One postcode search. Direct contact for every supported-housing operator
                commissioned in your council area. Pitch your property direct.
                Sign a long-term FRI lease at LHA-aligned rent.
                One tenant. No agent. Sleep at night.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ────── The stack: what you get for any area you unlock ────── */}
      <section className="stack">
        <div className="wrap">
          <h2 className="stack-title">What you unlock per provider</h2>
          <p className="stack-lead">The count is free. Pay to unlock the names, contracts and contacts:</p>
          <ul className="stack-list">
            <li>
              <span className="stack-check" aria-hidden="true">✓</span>
              <span><strong>Every commissioned provider</strong> operating in your chosen area — housing associations, care companies, supported living operators, the lot</span>
            </li>
            <li>
              <span className="stack-check" aria-hidden="true">✓</span>
              <span><strong>Direct contact details</strong> — website, business phone and email — verified, no referrals inboxes</span>
            </li>
            <li>
              <span className="stack-check" aria-hidden="true">✓</span>
              <span><strong>The specific contracts they hold</strong> — what service, which commissioner, named where public</span>
            </li>
            <li>
              <span className="stack-check" aria-hidden="true">✓</span>
              <span><strong>Which councils they work with</strong> — so you can see who works across borough boundaries</span>
            </li>
            <li>
              <span className="stack-check" aria-hidden="true">✓</span>
              <span><strong>Which service users they support</strong> — older people, learning disabilities, mental health, care leavers, asylum seekers, rough sleepers, domestic abuse survivors</span>
            </li>
            <li>
              <span className="stack-check" aria-hidden="true">✓</span>
              <span><strong>Regional and national providers too</strong> — pan-London frameworks, UK-wide operators, Home Office asylum contractors</span>
            </li>
            <li>
              <span className="stack-check" aria-hidden="true">✓</span>
              <span><strong>Local Housing Allowance rates</strong> — so you walk into the conversation knowing what they can pay</span>
            </li>
            <li>
              <span className="stack-check" aria-hidden="true">✓</span>
              <span><strong>A pre-written outreach email</strong> for each provider — copy, paste, send</span>
            </li>
            <li>
              <span className="stack-check" aria-hidden="true">✓</span>
              <span><strong>Full PDF report</strong> — take it into the next meeting, share with your client, attach to your investment deck</span>
            </li>
          </ul>
        </div>
      </section>

      {/* ────── Three-step how-it-works ────── */}
      <section className="explain">
        <div className="wrap">
          <h2 className="explain-title">Search free. Pay £29.99. Download the PDF.</h2>
          <div className="steps">
            <div className="step">
              <div className="n">1. Type a postcode — free</div>
              <p>We instantly show you <em>how many</em> social housing and supported living providers are commissioned to deliver there. No email, no signup.</p>
            </div>
            <div className="step">
              <div className="n">2. Unlock for £29.99</div>
              <p>One-off payment per postcode. No subscription, no auto-renew. You get every provider in that council area — names, contracts, councils they work with, service users they support, and verified direct contacts.</p>
            </div>
            <div className="step">
              <div className="n">3. Download the PDF</div>
              <p>The full report is yours to keep. Use the contacts to pitch your property direct. Go direct.</p>
            </div>
          </div>

          <div className="explain-foot">
            <p className="explain-honest">
              <strong>What you get:</strong> the data. Names, contracts, councils, service users and verified direct contacts for every supported housing provider commissioned in your chosen area.
              <br /><br />
              <strong>What we don&rsquo;t guarantee:</strong> that a provider has an immediate need on the day you call. We&rsquo;re a data product — not a brokerage. We hand you the right people and the right contracts to discuss. What happens in the conversation is between you and them.
            </p>
          </div>
        </div>
      </section>

      <section className="teasers">
        <div className="wrap">
          <h2>Guides for landlords</h2>
          <p className="teasers-lead">New to leasing property to the care sector? Start here.</p>
          <div className="teaser-grid">
            {GUIDES.map((g) => (
              <button key={g.slug} className="teaser-card" onClick={() => navigate(`/${g.slug}`)}>
                <h3>{g.teaser.title}</h3>
                <p>{g.teaser.blurb}</p>
                <span className="readmore">Read the guide →</span>
              </button>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}

/* ── Subscribe gate (preview → buy a tier / unlock by email) ──────────────── */
function SubscribeGate({ preview, onSubscribe, busy, notice, onEmailUnlock, emailBusy, onDev, onBack, addTemplates, setAddTemplates }) {
  const { council, countyName, region, total, tiers, pricing, postcode, _scope } = preview;
  const [email, setEmail] = useState("");
  const [showEmail, setShowEmail] = useState(false);
  const P = pricing || {};
  const scope = _scope || {};
  const isCounty = !!scope.county;
  const activeTier = isCounty ? (P.county || { label: "£49.99", name: "County" })
                              : (P.postcode || { label: "£29.99", name: "Postcode" });
  const scopeLabel = scope.county || scope.council || scope.postcode || council;
  const TEMPLATES_PRICE = "£12.00";
  const totalLabel = addTemplates
    ? (isCounty ? "£61.99" : "£41.99")
    : activeTier.label;
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
              <p className="sub">Names, contracts and direct contacts are unlocked when you buy. Pick the area you want.</p>

              <ul className="paywall-tiers">
                <li><b className="tnum">{tiers.local}</b> hold a contract with {council}</li>
                {countyName && tiers.county ? <li><b className="tnum">{tiers.county}</b> county-wide across {countyName}</li> : null}
                <li><b className="tnum">{tiers.regional}</b> active across {region || "the region"}</li>
                <li><b className="tnum">{tiers.national}</b> UK-wide providers</li>
              </ul>

              <label className="upsell" htmlFor="add-templates">
                <input id="add-templates" type="checkbox"
                  checked={addTemplates} onChange={(e) => setAddTemplates(e.target.checked)} />
                <div className="upsell-body">
                  <b>Add 3 outreach email templates — {TEMPLATES_PRICE}</b>
                  <span>Three proven scripts for approaching supported-living and social-housing providers — direct lease offer, portfolio partnership pitch, off-market building conversion. Sent to you immediately after checkout.</span>
                </div>
              </label>

              <div className="paywall-buy">
                <div className="paywall-price">
                  <b className="tnum">{totalLabel}</b>
                  <span>one-off · PDF + {addTemplates ? "email templates" : "download the PDF"}</span>
                </div>
                <button className="btn btn-primary" onClick={() => onSubscribe(isCounty ? "county" : "postcode")} disabled={busy}>
                  {busy ? <span className="spinner" /> : `Unlock — ${totalLabel}`}
                </button>
              </div>
              <p className="paywall-fine">One-off payment. Every provider in this area — names, contracts, councils, service users, and verified direct contacts. Yours to keep. Secure billing via Stripe.</p>

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
        {preview.lha ? <LhaTeaser lha={preview.lha} /> : null}
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
      {err ? <p className="searcherror">{err}</p> : null}
    </div>
  );
}

function LhaTeaser({ lha }) {
  const rows = [["Shared room", lha.shared], ["1 bedroom", lha.bed1], ["2 bedrooms", lha.bed2],
    ["3 bedrooms", lha.bed3], ["4 bedrooms", lha.bed4]].filter(([, v]) => v != null);
  return (
    <div className="lha-teaser">
      <h3>Local Housing Allowance — {lha.council}</h3>
      <p className="meta">{lha.brma} BRMA · 2026/27 monthly rates</p>
      <table className="lha-table">
        <thead><tr><th>Room entitlement</th><th>LHA / mo</th><th>+10%</th><th>+20%</th></tr></thead>
        <tbody>
          {rows.map(([label, v]) => (
            <tr key={label}>
              <td>{label}</td>
              <td className="tnum">£{Math.round(v).toLocaleString()}</td>
              <td className="tnum">£{Math.round(v * 1.1).toLocaleString()}</td>
              <td className="tnum">£{Math.round(v * 1.2).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="lha-note">
        Social housing providers typically pay rent in line with LHA. Where demand is high, you can often
        negotiate <b>LHA plus 10–20%</b> (shown above). The full categorised provider list — housing
        associations, asylum & homelessness providers, and supported-living providers by client group — is
        included in your downloadable report.
      </p>
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

/* ── Footer ──────────────────────────────────────────────────────────────── */
function Footer({ navigate, onManage }) {
  return (
    <footer className="site-footer">
      <div className="wrap">
        <div className="foot-col">
          <button className="brand small" onClick={() => navigate("/")}>
            <span className="mark" aria-hidden="true" /> Find a Housing Provider
          </button>
          <p className="foot-note">An independent directory connecting landlords with care and housing providers. £49.99/month, unlimited lists.</p>
        </div>
        <div className="foot-col">
          <h4>Guides</h4>
          {GUIDES.map((g) => <button key={g.slug} className="foot-link" onClick={() => navigate(`/${g.slug}`)}>{g.nav}</button>)}
        </div>
        <div className="foot-col">
          <h4>Site</h4>
          <button className="foot-link" onClick={() => navigate("/")}>Search by postcode</button>
          <button className="foot-link" onClick={() => navigate("/resources")}>Email templates</button>
          <button className="foot-link" onClick={() => navigate("/about")}>About &amp; get listed</button>
          <button className="foot-link" onClick={onManage}>Manage subscription</button>
        </div>
      </div>
      <div className="wrap foot-base"><span>© {new Date().getFullYear()} findahousingprovider.co.uk</span></div>
    </footer>
  );
}

/* ── Hero skyline (mixed housing + city, gentle parallax) ─────────────────── */
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
