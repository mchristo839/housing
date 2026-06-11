import { useMemo, useState, useEffect } from "react";
import { SECTORS, formatEmployees } from "../data.js";
import { areaContractsFor } from "../message.js";
import { generateReport } from "../pdf.js";

export default function Results({ result, onNewSearch, postcode }) {
  const [sectors, setSectors] = useState(new Set());
  const [sizes, setSizes] = useState(new Set());     // "SME" | "Large"
  const [includeNational, setIncludeNational] = useState(true);
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [active, setActive] = useState(null);        // provider for modal
  const [pdfBusy, setPdfBusy] = useState(false);

  async function downloadPdf() {
    setPdfBusy(true);
    try { await generateReport(result); } catch (e) { console.error(e); }
    setPdfBusy(false);
  }

  // server returns fully-hydrated provider objects, grouped by tier
  const groups = useMemo(() => ({
    local: result.local || [], county: result.county || [], regional: result.regional || [], national: result.national || [],
  }), [result]);

  const match = (p) => {
    if (verifiedOnly && !p.verification?.verified) return false;
    if (sectors.size && !(p.sector || []).some((s) => sectors.has(s))) return false;
    if (sizes.size) {
      const isSme = p.is_sme === true;
      const ok = (sizes.has("SME") && isSme) || (sizes.has("Large") && p.is_sme === false);
      if (!ok) return false;
    }
    return true;
  };

  // Verified providers sort above Listed inside each tier
  const sortVerifiedFirst = (a, b) => {
    const av = a.verification?.verified ? 0 : 1;
    const bv = b.verification?.verified ? 0 : 1;
    return av - bv;
  };
  const filtered = {
    local:    groups.local.filter(match).sort(sortVerifiedFirst),
    county:   groups.county.filter(match).sort(sortVerifiedFirst),
    regional: groups.regional.filter(match).sort(sortVerifiedFirst),
    national: includeNational ? groups.national.filter(match).sort(sortVerifiedFirst) : [],
  };
  const verifiedCount = [...filtered.local, ...filtered.county, ...filtered.regional, ...filtered.national]
    .filter(p => p.verification?.verified).length;
  const totalShown = filtered.local.length + filtered.county.length + filtered.regional.length + filtered.national.length;

  const toggle = (set, val, setter) => {
    const next = new Set(set); next.has(val) ? next.delete(val) : next.add(val); setter(next);
  };
  const clearAll = () => { setSectors(new Set()); setSizes(new Set()); setIncludeNational(true); setVerifiedOnly(false); };
  const anyFilter = sectors.size || sizes.size || !includeNational || verifiedOnly;

  const region = result.region || "this area";
  const pc = (result.postcode || postcode || "").toUpperCase();
  const ctx = { council: result.council, county: result.countyName, region: result.region };

  return (
    <main className="results">
      <div className="wrap">
        <div className="resbar">
          <div>
            <h2>
              Providers covering <span className="loc">{result.council || postcode}</span>
            </h2>
            <p className="meta">
              {pc} · {region} · {totalShown} provider{totalShown === 1 ? "" : "s"}
              {filtered.local.length > 0 && (
                <> · <b style={{ color: "var(--accent)" }}>{filtered.local.length}</b> hold a contract with this council</>
              )}
            </p>
          </div>
          <div className="resbar-actions">
            <button className="btn btn-primary" onClick={downloadPdf} disabled={pdfBusy}>
              {pdfBusy ? <span className="spinner" /> : "↓ Download PDF report"}
            </button>
            <button className="btn btn-secondary" onClick={onNewSearch}>New search</button>
          </div>
        </div>

        <div className="trust-banner" role="note">
          <span className="trust-tick">✓</span>
          <div>
            <b>Our 4-step verification:</b> for every <span className="badge-verified" style={{marginLeft:'4px'}}>✓ Verified</span> provider we check the website owner, confirm at least one housing service, and verify contact details.
            {" "}<b className="tnum">{verifiedCount}</b> of {totalShown} on this page are verified.
            {" "}<a href="#/about" onClick={(e)=>{e.preventDefault(); window.location.hash='#/about';}}>How it works →</a>
          </div>
        </div>

        <div className="reslayout">
          {/* ── Filters ── */}
          <aside className="filters" aria-label="Filters">
            <div className="group">
              <h4>Sector</h4>
              {SECTORS.map((s) => (
                <button key={s} className={`chip ${sectors.has(s) ? "on" : ""}`}
                  onClick={() => toggle(sectors, s, setSectors)} aria-pressed={sectors.has(s)}>{s}</button>
              ))}
            </div>
            <div className="group">
              <h4>Organisation size</h4>
              {["SME", "Large"].map((s) => (
                <button key={s} className={`chip ${sizes.has(s) ? "on" : ""}`}
                  onClick={() => toggle(sizes, s, setSizes)} aria-pressed={sizes.has(s)}>{s}</button>
              ))}
            </div>
            <div className="group">
              <h4>Geography</h4>
              <button className={`chip ${includeNational ? "on" : ""}`}
                onClick={() => setIncludeNational((v) => !v)} aria-pressed={includeNational}>
                Include UK-wide providers
              </button>
            </div>
            <div className="group">
              <h4>Data quality</h4>
              <button className={`chip ${verifiedOnly ? "on" : ""}`}
                onClick={() => setVerifiedOnly((v) => !v)} aria-pressed={verifiedOnly}
                title="Show only providers we have manually verified using our 4-step check">
                ✓ Verified providers only
              </button>
            </div>
            {anyFilter ? <button className="clear" onClick={clearAll}>Clear all filters</button> : null}
          </aside>

          {/* ── Results ── */}
          <section>
            {totalShown === 0 ? (
              <div className="empty">
                No providers match these filters for {result.council || postcode}.{" "}
                {anyFilter ? <button className="ex" style={{ background: "none", border: 0, color: "var(--accent)", cursor: "pointer", fontWeight: 600 }} onClick={clearAll}>Clear filters</button> : "Try a nearby postcode."}
              </div>
            ) : (
              <>
                <Tier title="Local contracts" subtitle={`Hold a contract with ${result.council || "this council"}`} items={filtered.local} onOpen={setActive} ctx={ctx} />
                {result.countyName ? <Tier title="County contracts" subtitle={`County-wide across ${result.countyName}`} items={filtered.county} onOpen={setActive} ctx={ctx} /> : null}
                <Tier title="Regional contracts" subtitle={`Active across ${region}`} items={filtered.regional} onOpen={setActive} ctx={ctx} />
                <Tier title="National contracts" subtitle="UK-wide providers" items={filtered.national} onOpen={setActive} ctx={ctx} />
              </>
            )}
          </section>
        </div>
      </div>

      {active && <ProviderModal p={active} ctx={ctx} onClose={() => setActive(null)} />}
    </main>
  );
}

