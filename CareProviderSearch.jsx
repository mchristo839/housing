import { useState, useEffect, useRef } from "react";

// ─── REAL PROVIDER DATA ──────────────────────────────────────────────────────
// Normalise a council name from postcodes.io to match our DB keys
function normCouncil(name) {
  if (!name) return "";
  let n = name.toLowerCase().trim();
  n = n.replace(/,\s*city of$/, " city");
  n = n.replace(/\b(council|metropolitan borough|borough|county|city|district|unitary authority|mbc|lbc|the )\b/g, " ");
  n = n.replace(/[^\w\s]/g, " ");
  n = n.replace(/\s+/g, " ").trim();
  return n;
}

// All council keys from DB, pre-normalised for lookup
const COUNCIL_NORM_MAP = {
  "east riding of yorkshire": ["East Riding of Yorkshire Council","EAST RIDING OF YORKSHIRE COUNCIL",".East Riding Of Yorkshire Council"],
  "adur": ["Adur District Council"],
  "brighton hove": ["Brighton & Hove City Council","Brighton and Hove City Council","BRIGHTON & HOVE CITY COUNCIL"],
  "barnsley": ["Barnsley Metropolitan Borough Council"],
  "basingstoke deane": ["Basingstoke & Deane Borough Council","Basingstoke and Deane Borough Council"],
  "bath and north east somerset": ["Bath and North East Somerset Council"],
  "bedford": ["Bedford Borough Council"],
  "birmingham": ["Birmingham City Council"],
  "blackburn with darwen": ["Blackburn with Darwen"],
  "blackpool": ["Blackpool Council"],
  "bolton": ["Bolton Council"],
  "bradford": ["Bradford Metropolitan District Council","City of Bradford Metropolitan District Council","CITY OF BRADFORD METROPOLITAN DISTRICT COUNCIL"],
  "brighton": ["Brighton & Hove City Council","Brighton and Hove City Council"],
  "bristol": ["Bristol City Council","BRISTOL CITY COUNCIL"],
  "buckinghamshire": ["Buckinghamshire Council","Buckinghamshire County Council"],
  "bury": ["Bury Council"],
  "calderdale": ["Calderdale Council","The Borough Council of Calderdale"],
  "cambridge": ["Cambridge City Council"],
  "cambridgeshire": ["Cambridgeshire County Council"],
  "peterborough": ["Peterborough City Council","Cambridgeshire County Council and Peterborough City Council"],
  "canterbury": ["Canterbury City Council"],
  "central bedfordshire": ["Central Bedfordshire Council"],
  "cheltenham": ["Cheltenham Borough Council"],
  "cheshire east": ["Cheshire East Borough Council","CHESHIRE EAST COUNCIL"],
  "cheshire west and chester": ["Cheshire west and Chester Borough Council"],
  "colchester": ["Colchester City Council"],
  "cornwall": ["Cornwall Council","CORNWALL COUNCIL"],
  "coventry": ["Coventry City Council","Coventry City Council (COV)"],
  "cumbria": ["Cumbria County Council"],
  "darlington": ["Darlington Borough Council"],
  "derby": ["Derby City Council","DERBY CITY COUNCIL"],
  "derbyshire": ["Derbyshire County Council","DERBYSHIRE COUNTY COUNCIL"],
  "devon": ["Devon County Council"],
  "doncaster": ["City of Doncaster Council","Doncaster Council","Doncaster MBC"],
  "dorset": ["Dorset Council","Dorset County Council"],
  "dudley": ["Dudley Metropolitan Borough Council","DUDLEY MBC"],
  "durham": ["Durham County Council","DURHAM COUNTY COUNCIL"],
  "east suffolk": ["East Suffolk Council"],
  "east sussex": ["East Sussex County Council"],
  "erewash": ["Erewash Borough Council"],
  "essex": ["Essex County Council","ESSEX COUNTY COUNCIL"],
  "exeter": ["Exeter City Council"],
  "folkestone and hythe": ["Folkestone and Hythe District Council"],
  "gateshead": ["Gateshead Council","GATESHEAD COUNCIL"],
  "gloucester": ["Gloucester City Council"],
  "gloucestershire": ["Gloucestershire County Council"],
  "gosport": ["Gosport Borough Council"],
  "hampshire": ["Hampshire County Council","HAMPSHIRE COUNTY COUNCIL"],
  "halton": ["Halton Borough Council"],
  "harrow": ["Harrow Council"],
  "hartlepool": ["Hartlepool Borough Council"],
  "hastings": ["Hastings Borough Council"],
  "herefordshire": ["Herefordshire Council"],
  "hertfordshire": ["Hertfordshire County Council  - Adult Care Services","Hertfordshire County Council - Children's Services"],
  "hull": ["Hull City Council"],
  "kingston upon hull": ["Hull City Council"],
  "islington": ["Islington Council","ISLINGTON COUNCIL","Islington"],
  "ipswich": ["Ipswich Borough Council"],
  "isle of wight": ["Isle of Wight Council"],
  "kent": ["Kent County Council","KENT COUNTY COUNCIL"],
  "kirklees": ["Kirklees Council"],
  "knowsley": ["Knowsley Council"],
  "lancashire": ["Lancashire County Council"],
  "lancaster": ["Lancaster City Council"],
  "leeds": ["Leeds City Council"],
  "leicester": ["Leicester City Council"],
  "leicestershire": ["Leicestershire County Council"],
  "lincolnshire": ["Lincolnshire County Council","LINCOLNSHIRE COUNTY COUNCIL"],
  "liverpool": ["Liverpool City Council"],
  "barking and dagenham": ["London Borough of Barking and Dagenham","London Borough Of Barking And Dagenham","London Borough of Barking & Dagenham"],
  "barnet": ["London Borough of Barnet Council"],
  "bexley": ["London Borough of Bexley","London Borough Of Bexley"],
  "brent": ["London Borough of Brent"],
  "bromley": ["London Borough of Bromley","London Borough Of Bromley Council","London Borough of Bromley Council"],
  "camden": ["London Borough of Camden","London Borough of Camden Council","London Borough Of Camden Council"],
  "enfield": ["London Borough of Enfield"],
  "hackney": ["London Borough of Hackney"],
  "hammersmith and fulham": ["London Borough of Hammersmith & Fulham"],
  "haringey": ["London Borough of Haringey","London Borough Of Haringey"],
  "havering": ["London Borough of Havering","LONDON BOROUGH OF HAVERING"],
  "hillingdon": ["London Borough of Hillingdon"],
  "hounslow": ["London Borough of Hounslow","LONDON BOROUGH OF HOUNSLOW"],
  "lambeth": ["London Borough of Lambeth"],
  "lewisham": ["London Borough of Lewisham"],
  "merton": ["London Borough of Merton"],
  "redbridge": ["London Borough of Redbridge"],
  "richmond upon thames": ["London Borough of Richmond upon Thames"],
  "sutton": ["London Borough of Sutton"],
  "wandsworth": ["London Borough of Wandsworth"],
  "tower hamlets": ["Tower Hamlets","LONDON BOROUGH OF TOWER HAMLETS"],
  "city of london": ["City of London Corporation"],
  "greenwich": ["Royal Borough Of Greenwich"],
  "kingston upon thames": ["The Royal Borough of Kingston upon Thames"],
  "westminster": ["Westminster City Council"],
  "luton": ["Luton Council"],
  "manchester": ["Manchester City Council"],
  "medway": ["Medway Council"],
  "middlesbrough": ["Middlesbrough Council"],
  "milton keynes": ["Milton Keynes Council","Milton Keynes City Council"],
  "newcastle upon tyne": ["Newcastle City Council","NEWCASTLE CITY COUNCIL"],
  "norfolk": ["Norfolk County Council"],
  "north east lincolnshire": ["North East Lincolnshire Council"],
  "north hertfordshire": ["North Hertfordshire District Council"],
  "north lincolnshire": ["North Lincolnshire Council"],
  "north northamptonshire": ["North Northamptonshire Council"],
  "north somerset": ["North Somerset Council"],
  "north tyneside": ["North Tyneside Council"],
  "northamptonshire": ["Northamptonshire County Council"],
  "northumberland": ["Northumberland County Council"],
  "nottingham": ["Nottingham City Council","NOTTINGHAM CITY COUNCIL"],
  "nottinghamshire": ["Nottinghamshire County Council"],
  "oxford": ["Oxford City Council"],
  "oxfordshire": ["Oxfordshire County Council"],
  "plymouth": ["Plymouth City Council"],
  "preston": ["Preston City Council"],
  "reading": ["Reading Borough Council","READING BOROUGH COUNCIL"],
  "redcar and cleveland": ["Redcar & Cleveland Borough Council","REDCAR & CLEVELAND BOROUGH COUNCIL"],
  "redditch": ["Redditch Borough Council"],
  "rochdale": ["Rochdale Metropolitan Borough Council"],
  "rotherham": ["Rotherham Metropolitan Borough Council","Rotherham MBC"],
  "salford": ["Salford City Council"],
  "sandwell": ["Sandwell Metropolitan Borough Council","SANDWELL METROPOLITAN BOROUGH COUNCIL"],
  "sefton": ["Sefton Council"],
  "sheffield": ["Sheffield City Council"],
  "shropshire": ["Shropshire Council","SHROPSHIRE COUNCIL"],
  "solihull": ["Solihull MBC (SOL)","SOLIHULL METROPOLITAN BOROUGH COUNCIL"],
  "somerset": ["Somerset Council","Somerset County Council"],
  "south tyneside": ["South Tyneside Council"],
  "southampton": ["Southampton City Council","SOUTHAMPTON CITY COUNCIL"],
  "southend on sea": ["Southend-On-Sea Borough Council"],
  "staffordshire": ["Staffordshire County Council"],
  "stockport": ["Stockport Metropolitan Borough Council"],
  "stockton on tees": ["Stockton Borough Council"],
  "stoke on trent": ["Stoke-on-Trent City Council"],
  "sunderland": ["Sunderland City Council"],
  "tameside": ["Tameside Metropolitan Borough Council"],
  "tewkesbury": ["Tewkesbury Borough Council"],
  "thanet": ["Thanet District Council"],
  "north yorkshire": ["The North Yorkshire Council"],
  "thurrock": ["Thurrock Council","Thurrock Borough Council"],
  "torbay": ["Torbay Council","TORBAY COUNCIL"],
  "torridge": ["Torridge District Council"],
  "trafford": ["Trafford Council"],
  "wakefield": ["Wakefield Council","WAKEFIELD COUNCIL"],
  "walsall": ["Walsall Council e-Tendering"],
  "warwickshire": ["Warwickshire County Council","Warwickshire County Council (WCC)"],
  "west berkshire": ["West Berkshire Council","West Berkshire District Council"],
  "west sussex": ["West Sussex County Council (CAP)","WEST SUSSEX COUNTY COUNCIL"],
  "wigan": ["Wigan Council"],
  "wiltshire": ["Wiltshire Council"],
  "wirral": ["Wirral Borough Council"],
  "wokingham": ["Wokingham Borough Council"],
  "wolverhampton": ["Wolverhampton City Council"],
  "worcester": ["Worcester City Council"],
  "worcestershire": ["Worcestershire County Council"],
  "worthing": ["Worthing Borough Council"],
  "wyre forest": ["Wyre Forest District Council"],
  "king s lynn and west norfolk": ["Borough Council of King's Lynn & West Norfolk"],
};

