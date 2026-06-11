// Reusable outreach email templates (shown on the Resources page and in the PDF)
// plus a helper to find the contract a provider holds with a given council.

const COUNCIL_DROP = new Set(["council", "borough", "county", "city", "district", "the", "of",
  "metropolitan", "unitary", "authority", "corporation", "mbc", "mdc", "cc"]);
function normCouncil(s) {
  return String(s || "").toLowerCase().replace(/&/g, " and ").replace(/[^a-z0-9 ]/g, " ")
    .split(/\s+/).filter((t) => t && !COUNCIL_DROP.has(t)).join(" ");
}

// Find the provider's contract entry for a given council (from contracts_list).
export function contractForCouncil(provider, council) {
  const key = normCouncil(council);
  const list = provider.contracts_list || [];
  if (!key) return null;
  return list.find((g) => normCouncil(g.council).includes(key) || key.includes(normCouncil(g.council))) || null;
}

// Contracts that relate to the searched area: the council's own contracts if any,
// otherwise contracts the provider holds elsewhere in the same region.
export function areaContractsFor(provider, council, region, county) {
  const list = provider.contracts_list || [];
  const key = normCouncil(council);
  const councilEntries = key
    ? list.filter((g) => { const gk = normCouncil(g.council); return gk.includes(key) || key.includes(gk); })
    : [];
  if (councilEntries.length) return { scope: "council", entries: councilEntries };
  // county-council frameworks covering the whole county
  const ckey = normCouncil(county || "");
  const countyEntries = ckey ? list.filter((g) => g.scope === "County" && normCouncil(g.county || "") === ckey) : [];
  if (countyEntries.length) return { scope: "county", entries: countyEntries };
  // only genuinely regional (pan-region) contracts count for the region tier
  const regionEntries = region ? list.filter((g) => g.scope === "Regional" && g.region === region) : [];
  if (regionEntries.length) return { scope: "region", entries: regionEntries };
  const nationalEntries = list.filter((g) => g.scope === "National");
  if (nationalEntries.length) return { scope: "national", entries: nationalEntries };
  return { scope: "none", entries: [] };
}

export const TEMPLATES = [
  {
    id: "direct",
    title: "Template 1 — Direct approach (reference their contract)",
    blurb: "Use when the provider holds a contract with your council. Reference the exact contract shown on their profile.",
    subject: "Property to lease in the [council] area",
    body: `Dear Sir or Madam,

I'm a landlord in the [council] area with a property available to lease:

• Property type: [e.g. 6-bed semi-detached HMO / flat]
• Bedrooms: [   ]   Bathrooms: [   ]   Kitchens: [   ]
• Parking: [private driveway / on-street]
• Full address: [                                  ]
• Available from: [date]

I can see you currently hold a contract with [council] for [the contract shown on their profile], and I wanted to reach out to ask whether you — or a housing association you partner with — are looking to lease properties from private landlords in this area.

If so, I'd be grateful if the appropriate person could get in touch.

Kind regards,
[Your name]
[Phone number / email]`,
  },
  {
    id: "short",
    title: "Template 2 — Short introduction",
    blurb: "A briefer first approach for any provider or housing association operating in your area.",
    subject: "Private landlord — property available for supported housing in [area]",
    body: `Dear [Provider name],

I'm a private landlord with a [property type, e.g. 4-bed house] in [area / postcode] that I'm looking to lease to a care or housing provider on a long-term basis.

I understand you provide supported housing across [council / region]. Would you, or a housing association you work with, be interested in leasing it? In brief:

• [number] bedrooms · [number] bathrooms · [parking]
• Available from [date]

I'd welcome a short call with the right person to discuss.

Best regards,
[Your name]
[Phone number / email]`,
  },
];