function Tier({ title, subtitle, items, onOpen, ctx, initial = 12 }) {
  const [shown, setShown] = useState(initial);
  if (!items.length) return null;
  const visible = items.slice(0, shown);
  const remaining = items.length - shown;
  return (
    <>
      <div className="tier-label">
        <h3>{title}{subtitle ? <span className="tier-sub"> — {subtitle}</span> : null}</h3>
        <span className="line" /><span className="meta tnum">{items.length}</span>
      </div>
      <div className="cards">
        {visible.map((p, i) => <ProviderCard key={p.id || `${p.name}-${i}`} p={p} i={i} ctx={ctx} onOpen={onOpen} />)}
      </div>
      {remaining > 0 && (
        <button className="btn btn-secondary showmore" onClick={() => setShown((n) => n + 24)}>
          Show {Math.min(24, remaining)} more <span className="meta">({remaining} hidden)</span>
        </button>
      )}
    </>
  );
}

function ProviderCard({ p, i, ctx, onOpen }) {
  const emp = formatEmployees(p.employees);
  const regionCount = (p.regions || []).length;
  // contract name(s) relevant to the searched postcode
  const area = ctx ? areaContractsFor(p, ctx.council, ctx.region, ctx.county) : { scope: "none", entries: [] };
  const relTitles = area.entries.flatMap((e) => e.titles || []);
  const via = area.entries.find((e) => e.via)?.via;
  const relLabel = area.scope === "council" ? `Contract with ${ctx.council}`
    : area.scope === "county" ? `County-wide contract (${ctx.county})`
    : area.scope === "region" ? `Region-wide contract (${ctx.region})`
    : area.scope === "national" ? "National contract" : null;
  return (
    <article className="card" style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}
      onClick={() => onOpen(p)} role="button" tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onOpen(p))}>
      <div>
        <div className="head">
          <span className="logo" aria-hidden="true">{initials(p.name)}</span>
          <h3>{p.name}</h3>
          {p.verification?.verified
            ? <span className="badge-verified" title="Passed our 4-step verification: website, services, contacts confirmed">✓ Verified</span>
            : <span className="badge-listed" title="On a government framework contract. Awaiting manual verification.">Listed</span>}
          {p.in_network ? <span className="badge-net" title="In our direct provider network">In network</span> : null}
          {p.badge ? <span className="badge-ho">{p.badge}</span> : null}
          {p.website_unverified ? <span className="badge-uv" title="Website unverified">Unverified</span> : null}
        </div>
        {p.description ? <p className="desc">{p.description}</p> : null}
        <div className="tags">
          <span className="tag cat">{p.primary_cat}</span>
          {p.scope ? <span className="tag">{p.scope}</span> : null}
          {regionCount > 1 ? <span className="tag">{regionCount} regions</span> : null}
        </div>
        {relTitles.length ? (
          <div className="card-contract">
            <span className="cc-label">{relLabel}{via ? <span className="cc-via"> · via {via}</span> : null}</span>
            <ul>
              {relTitles.slice(0, 2).map((t, j) => <li key={j}>{t}</li>)}
            </ul>
            <button className="cc-viewall" onClick={(e) => { e.stopPropagation(); onOpen(p); }}>
              {relTitles.length > 2 ? `View all ${relTitles.length} contracts →` : "View contract detail →"}
            </button>
          </div>
        ) : null}
        <div className="metarow">
          {emp ? <span><b className="tnum">{emp}</b> staff</span> : null}
          {p.is_sme === true ? <span>SME</span> : null}
          {p.hq_address ? <span>{shortHQ(p.hq_address)}</span> : null}
        </div>
      </div>
      <div className="side" onClick={(e) => e.stopPropagation()}>
        {p.contracts ? (
          <div className="contracts"><b className="tnum">{p.contracts}</b><span>contracts</span></div>
        ) : <span />}
        <div className="actions">
          {p.email ? <a className="iconbtn" href={`mailto:${p.email}`} title={`Email ${p.name}`} aria-label="Email">✉</a>
            : p.contact_page ? <a className="iconbtn" href={withHttp(p.contact_page)} target="_blank" rel="noopener" title="Contact form" aria-label="Contact form">✎</a> : null}
          {p.phone ? <a className="iconbtn" href={`tel:${p.phone.replace(/\s/g, "")}`} title={`Call ${p.name}`} aria-label="Call">☎</a> : null}
          {p.website && !p.website_unverified ? <a className="iconbtn" href={withHttp(p.website)} target="_blank" rel="noopener" title="Website" aria-label="Website">↗</a> : null}
        </div>
      </div>
    </article>
  );
}