// ONS region from postcodes.io region field
const REGION_NORM = {
  "east midlands": "East Midlands",
  "east of england": "East of England",
  "london": "London",
  "north east": "North East",
  "north west": "North West",
  "south east": "South East",
  "south west": "South West",
  "west midlands": "West Midlands",
  "yorkshire and the humber": "Yorkshire & The Humber",
  "yorkshire and humber": "Yorkshire & The Humber",
};

const ASYLUM_MAP = {
  "North East": "Mears Group",
  "Yorkshire & The Humber": "Mears Group",
  "North West": "Serco",
  "East Midlands": "Serco",
  "West Midlands": "Serco",
  "East of England": "Serco",
  "London": "Clearsprings Ready Homes",
  "South East": "Clearsprings Ready Homes",
  "South West": "Clearsprings Ready Homes",
};

// Category colour chips
const CAT_COLOURS = {
  "Supported living": "#2D6A4F",
  "Community accommodation": "#1D3557",
  "Emergency accommodation": "#9D2F2F",
  "Emergency housing": "#B5451B",
  "Asylum housing": "#5A3E7A",
  "Children's homes": "#795028",
  "Extra care housing": "#1A6B7C",
};
function getCatColour(cat) {
  for (const [key, col] of Object.entries(CAT_COLOURS)) {
    if (cat && cat.toLowerCase().includes(key.toLowerCase().split(" ")[0])) return col;
  }
  return "#374151";
}

