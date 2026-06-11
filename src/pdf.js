// Builds the downloadable provider report PDF from an unlocked result.
// Organised by Local / Regional / National contracts; within each tier, grouped
// by type (housing associations, asylum, homelessness, supported living by client
// group). pdfmake is loaded lazily so it never weighs down the initial page load.
import { contractForCouncil, TEMPLATES } from "./message.js";

const ACCENT = "#0F5C4E";
const SLATE = "#1A2B28";
const MUTED = "#5A6B66";

const CG_ORDER = [
  "Learning disabilities", "Autism", "Mental health", "Acquired brain injury",
  "Physical disabilities", "Sensory impairment", "Older people",
  "Young people & care leavers", "Substance misuse", "Domestic abuse",
  "Asylum & refugees", "Homelessness",
];

function isAsylum(p) {
  return (p.sector || []).some((s) => /asylum/i.test(s))
    || /home office/i.test(p.badge || "")
    || (p.client_groups || []).includes("Asylum & refugees");
}
function isHomeless(p) {
  return (p.sector || []).some((s) => /emergency/i.test(s))
    || (p.client_groups || []).includes("Homelessness");
}

// categorise a single tier's providers
function categorizeList(list) {
  const ha = [], asylum = [], homeless = [], supported = [];
  for (const p of list) {
    if (p.is_housing_association) ha.push(p);
    else if (isAsylum(p)) asylum.push(p);
    else if (isHomeless(p)) homeless.push(p);
    else supported.push(p);
  }
  const groups = {};
  for (const p of supported) {
    const cg = CG_ORDER.find((g) => (p.client_groups || []).includes(g)) || "General supported living";
    (groups[cg] ||= []).push(p);
  }
  const byC = (a, b) => (b.contracts || 0) - (a.contracts || 0);
  ha.sort(byC); asylum.sort(byC); homeless.sort(byC);
  const supportedGroups = Object.entries(groups)
    .sort((a, b) => b[1].length - a[1].length)
    .map(([name, l]) => [name, l.sort(byC)]);
  return { ha, asylum, homeless, supportedGroups, count: list.length };
}