function ProviderModal({ p, ctx, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const emp = formatEmployees(p.employees);
  const area = areaContractsFor(p, ctx.council, ctx.region, ctx.county);
  const brief = (p.description || p.notes || "").slice(0, 320);
  const whatTheyDo = (p.client_groups || []).join(", ");
  const careType = (p.sector || []).filter((s) => !/^homecare$/i.test(s)).join(", ") || (p.sector || []).join(", ");
  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={p.name}>
        <div className="modal-h">
          <span className="logo" aria-hidden="true">{initials(p.name)}</span>
          <div>
            <h2>{p.name}</h2>
            <p className="meta" style={{ margin: "4px 0 0" }}>
              {p.primary_cat}{p.scope ? ` · ${p.scope}` : ""}
              {p.website_unverified ? " · website unverified" : ""}
            </p>
          </div>
          <button className="modal-close" onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className="modal-b">
          {brief ? <p className="lead">{brief}{(p.description || p.notes || "").length > 320 ? "…" : ""}</p> : null}

          <dl className="kv">
            {whatTheyDo ? <><dt>What they do</dt><dd>{whatTheyDo}</dd></> : null}
            {careType ? <><dt>Contracted care</dt><dd>{careType}</dd></> : null}
            {emp ? <><dt>Size</dt><dd className="tnum">{emp} staff{p.employee_confidence ? ` (${p.employee_confidence.toLowerCase()} confidence)` : ""}</dd></> : null}
            {p.scope ? <><dt>Coverage</dt><dd>{p.scope}{p.councils?.length ? ` · ${p.councils.length} councils` : ""}</dd></> : null}
          </dl>

          <AreaContracts area={area} council={ctx.council} county={ctx.county} region={ctx.region} totalCouncils={p.councils?.length || 0} />

          <div className="profile-contact">
            <h4>Contact</h4>
            {p.email ? <div><span>Email</span><a href={`mailto:${p.email}`}>{p.email}</a></div> : null}
            {p.phone ? <div><span>Telephone</span><a href={`tel:${p.phone.replace(/\s/g, "")}`}>{p.phone}</a></div> : null}
            {!p.email && p.contact_page ? <div><span>Contact</span><a href={withHttp(p.contact_page)} target="_blank" rel="noopener">Contact form</a></div> : null}
            {p.website && !p.website_unverified ? <div><span>Website</span><a href={withHttp(p.website)} target="_blank" rel="noopener">{p.website.replace(/^https?:\/\//, "").replace(/\/$/, "")}</a></div> : null}
            {p.hq_address ? <div><span>Head office</span><span>{p.hq_address}</span></div> : null}
          </div>

          {p.charity ? (
            <div className="charitybox">
              <h4>Registered charity</h4>
              <div>No. {p.charity.number}{p.charity.status ? ` · ${p.charity.status}` : ""}
                {p.charity.income ? ` · income £${Number(p.charity.income).toLocaleString()}` : ""}</div>
              {p.charity.activities ? <p style={{ margin: "8px 0 0", color: "var(--muted)" }}>{p.charity.activities}</p> : null}
            </div>
          ) : null}

          <div className="modal-actions">
            {p.email ? <a className="btn btn-primary" href={`mailto:${p.email}`}>Email {firstName(p.name)}</a>
              : p.contact_page ? <a className="btn btn-primary" href={withHttp(p.contact_page)} target="_blank" rel="noopener">Open contact form</a> : null}
            {p.phone ? <a className="btn btn-secondary" href={`tel:${p.phone.replace(/\s/g, "")}`}>Call {p.phone}</a> : null}
            {p.website && !p.website_unverified ? <a className="btn btn-secondary" href={withHttp(p.website)} target="_blank" rel="noopener">Visit website</a> : null}
          </div>
        </div>
      </div>
    </div>
  );
}

// All contracts relevant to the searched postcode — names only (no commissioner
// or other suppliers), with the service type and value where available.
function AreaContracts({ area, council, county, region, totalCouncils }) {
  if (area.scope === "none") {
    return (
      <div className="contracts-list">
        <h4>Contracts relating to {council}</h4>
        <p className="meta">No council-specific contract is recorded for {council}. This provider operates more widely
          {region ? ` across ${region}` : ""}{totalCouncils ? ` (${totalCouncils} council areas nationally)` : ""}.</p>
      </div>
    );
  }
  // flatten into individual contracts, each with its service type / value
  const items = [];
  for (const e of area.entries) {
    for (const t of (e.titles || [])) items.push({ title: t, sectors: e.sectors || [], value: e.value, via: e.via });
    if (!(e.titles || []).length) items.push({ title: `${e.sectors?.join(" / ") || "Care & housing"} provision`, sectors: e.sectors || [], value: e.value, via: e.via });
  }
  const title = area.scope === "council" ? `Contracts held with ${council}`
    : area.scope === "county" ? `County-wide contracts (${county})`
    : area.scope === "region" ? `Region-wide contracts (${region})`
    : `National contracts`;
  const otherCouncils = area.scope === "council" && totalCouncils ? totalCouncils - 1 : 0;
  return (
    <div className="contracts-list">
      <h4>{title} · {items.length}</h4>
      {items.map((it, i) => (
        <div className="contract-item" key={i}>
          <div className="contract-title">{it.title}</div>
          <div className="contract-tags">
            {it.sectors.map((s) => <span className="tag" key={s}>{s}</span>)}
            {it.via ? <span className="tag via">via {it.via}</span> : null}
            {it.value ? <span className="contract-val">{it.value}</span> : null}
          </div>
        </div>
      ))}
      {otherCouncils > 0 && (
        <p className="meta" style={{ marginTop: "8px" }}>This provider is also active in {otherCouncils} other council area{otherCouncils === 1 ? "" : "s"} nationally.</p>
      )}
    </div>
  );
}

/* helpers */
function initials(name) {
  return name.replace(/[^a-zA-Z ]/g, "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
}
function firstName(name) { return name.split(/[\s/]/)[0]; }
function shortHQ(addr) { const parts = addr.split(","); return parts[parts.length - 1].trim() || addr; }
function withHttp(u) { return /^https?:\/\//.test(u) ? u : `https://${u}`; }