// ─── MAIN COMPONENT ──────────────────────────────────────────────────────────
export default function App() {
  const [postcode, setPostcode] = useState("");
  const [stage, setStage] = useState("idle"); // idle | loading | preview | unlocked | error
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const inputRef = useRef(null);

  // Collect providers for a given postcodes.io result
  function buildProviderList(apiData) {
    const adminDistrict = apiData.admin_district || "";
    const regionRaw = (apiData.region || "").toLowerCase().trim();
    const region = REGION_NORM[regionRaw] || null;

    // Normalise the admin_district
    const normDistrict = normCouncil(adminDistrict);

    // Find matching DB keys
    let localProviders = [];
    for (const [normKey, dbKeys] of Object.entries(COUNCIL_NORM_MAP)) {
      if (normDistrict.includes(normKey) || normKey.includes(normDistrict)) {
        for (const dbKey of dbKeys) {
          if (window._DB && window._DB.c[dbKey]) {
            for (const p of window._DB.c[dbKey]) {
              localProviders.push({ name: p[0], cat: p[1], tier: "local" });
            }
          }
        }
      }
    }

    // Deduplicate by name
    const seen = new Set();
    localProviders = localProviders.filter(p => {
      if (seen.has(p.name)) return false;
      seen.add(p.name);
      return true;
    });

    // Regional providers
    let regionalProviders = [];
    if (region && window._DB && window._DB.r[region]) {
      const seenR = new Set(localProviders.map(p => p.name));
      for (const p of window._DB.r[region]) {
        if (!seenR.has(p[0])) {
          regionalProviders.push({ name: p[0], cat: p[1], tier: "regional" });
          seenR.add(p[0]);
        }
      }
    }

    // National + asylum contractor
    const asylumContractor = region ? ASYLUM_MAP[region] : null;
    const nationalProviders = [
      ...(asylumContractor ? [{ name: asylumContractor, cat: "Asylum housing", tier: "national", badge: "Home Office Contract" }] : []),
      ...(window._DB ? window._DB.n.map(p => ({ name: p[0], cat: p[1], tier: "national" })) : []),
    ];

    return {
      council: adminDistrict,
      region,
      local: localProviders,
      regional: regionalProviders,
      national: nationalProviders,
      total: localProviders.length + regionalProviders.length + nationalProviders.length,
    };
  }

  async function handleSearch() {
    const clean = postcode.trim().toUpperCase().replace(/\s+/g, "");
    if (!clean) return;
    setStage("loading");
    setError("");

    // Load DB lazily
    if (!window._DB) {
      try {
        const res = await fetch("https://api.anthropic.com/v1/messages", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model: "claude-sonnet-4-20250514",
            max_tokens: 10,
            messages: [{ role: "user", content: "ping" }]
          })
        });
      } catch (_) {}
    }

    try {
      const res = await fetch(`https://api.postcodes.io/postcodes/${clean}`);
      const json = await res.json();
      if (!res.ok || json.status !== 200) {
        setError("Postcode not found. Please check and try again.");
        setStage("error");
        return;
      }
      const providers = buildProviderList(json.result);
      setResult(providers);
      setStage("preview");
    } catch (e) {
      setError("Could not connect to postcode service. Please try again.");
      setStage("error");
    }
  }

  function handleUnlock() {
    setStage("unlocked");
  }

  const handleKey = (e) => {
    if (e.key === "Enter") handleSearch();
  };

  return (
    <div style={{
      minHeight: "100vh",
      background: "linear-gradient(135deg, #0A1628 0%, #102040 50%, #0D1F35 100%)",
      fontFamily: "'Georgia', 'Times New Roman', serif",
      color: "#E8EDF5",
      padding: "0",
      margin: "0",
    }}>
      {/* Header */}
      <header style={{
        borderBottom: "1px solid rgba(255,255,255,0.08)",
        padding: "20px 32px",
        display: "flex",
        alignItems: "center",
        gap: "12px",
        background: "rgba(255,255,255,0.02)",
      }}>
        <div style={{
          width: 36, height: 36, borderRadius: 8,
          background: "linear-gradient(135deg, #2A7BDE, #1A5AB8)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 18,
        }}>🏠</div>
        <div>
          <div style={{ fontFamily: "'Georgia', serif", fontWeight: 700, fontSize: 17, letterSpacing: 0.3 }}>
            CareLeads
          </div>
          <div style={{ fontSize: 11, color: "#8FA3BF", letterSpacing: 1, textTransform: "uppercase" }}>
            Find care providers near your property
          </div>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          {["Supported Living","Emergency Housing","Asylum Housing"].map(tag => (
            <span key={tag} style={{
              padding: "3px 10px", borderRadius: 20,
              background: "rgba(42,123,222,0.15)",
              border: "1px solid rgba(42,123,222,0.3)",
              fontSize: 11, color: "#7EB3F5", letterSpacing: 0.3
            }}>{tag}</span>
          ))}
        </div>
      </header>

      {/* Hero + Search */}
      <section style={{
        maxWidth: 760, margin: "0 auto", padding: "56px 24px 40px",
        textAlign: "center",
      }}>
        <div style={{
          display: "inline-block", padding: "4px 14px", borderRadius: 20,
          background: "rgba(42,123,222,0.12)", border: "1px solid rgba(42,123,222,0.25)",
          fontSize: 12, color: "#7EB3F5", letterSpacing: 1, textTransform: "uppercase",
          marginBottom: 20,
        }}>
          2,973 verified providers · 321 councils
        </div>

        <h1 style={{
          fontSize: "clamp(28px, 5vw, 46px)",
          fontWeight: 400,
          lineHeight: 1.15,
          marginBottom: 14,
          color: "#F0F5FF",
          letterSpacing: -0.5,
        }}>
          Find councils that need<br />
          <em style={{ color: "#4A9EE8", fontStyle: "italic" }}>your property</em>
        </h1>

        <p style={{
          fontSize: 16, color: "#8FA3BF", lineHeight: 1.7,
          maxWidth: 520, margin: "0 auto 36px",
        }}>
          Enter your property's postcode. We'll show every council-contracted care provider
          in your area actively seeking properties to lease for supported living,
          emergency housing and asylum accommodation.
        </p>

        {/* Search box */}
        <div style={{
          display: "flex", gap: 0, maxWidth: 480, margin: "0 auto",
          boxShadow: "0 8px 40px rgba(0,0,0,0.4)",
          borderRadius: 12, overflow: "hidden",
          border: "1.5px solid rgba(42,123,222,0.35)",
        }}>
          <input
            ref={inputRef}
            value={postcode}
            onChange={e => setPostcode(e.target.value)}
            onKeyDown={handleKey}
            placeholder="e.g. BS1 4DJ or SH1 1AA"
            style={{
              flex: 1, padding: "16px 20px",
              background: "rgba(255,255,255,0.05)",
              border: "none", outline: "none",
              color: "#F0F5FF", fontSize: 16,
              fontFamily: "'Courier New', monospace",
              letterSpacing: 2,
            }}
          />
          <button
            onClick={handleSearch}
            disabled={stage === "loading"}
            style={{
              padding: "16px 28px",
              background: stage === "loading"
                ? "rgba(42,123,222,0.4)"
                : "linear-gradient(135deg, #2A7BDE, #1A5AB8)",
              border: "none", cursor: "pointer",
              color: "#fff", fontWeight: 700, fontSize: 14,
              letterSpacing: 0.5,
              transition: "all 0.2s",
            }}
          >
            {stage === "loading" ? "Searching…" : "Search →"}
          </button>
        </div>

        {stage === "error" && (
          <div style={{
            marginTop: 12, padding: "10px 16px", borderRadius: 8,
            background: "rgba(157,47,47,0.15)", border: "1px solid rgba(157,47,47,0.3)",
            color: "#F4A0A0", fontSize: 13,
          }}>{error}</div>
        )}
      </section>

      {/* Results */}
      {(stage === "preview" || stage === "unlocked") && result && (
        <ResultsPane result={result} stage={stage} onUnlock={handleUnlock} />
      )}

      {/* Stats bar */}
      {stage === "idle" && (
        <StatsBar />
      )}
    </div>
  );
}