// one compact provider entry
function entry(p, council) {
  const care = (p.sector || []).filter((s) => !/^homecare$/i.test(s)).join(", ") || (p.sector || []).join(", ");
  const what = (p.client_groups || []).join(", ");
  const contacts = [p.email, p.phone, p.website && p.website.replace(/^https?:\/\//, "")].filter(Boolean).join("  ·  ");
  const held = contractForCouncil(p, council);
  const lines = [{ text: p.name, bold: true, fontSize: 10, color: SLATE, margin: [0, 4, 0, 0] }];
  const meta = [];
  if (p.contracts) meta.push(`${p.contracts} council contract${p.contracts === 1 ? "" : "s"}`);
  if (p.employees) meta.push(`${p.employees.toLocaleString()} staff`);
  if (p.badge) meta.push(p.badge);
  if (meta.length) lines.push({ text: meta.join("  ·  "), fontSize: 8, color: ACCENT });
  if (held && (held.titles?.length || held.sectors?.length)) {
    lines.push({ text: [{ text: `Contract with ${council}: `, color: MUTED }, (held.titles && held.titles[0]) || held.sectors.join(", ")], fontSize: 8.5 });
  }
  if (what) lines.push({ text: [{ text: "Supports: ", color: MUTED }, what], fontSize: 8.5 });
  if (care) lines.push({ text: [{ text: "Contracted care: ", color: MUTED }, care], fontSize: 8.5 });
  if (contacts) lines.push({ text: contacts, fontSize: 8.5, color: SLATE });
  return { stack: lines, margin: [0, 0, 0, 6], unbreakable: true };
}

function section(title, subtitle, providers, council) {
  if (!providers.length) return [];
  const out = [{ text: title, style: "h2", margin: [0, 16, 0, 2] }];
  if (subtitle) out.push({ text: subtitle, fontSize: 9, italics: true, color: MUTED, margin: [0, 0, 0, 4] });
  out.push({ text: `${providers.length} provider${providers.length === 1 ? "" : "s"}`, fontSize: 8, color: ACCENT, margin: [0, 0, 0, 2] });
  out.push(...providers.map((p) => entry(p, council)));
  return out;
}

// a National/Regional/Local block, sub-grouped by category
function tierBlock(label, subtitle, list, council) {
  if (!list.length) return [];
  const cat = categorizeList(list);
  const out = [
    { text: label, style: "h1", margin: [0, 24, 0, 2], pageBreak: "before" },
    { text: subtitle, fontSize: 9.5, color: MUTED, margin: [0, 0, 0, 6], lineHeight: 1.3 },
  ];
  if (cat.ha.length) {
    out.push({ text: "Housing associations", style: "h2", margin: [0, 12, 0, 2] });
    out.push({ text: "Typically own or develop their own stock — but several take on extra property in high-demand areas.", fontSize: 8.5, italics: true, color: MUTED, margin: [0, 0, 0, 4] });
    out.push(...cat.ha.map((p) => entry(p, council)));
  }
  out.push(...section("Asylum & refugee accommodation", null, cat.asylum, council));
  out.push(...section("Homelessness & emergency", null, cat.homeless, council));
  for (const [name, l] of cat.supportedGroups) out.push(...section(`Supported living — ${name}`, null, l, council));
  return out;
}

function gbp(n) { return `£${Math.round(n).toLocaleString()}`; }

function lhaBlock(lha) {
  if (!lha) return [];
  const rows = [
    ["Room entitlement", "LHA / month", "+10%", "+20%"],
    ...[["Shared room", lha.shared], ["1 bedroom", lha.bed1], ["2 bedrooms", lha.bed2],
        ["3 bedrooms", lha.bed3], ["4 bedrooms", lha.bed4]]
      .filter(([, v]) => v != null)
      .map(([label, v]) => [label, gbp(v), gbp(v * 1.1), gbp(v * 1.2)]),
  ];
  return [
    { text: "Local Housing Allowance for this area", style: "h2", margin: [0, 18, 0, 2] },
    { text: `${lha.council} · ${lha.brma} BRMA · 2026/27 rates`, fontSize: 9, color: MUTED, margin: [0, 0, 0, 6] },
    {
      table: { headerRows: 1, widths: ["*", "auto", "auto", "auto"], body: rows },
      layout: { fillColor: (r) => (r === 0 ? "#E3EFEB" : null), hLineColor: "#E6E8E4", vLineColor: "#E6E8E4", hLineWidth: () => 0.5, vLineWidth: () => 0.5 },
      fontSize: 9,
    },
    {
      text: [
        { text: "How rent is set.  ", bold: true },
        "Social housing and supported-living providers typically pay rent in line with the LHA above, claimed as Housing Benefit on behalf of residents. Where demand is high and suitable property is scarce, providers can often negotiate ",
        { text: "LHA plus 10–20%", bold: true, color: ACCENT },
        " — the +10% and +20% columns show that headroom.",
      ],
      fontSize: 9, color: SLATE, margin: [0, 10, 0, 0], lineHeight: 1.3,
    },
  ];
}

function templatesBlock() {
  const out = [
    { text: "Email templates you can use", style: "h2", margin: [0, 20, 0, 2] },
    { text: "Fill in the [bracketed] details. For Template 1, use the contract shown under each provider below.", fontSize: 9, italics: true, color: MUTED, margin: [0, 0, 0, 6] },
  ];
  for (const t of TEMPLATES) {
    out.push({ text: t.title, bold: true, fontSize: 10, color: SLATE, margin: [0, 8, 0, 2] });
    out.push({
      table: { widths: ["*"], body: [[{ text: `Subject: ${t.subject}\n\n${t.body}`, fontSize: 8.5, color: SLATE, lineHeight: 1.3 }]] },
      layout: { fillColor: () => "#F2F4F1", hLineWidth: () => 0, vLineWidth: () => 0, paddingLeft: () => 12, paddingRight: () => 12, paddingTop: () => 10, paddingBottom: () => 10 },
      margin: [0, 0, 0, 4],
    });
  }
  return out;
}

export async function generateReport(result) {
  const [pdfMakeMod, vfsMod] = await Promise.all([
    import("pdfmake/build/pdfmake"),
    import("pdfmake/build/vfs_fonts"),
  ]);
  const pdfMake = pdfMakeMod.default || pdfMakeMod;
  const vfs = vfsMod.default?.pdfMake?.vfs || vfsMod.pdfMake?.vfs || vfsMod.default?.vfs || vfsMod.vfs;
  if (vfs) pdfMake.vfs = vfs;

  const council = result.council;
  const region = result.region || "the region";
  const nLocal = (result.local || []).length, nReg = (result.regional || []).length, nNat = (result.national || []).length;
  const total = nLocal + nReg + nNat;
  const dateStr = new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

  const content = [
    { text: "Find a Housing Provider", color: ACCENT, bold: true, fontSize: 11 },
    { text: `Provider report — ${council}`, style: "h1", margin: [0, 2, 0, 2] },
    { text: `${(result.postcode || "").toUpperCase()}  ·  ${result.region || "England"}  ·  ${total} providers  ·  ${dateStr}`, fontSize: 9, color: MUTED, margin: [0, 0, 0, 6] },
    { text: `This report lists care and housing providers covering ${council}, broken down by the level at which they hold contracts: Local (a contract with ${council}), Regional (active across ${region}) and National (UK-wide). Within each level they are grouped by type — housing associations, asylum & homelessness, and supported living by who they support.`, fontSize: 9.5, color: SLATE, margin: [0, 0, 0, 4], lineHeight: 1.35 },
    { text: `Local ${nLocal}  ·  Regional ${nReg}  ·  National ${nNat}`, fontSize: 9, bold: true, color: ACCENT, margin: [0, 2, 0, 0] },
    ...lhaBlock(result.lha),
    ...templatesBlock(),
    ...tierBlock(`Local contracts — a contract with ${council}`,
      `Providers that hold a contract directly with ${council}. The most relevant to approach about property in your area.`, result.local, council),
    ...tierBlock(`Regional contracts — active across ${region}`,
      `Providers operating across ${region} that may take on property in ${council} even without a current contract there.`, result.regional, council),
    ...tierBlock(`National contracts — UK-wide providers`,
      `Large providers and Home Office contractors operating nationwide.`, result.national, council),
  ];

  const doc = {
    info: { title: `Provider report — ${council}`, author: "Find a Housing Provider" },
    pageSize: "A4",
    pageMargins: [40, 48, 40, 54],
    content,
    styles: { h1: { fontSize: 19, bold: true, color: SLATE }, h2: { fontSize: 13, bold: true, color: SLATE } },
    defaultStyle: { fontSize: 9.5, color: SLATE, lineHeight: 1.2 },
    footer: (page, count) => ({
      columns: [
        { text: "findahousingprovider.co.uk — independent directory. Verify provider status before any agreement.", fontSize: 7, color: MUTED, margin: [40, 0, 0, 0] },
        { text: `${page} / ${count}`, alignment: "right", fontSize: 7, color: MUTED, margin: [0, 0, 40, 0] },
      ],
      margin: [0, 16, 0, 0],
    }),
  };

  const safe = (result.postcode || "report").replace(/\s+/g, "");
  pdfMake.createPdf(doc).download(`housing-providers-${safe}.pdf`);
}