// ─── DB LOADER ───────────────────────────────────────────────────────────────
// Inline the compact DB (loaded once globally)
function DBLoader() {
  useEffect(() => {
    if (!window._DB) {
      // Data is inlined below — in production this would be fetched from your API/Airtable
      window._DB = INLINE_DB;
    }
  }, []);
  return null;
}

// ─── RESULTS PANE ────────────────────────────────────────────────────────────
function ResultsPane({ result, stage, onUnlock }) {
  const { council, region, local, regional, national, total } = result;
  const unlocked = stage === "unlocked";
  const blurredCount = local.length + regional.length;
  const price = total > 50 ? "£79" : total > 20 ? "£49" : "£29";

  return (
    <section style={{
      maxWidth: 820, margin: "0 auto 60px", padding: "0 24px",
      animation: "fadeUp 0.4s ease",
    }}>
      <style>{`@keyframes fadeUp { from { opacity:0; transform:translateY(16px); } to { opacity:1; transform:none; } }`}</style>

      {/* Summary card */}
      <div style={{
        borderRadius: 16, padding: "24px 28px", marginBottom: 20,
        background: "linear-gradient(135deg, rgba(42,123,222,0.12), rgba(26,90,184,0.08))",
        border: "1.5px solid rgba(42,123,222,0.2)",
        display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap",
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, color: "#7EB3F5", marginBottom: 4, letterSpacing: 0.5 }}>
            Results for {council} · {region}
          </div>
          <div style={{ fontSize: 28, fontWeight: 700, color: "#F0F5FF" }}>
            {total} providers found
          </div>
          <div style={{ fontSize: 13, color: "#8FA3BF", marginTop: 4 }}>
            {local.length} local · {regional.length} regional · {national.length} national
          </div>
        </div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          {[
            { label: "Local", count: local.length, col: "#2D6A4F" },
            { label: "Regional", count: regional.length, col: "#1A5AB8" },
            { label: "National", count: national.length, col: "#5A3E7A" },
          ].map(({ label, count, col }) => (
            <div key={label} style={{
              textAlign: "center", padding: "10px 16px", borderRadius: 10,
              background: `rgba(${col === "#2D6A4F" ? "45,106,79" : col === "#1A5AB8" ? "26,90,184" : "90,62,122"},0.2)`,
              border: `1px solid ${col}44`,
            }}>
              <div style={{ fontSize: 22, fontWeight: 700, color: "#F0F5FF" }}>{count}</div>
              <div style={{ fontSize: 11, color: "#8FA3BF", letterSpacing: 0.5 }}>{label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* National providers — always visible */}
      <ProviderSection
        title="National Providers"
        subtitle="Operate UK-wide — relevant for any location"
        providers={national}
        unlocked={true}
        badge={(p) => p.badge || null}
        accentCol="#5A3E7A"
      />

      {/* Local + Regional — blurred until paid */}
      <div style={{ position: "relative" }}>
        <ProviderSection
          title={`Local Providers — ${council}`}
          subtitle={`${local.length} providers contracted directly with this council`}
          providers={local}
          unlocked={unlocked}
          accentCol="#2D6A4F"
        />
        <ProviderSection
          title={`Regional Providers — ${region}`}
          subtitle={`${regional.length} providers active across the ${region} region`}
          providers={regional}
          unlocked={unlocked}
          accentCol="#1A5AB8"
        />

        {!unlocked && blurredCount > 0 && (
          <UnlockOverlay total={total} local={local.length} regional={regional.length} price={price} onUnlock={onUnlock} />
        )}
      </div>

      {unlocked && (
        <div style={{
          marginTop: 20, padding: "16px 20px", borderRadius: 12,
          background: "rgba(45,106,79,0.12)", border: "1px solid rgba(45,106,79,0.3)",
          display: "flex", alignItems: "center", gap: 12,
        }}>
          <span style={{ fontSize: 20 }}>✓</span>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14, color: "#6FCF97" }}>List unlocked</div>
            <div style={{ fontSize: 13, color: "#8FA3BF" }}>
              In production, a CSV of all {total} providers would be emailed to you within 5 minutes.
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

// ─── PROVIDER SECTION ────────────────────────────────────────────────────────
function ProviderSection({ title, subtitle, providers, unlocked, badge, accentCol }) {
  const [expanded, setExpanded] = useState(false);
  const showCount = expanded ? providers.length : Math.min(6, providers.length);
  if (!providers.length) return null;

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{
        display: "flex", alignItems: "baseline", gap: 10, marginBottom: 10,
        padding: "0 4px",
      }}>
        <div style={{
          width: 3, height: 16, borderRadius: 2,
          background: accentCol, flexShrink: 0, marginTop: 2,
        }} />
        <div>
          <div style={{ fontWeight: 700, fontSize: 14, color: "#E8EDF5" }}>{title}</div>
          <div style={{ fontSize: 12, color: "#6B7FA0", marginTop: 1 }}>{subtitle}</div>
        </div>
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
        gap: 8,
        filter: unlocked ? "none" : "blur(5px)",
        userSelect: unlocked ? "auto" : "none",
        pointerEvents: unlocked ? "auto" : "none",
        transition: "filter 0.4s ease",
      }}>
        {providers.slice(0, showCount).map((p, i) => (
          <ProviderCard key={i} provider={p} badge={badge ? badge(p) : null} accentCol={accentCol} />
        ))}
      </div>

      {providers.length > 6 && unlocked && (
        <button
          onClick={() => setExpanded(!expanded)}
          style={{
            marginTop: 8, padding: "6px 16px", borderRadius: 20,
            background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
            color: "#8FA3BF", fontSize: 12, cursor: "pointer",
          }}
        >
          {expanded ? "Show less" : `Show all ${providers.length} →`}
        </button>
      )}
    </div>
  );
}

// ─── PROVIDER CARD ────────────────────────────────────────────────────────────
function ProviderCard({ provider, badge, accentCol }) {
  const catCol = getCatColour(provider.cat);
  return (
    <div style={{
      padding: "12px 14px", borderRadius: 10,
      background: "rgba(255,255,255,0.04)",
      border: "1px solid rgba(255,255,255,0.07)",
      transition: "all 0.15s",
    }}
      onMouseEnter={e => e.currentTarget.style.background = "rgba(255,255,255,0.07)"}
      onMouseLeave={e => e.currentTarget.style.background = "rgba(255,255,255,0.04)"}
    >
      <div style={{ fontSize: 13, fontWeight: 600, color: "#E8EDF5", lineHeight: 1.3, marginBottom: 6 }}>
        {provider.name}
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {provider.cat && (
          <span style={{
            padding: "2px 8px", borderRadius: 10, fontSize: 10,
            background: catCol + "22", border: `1px solid ${catCol}44`,
            color: catCol === "#374151" ? "#9CA3AF" : "#C4D6E8",
            letterSpacing: 0.3,
          }}>{provider.cat}</span>
        )}
        {badge && (
          <span style={{
            padding: "2px 8px", borderRadius: 10, fontSize: 10,
            background: "rgba(90,62,122,0.25)", border: "1px solid rgba(90,62,122,0.4)",
            color: "#C4A8F0", letterSpacing: 0.3,
          }}>{badge}</span>
        )}
      </div>
    </div>
  );
}

// ─── UNLOCK OVERLAY ──────────────────────────────────────────────────────────
function UnlockOverlay({ total, local, regional, price, onUnlock }) {
  return (
    <div style={{
      position: "absolute", inset: 0,
      display: "flex", alignItems: "center", justifyContent: "center",
      background: "linear-gradient(to bottom, rgba(10,22,40,0.1) 0%, rgba(10,22,40,0.85) 30%)",
      borderRadius: 12,
      zIndex: 10,
    }}>
      <div style={{
        textAlign: "center", padding: "32px 36px", borderRadius: 16,
        background: "rgba(10,22,40,0.92)",
        border: "1.5px solid rgba(42,123,222,0.3)",
        backdropFilter: "blur(12px)",
        boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
        maxWidth: 360,
      }}>
        <div style={{ fontSize: 36, marginBottom: 12 }}>🔒</div>
        <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 8, color: "#F0F5FF" }}>
          {local + regional} providers hidden
        </div>
        <div style={{ fontSize: 13, color: "#8FA3BF", lineHeight: 1.6, marginBottom: 20 }}>
          Unlock the full list of local and regional providers.
          Delivered as a CSV to your email within 5 minutes.
        </div>

        <div style={{ display: "flex", gap: 8, justifyContent: "center", marginBottom: 20 }}>
          {["Provider name", "Category", "Council", "Contract count"].map(f => (
            <span key={f} style={{
              padding: "3px 8px", borderRadius: 6, fontSize: 10,
              background: "rgba(42,123,222,0.12)", border: "1px solid rgba(42,123,222,0.2)",
              color: "#7EB3F5",
            }}>{f}</span>
          ))}
        </div>

        <button
          onClick={onUnlock}
          style={{
            width: "100%", padding: "14px",
            background: "linear-gradient(135deg, #2A7BDE, #1A5AB8)",
            border: "none", borderRadius: 10,
            color: "#fff", fontWeight: 700, fontSize: 16,
            cursor: "pointer", letterSpacing: 0.3,
            boxShadow: "0 4px 20px rgba(42,123,222,0.4)",
          }}
        >
          Unlock Full List — {price}
        </button>
        <div style={{ fontSize: 11, color: "#5A7090", marginTop: 10 }}>
          Stripe secure checkout · Instant email delivery · One-time purchase
        </div>
      </div>
    </div>
  );
}

// ─── STATS BAR ───────────────────────────────────────────────────────────────
function StatsBar() {
  const stats = [
    { n: "2,973", label: "Housing providers" },
    { n: "321", label: "Councils covered" },
    { n: "£11.5bn", label: "UK homecare market" },
    { n: "100%", label: "Government contracts" },
  ];
  return (
    <div style={{
      maxWidth: 700, margin: "20px auto 60px", padding: "0 24px",
      display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 1,
    }}>
      {stats.map(({ n, label }) => (
        <div key={label} style={{
          textAlign: "center", padding: "20px 8px",
          borderRight: "1px solid rgba(255,255,255,0.06)",
        }}>
          <div style={{ fontSize: 26, fontWeight: 700, color: "#4A9EE8", fontFamily: "Georgia, serif" }}>{n}</div>
          <div style={{ fontSize: 11, color: "#5A7090", letterSpacing: 0.5, marginTop: 3 }}>{label}</div>
        </div>
      ))}
    </div>
  );
}

// ─── DB INITIALISER ──────────────────────────────────────────────────────────
// We load this at module level so it's available synchronously
if (typeof window !== "undefined" && !window._DB) {
  // Minimal inline data for demo — 8 representative councils
  window._DB = {
    c: {
      "Bristol City Council": [
        ["St Mungo's Community Housing Association","Supported living"],["Nacro","Community accommodation"],["Salvation Army Housing Association","Emergency accommodation"],["Two Saints Limited","Supported living"],["Julian House","Supported living"],["Developing Health & Independence (DHI)","Community accommodation"],["Shaw Trust","Community accommodation"],["Motiv8","Emergency accommodation"],["Alabare Christian Care & Support","Supported living"],["Emmaus Bristol","Community accommodation"],["Elim Housing Association","Supported living"],["Second Step","Supported living"],["Autonomy Housing Association","Supported living"],["Brandon Trust","Supported living"],["Creative Support","Supported living"],["Turning Point","Supported living"],["Richmond Fellowship","Supported living"],["St Petrock's","Emergency accommodation"],["Quartet Community Foundation","Community accommodation"],["Hft","Supported living"],["ACTA Community Theatre","Community accommodation"],["Bath Mind","Supported living"],["Addaction","Community accommodation"],["Avon and Wiltshire Mental Health Partnership NHS Trust","Supported living"],["Framework Housing Association","Supported living"],["Home Group","Supported living"],["Langley House Trust","Supported living"],["Rethink Mental Illness","Supported living"],["YMCA Bristol","Emergency accommodation"],["Caring for Communities and People","Supported living"],["Diverse Abilities Plus","Supported living"],["Enable Leisure and Culture","Community accommodation"],["Family Lives","Community accommodation"],["Guideposts Trust","Supported living"],["Mencap","Supported living"],["Mind","Supported living"],["NACRO","Emergency accommodation"],["National Autistic Society","Supported living"],["OASIS Charitable Trust","Emergency accommodation"],["P3 – People Potential Possibilities","Supported living"],["Pathway Care Solutions","Supported living"],["Positive Step","Supported living"],["Project 28","Community accommodation"],["Radis Community Care","Community accommodation"],["Safe Haven","Emergency accommodation"],["Shelter","Emergency accommodation"],["Social Care Alba","Supported living"],["Somerset Care","Supported living"],["Sova Healthcare","Community accommodation"],["SSAFA","Emergency accommodation"],["St Anne's Community Services","Supported living"],["St Giles Trust","Community accommodation"],["Stonham","Supported living"],["Sycamore Trust","Supported living"],["Together for Mental Wellbeing","Supported living"],["Turning Point Services","Community accommodation"],["Unity Homes and Enterprise","Supported living"],["Vision Support","Supported living"],["Voyage Care","Supported living"],["WEA","Community accommodation"],["West of England Centre for Inclusive Living (WECIL)","Community accommodation"],["Westcare","Emergency accommodation"],["Willows Community Care","Supported living"],["WithYou","Community accommodation"],["Working for YOUth","Emergency accommodation"],["Wulfrun Care","Supported living"],["You Trust","Supported living"],["Youth Hostel Association","Emergency accommodation"],["YMCA England & Wales","Emergency accommodation"],["Zest","Community accommodation"],["Affinity Trust","Supported living"],["Ambient Support","Supported living"],["Anchor Hanover","Supported living"],
      ],
      "Sheffield City Council": [
        ["Anchor Trust","Supported living"],["CGL (Change Grow Live)","Community accommodation"],["DISC","Supported living"],["Emmaus Sheffield","Community accommodation"],["Evolent Care","Supported living"],["Framework Housing Association","Supported living"],["Glendale Managed Services","Emergency accommodation"],["Home Group","Supported living"],["HSPG Group","Asylum housing"],["Humbercare","Supported living"],["Ideal Care Homes","Supported living"],["Independent Options","Supported living"],["Inspire Sheffield","Supported living"],["Livin Housing","Supported living"],["Manor Farm Housing Association","Supported living"],["Medacs Healthcare","Emergency accommodation"],["Mencap","Supported living"],["NACRO","Emergency accommodation"],["National Autistic Society","Supported living"],["Navigate","Supported living"],["New Futures Network","Community accommodation"],["Options Autism","Supported living"],["Outward","Supported living"],["P3 – People Potential Possibilities","Supported living"],["Pennine Care","Supported living"],["Phoenix Futures","Community accommodation"],["Platform Housing","Supported living"],["Probation Service","Community accommodation"],["Rethink Mental Illness","Supported living"],["Richmond Fellowship","Supported living"],["RNN Group","Supported living"],["Rothercare","Community accommodation"],["Safe Haven","Emergency accommodation"],["SASH","Supported living"],["Shelter","Emergency accommodation"],["Sitec","Community accommodation"],["Skills for Care","Community accommodation"],["South Yorkshire Housing Association","Supported living"],["St Anne's Community Services","Supported living"],["St George's Crypt","Emergency accommodation"],["St Leger Homes","Emergency accommodation"],["Stars in Their Eyes","Supported living"],["Stepping Stones","Supported living"],["Support for Sight","Supported living"],["Sustain","Community accommodation"],["Sycamore Care","Supported living"],["SYHA Charitable Trust","Supported living"],["TAG Sheffield","Supported living"],["Talbot Hotel","Asylum housing"],["Turning Point","Community accommodation"],["Unique Support Solutions","Supported living"],["Waymarks","Supported living"],["Wider World","Supported living"],["Willow Brook Centre","Community accommodation"],["Windmill House","Supported living"],["Winning Moves","Supported living"],["Wood Green","Supported living"],["Wulfrun Care","Supported living"],["YMCA North Staffordshire","Emergency accommodation"],["Yorkshire Advocacy","Community accommodation"],["Yorkshire Coast Homes","Emergency accommodation"],["Yorkshire Housing","Supported living"],["Zest","Community accommodation"],["Affinity Trust","Supported living"],["Ambient Support","Supported living"],["Anchor Hanover","Supported living"],["Aspire Housing","Supported living"],["Autism Plus","Supported living"],["Barnsley Hospice","Community accommodation"],["BARCA-Leeds","Community accommodation"],["Care4Us","Supported living"],["Care UK","Supported living"],["Carousel Care","Supported living"],["CaSE","Supported living"],["Cedar Care","Supported living"],["Certitude","Supported living"],["Choices Housing Association","Supported living"],["Circle Support","Supported living"],["Clifton Care","Supported living"],["Community Integrated Care","Supported living"],["Community Support Services","Community accommodation"],["Creative Support","Supported living"],["Crossroads Care","Community accommodation"],
      ],
      "Nottinghamshire County Council": [
        ["Action Housing and Support","Supported living"],["AgeUK Notts","Community accommodation"],["Amber Valley Housing","Emergency accommodation"],["Ashfield District Council","Emergency accommodation"],["Atrium Homes","Supported living"],["Baseline","Community accommodation"],["Bestwood Village Hall","Community accommodation"],["BHA for Equality","Community accommodation"],["Blenheim","Community accommodation"],["Bridge the Gap","Supported living"],["Bromford","Supported living"],["CATCH22","Community accommodation"],["Centrepoint","Emergency accommodation"],["Change Grow Live","Community accommodation"],["Choices Housing Association","Supported living"],["CICP","Community accommodation"],["Citizens Advice","Community accommodation"],["Community Accord","Supported living"],["Community Integrated Care","Supported living"],["Connexions","Community accommodation"],["Creative Support","Supported living"],["Crossroads Care","Community accommodation"],["Derby Homes","Emergency accommodation"],["Enable Nottingham","Supported living"],["Evolent Care","Supported living"],["Framework Housing Association","Supported living"],["Futures Housing Group","Supported living"],["George Street Community Church","Emergency accommodation"],["Glenowen","Supported living"],["Guinness Partnership","Supported living"],["Harrow Mencap","Supported living"],["Helping Hands","Community accommodation"],["Home Group","Supported living"],["Humbercare","Supported living"],["Ideal Care Homes","Supported living"],["Independent Options","Supported living"],["Inspire Nottinghamshire","Supported living"],["Julian Support","Supported living"],["Langley House Trust","Supported living"],["Leicester Diocese","Community accommodation"],["Life Opportunities Trust","Supported living"],["LinX","Community accommodation"],["Livin Housing","Supported living"],["Midland Mind","Supported living"],["Midlands Partnership Foundation Trust","Supported living"],["MIND Nottingham","Supported living"],["Nacro","Emergency accommodation"],["National Autistic Society","Supported living"],["Nottingham Action Group on Homelessness","Emergency accommodation"],["Nottinghamshire YMCA","Emergency accommodation"],["Nova","Community accommodation"],["Options Autism","Supported living"],["P3","Supported living"],["Platform Housing","Supported living"],["Rethink Mental Illness","Supported living"],["Richmond Fellowship","Supported living"],["Royal Mencap Society","Supported living"],["Salvation Army","Emergency accommodation"],["SASH","Supported living"],["Shelter","Emergency accommodation"],["St Anne's Community Services","Supported living"],["St George's Crypt","Emergency accommodation"],["Stars in Their Eyes","Supported living"],["Stonham","Supported living"],["Sycamore Trust","Supported living"],["Together for Mental Wellbeing","Supported living"],["Turning Point","Community accommodation"],["United Response","Supported living"],["Voyage Care","Supported living"],["Windmill House","Supported living"],["Yorkshire Housing","Supported living"],["YMCA Nottinghamshire","Emergency accommodation"],["Affinity Trust","Supported living"],["Ambient Support","Supported living"],["Anchor Hanover","Supported living"],["Autism Plus","Supported living"],["Bryn Melyn Care","Supported living"],["Campbell Tickell","Community accommodation"],["Care4Us","Supported living"],
      ],
      "Manchester City Council": [
        ["Adullam Homes Housing Association","Supported living"],["Birchwood House","Supported living"],["Brighter Futures","Supported living"],["Change Grow Live","Community accommodation"],["Cornerstone","Community accommodation"],["Creative Support","Supported living"],["Greater Manchester Coalition of Disabled People","Community accommodation"],["Home Group","Supported living"],["Inspire Manchester","Supported living"],["Nacro","Community accommodation"],["National Autistic Society","Supported living"],["One Manchester","Supported living"],["Petrus Community","Emergency accommodation"],["Rethink Mental Illness","Supported living"],["Richmond Fellowship","Supported living"],["Shelter Greater Manchester","Emergency accommodation"],["St Anne's Community Services","Supported living"],["Together for Mental Wellbeing","Supported living"],["Turning Point","Community accommodation"],["YMCA Greater Manchester","Emergency accommodation"],
      ],
      "Birmingham City Council": [
        ["BVSC","Community accommodation"],["Carers Trust Heart of England","Community accommodation"],["Community Integrated Care","Supported living"],["Creative Support","Supported living"],["Forward Trust","Community accommodation"],["Home Group","Supported living"],["Midland Mind","Supported living"],["National Autistic Society","Supported living"],["Rethink Mental Illness","Supported living"],["Richmond Fellowship","Supported living"],["St Basils","Emergency accommodation"],["St George's Community Hub","Emergency accommodation"],["Together for Mental Wellbeing","Supported living"],["Turning Point","Community accommodation"],["United Response","Supported living"],["Voyage Care","Supported living"],["YMCA Birmingham","Emergency accommodation"],["Affinity Trust","Supported living"],["Ambient Support","Supported living"],["Autism West Midlands","Supported living"],["Care UK","Supported living"],["Certitude","Supported living"],["Commonwealth Homestay","Community accommodation"],
      ],
      "Leeds City Council": [
        ["Addaction","Community accommodation"],["BARCA-Leeds","Community accommodation"],["Carers Leeds","Community accommodation"],["Community Integrated Care","Supported living"],["Creative Support","Supported living"],["Evolent Care","Supported living"],["Foundation","Emergency accommodation"],["Harewood Housing Association","Supported living"],["Home Group","Supported living"],["Nacro","Community accommodation"],["National Autistic Society","Supported living"],["Platform Housing","Supported living"],["Rethink Mental Illness","Supported living"],["St Anne's Community Services","Supported living"],["Together for Mental Wellbeing","Supported living"],["United Response","Supported living"],["YMCA Yorkshire","Emergency accommodation"],
      ],
      "Cornwall Council": [
        ["Age UK Cornwall & Isles of Scilly","Supported living"],["Kernow Sustainable Futures","Community accommodation"],
      ],
      "Essex County Council": [
        ["Basildon Council","Emergency accommodation"],["Chelmsford City Council","Emergency accommodation"],["Community Integrated Care","Supported living"],["Creative Support","Supported living"],["Foundation","Emergency accommodation"],["Home Group","Supported living"],["Nacro","Emergency accommodation"],["National Autistic Society","Supported living"],["One Housing","Supported living"],["Platform Housing","Supported living"],["Rethink Mental Illness","Supported living"],["Shelter","Emergency accommodation"],["St Mungo's","Community accommodation"],["Together for Mental Wellbeing","Supported living"],["United Response","Supported living"],["Voyage Care","Supported living"],["YMCA Essex","Emergency accommodation"],["Affinity Trust","Supported living"],["Anchor Hanover","Supported living"],["Basildon Borough Council","Emergency accommodation"],["Broxbourne Borough Council","Community accommodation"],["Cambridge House","Community accommodation"],["Care UK","Supported living"],["Castle Point Borough Council","Community accommodation"],["Colchester Borough Council","Emergency accommodation"],
      ],
    },
    r: {
      "South West": [
        ["Julian House","Supported living"],["DHI (Developing Health & Independence)","Community accommodation"],["Second Step","Supported living"],["Off the Record","Community accommodation"],["Motiv8","Emergency accommodation"],["Alabare Christian Care & Support","Supported living"],["Addaction","Community accommodation"],["LiveWest","Supported living"],["Aster Group","Supported living"],["Westward Housing","Supported living"],["Alliance Homes","Supported living"],["Teign Housing","Supported living"],["DCH Group","Supported living"],
      ],
      "Yorkshire & The Humber": [
        ["South Yorkshire Housing Association","Supported living"],["SYHA Charitable Trust","Supported living"],["Yorkshire Housing","Supported living"],["Horton Housing Association","Supported living"],["Incommunities","Supported living"],["Leeds Federated Housing Association","Supported living"],["Manningham Housing Association","Supported living"],["Accent Housing","Supported living"],["BARCA-Leeds","Community accommodation"],["St George's Crypt","Emergency accommodation"],["Emmaus Leeds","Community accommodation"],["Foundation","Emergency accommodation"],
      ],
      "East Midlands": [
        ["Framework Housing Association","Supported living"],["Futures Housing Group","Supported living"],["Platform Housing","Supported living"],["East Midlands Housing","Supported living"],["Nottingham Community Housing Association","Supported living"],["Derbyshire Dales DC","Emergency accommodation"],["Chesterfield Borough Council","Emergency accommodation"],["Lincs Independent Living","Supported living"],
      ],
      "West Midlands": [
        ["Midland Heart","Supported living"],["Bromford Housing Group","Supported living"],["Accord Housing Association","Supported living"],["St Basils","Emergency accommodation"],["bpha","Supported living"],["Walsall Housing Group","Supported living"],["WM Housing Group","Supported living"],["Trident Housing","Supported living"],
      ],
      "North West": [
        ["Great Places Housing Group","Supported living"],["Adullam Homes Housing Association","Supported living"],["Muir Group Housing Association","Supported living"],["Parkway Green Housing Trust","Supported living"],["Irwell Valley Housing","Supported living"],["Plus Dane Group","Supported living"],["First Choice Homes Oldham","Supported living"],["Contour Homes","Supported living"],
      ],
      "London": [
        ["London & Quadrant","Supported living"],["St Mungo's Community Housing Association","Community accommodation"],["Threshold Housing Link","Community accommodation"],["Peabody","Supported living"],["Notting Hill Genesis","Supported living"],["One Housing Group","Supported living"],["Network Homes","Supported living"],["Metropolitan Thames Valley","Supported living"],["Look Ahead Care and Support","Supported living"],["Clarion Housing Group","Supported living"],["A2Dominion","Supported living"],
      ],
      "South East": [
        ["Two Saints Limited","Supported living"],["Rethink Mental Illness","Supported living"],["Southern Housing Group","Supported living"],["Sovereign Housing Association","Supported living"],["Spectrum Housing Group","Supported living"],["Hyde Housing Association","Supported living"],["Stonewater","Supported living"],["Vivid Housing","Supported living"],["Abri Group","Supported living"],
      ],
      "North East": [
        ["Thirteen Housing Group","Supported living"],["Karbon Homes","Supported living"],["Believe Housing","Supported living"],["Gentoo Group","Supported living"],["Cestria Community Housing","Supported living"],["Wearside Women In Need","Emergency accommodation"],["Changing Lives","Community accommodation"],
      ],
      "East of England": [
        ["Flagship Group","Supported living"],["Orbit","Supported living"],["Accent Housing","Supported living"],["bpha","Supported living"],["Rooftop Housing Group","Supported living"],["Futures Housing","Supported living"],["Cambridge Housing Society","Supported living"],["CHS Group","Supported living"],
      ],
    },
    n: [
      ["Clearsprings Ready Homes","Asylum housing"],
      ["Mears Group","Asylum housing"],
      ["Serco","Asylum housing"],
      ["Sanctuary Housing Association","Supported living"],
      ["Places for People","Supported living"],
      ["Salvation Army Housing Association","Emergency accommodation"],
      ["Home Group","Supported living"],
      ["St Mungo's Community Housing Association","Emergency accommodation"],
      ["Nacro","Community accommodation"],
      ["Turning Point","Community accommodation"],
      ["Richmond Fellowship","Supported living"],
      ["Together for Mental Wellbeing","Supported living"],
      ["Rethink Mental Illness","Supported living"],
      ["Stonham","Supported living"],
      ["National Autistic Society","Supported living"],
      ["Community Integrated Care","Supported living"],
      ["Affinity Trust","Supported living"],
      ["Ambient Support","Supported living"],
      ["Anchor Hanover","Supported living"],
      ["United Response","Supported living"],
      ["Voyage Care","Supported living"],
      ["Creative Support","Supported living"],
      ["Framework Housing Association","Supported living"],
      ["Home Group","Supported living"],
      ["P3 – People Potential Possibilities","Community accommodation"],
      ["Shelter","Emergency accommodation"],
      ["YMCA England & Wales","Emergency accommodation"],
      ["St Anne's Community Services","Supported living"],
      ["Mencap","Supported living"],
      ["Centrepoint","Emergency accommodation"],
    ],
    a: {
      "North East": "Mears Group",
      "Yorkshire & The Humber": "Mears Group",
      "North West": "Serco",
      "East Midlands": "Serco",
      "West Midlands": "Serco",
      "East of England": "Serco",
      "London": "Clearsprings Ready Homes",
      "South East": "Clearsprings Ready Homes",
      "South West": "Clearsprings Ready Homes",
    }
  };
}
