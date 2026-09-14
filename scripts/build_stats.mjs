// Regenerates public/stats.json — the figures shown on the homepage stat band.
// Run from the repo root:  node scripts/build_stats.mjs
//
// "Councils covered" counts distinct LOCAL AUTHORITIES that hold at least one
// contract in the dataset. The raw contract data is keyed by awarding body,
// which also includes NHS trusts, housing associations, ministries, regional
// frameworks and procurement portals — those award contracts but are not areas
// a customer can search, so counting them overstates our coverage.
import { readFileSync, writeFileSync } from "node:fs";

const db = JSON.parse(readFileSync("api/_data/db.json"));
const providers = JSON.parse(readFileSync("api/_data/providers.json"));

const DROP = new Set(["council","borough","county","city","district","the","of",
  "metropolitan","unitary","authority","corporation","mbc","mdc","cc"]);
const norm = (s) => String(s || "").toLowerCase().replace(/&/g, " and ")
  .replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter((t) => t && !DROP.has(t)).join(" ");

// Awarding bodies that are not local authorities.
const NOT_A_COUNCIL = [
  /nhs|integrated care board|\bicb\b|foundation trust|teaching hospital/i,
  /ministry|home office|police|probation|fire |ambulance/i,
  /housing group|housing trust|housing society|housing association|\bhousing\b$/i,
  /limited|\bltd\b|\bcic\b|combined authority|greater london authority/i,
  /procurement|commissioning support|shared (business )?service|shared services/i,
  /esourcing|in-tend|eu supply|due north|atamis|lgss|supply hertfordshire/i,
  /regional framework|^coventry - /i,
];
const isCouncil = (name) => !NOT_A_COUNCIL.some((re) => re.test(name));

// A council with an empty list is still searchable but holds no local contract,
// so it is not somewhere we cover.
const groups = new Map();
for (const [key, ids] of Object.entries(db.c)) {
  if (!ids.length) continue;
  const k = norm(key);
  if (!groups.has(k)) groups.set(k, []);
  groups.get(k).push(key);
}
const councils = [...groups.values()]
  .map((keys) => keys.slice().sort((a, b) => b.length - a.length)[0])
  .filter(isCouncil);

// "Contracts processed" = distinct contract titles across the whole dataset.
const contracts = new Set(providers.flatMap((p) => (p.contracts_list || []).flatMap((c) => c.titles || []))).size;
const stats = {
  providers: providers.length,
  councils: councils.length,
  regions: Object.keys(db.r).length,
  in_network: providers.filter((p) => p.in_network).length,
  contracts,
};
writeFileSync("public/stats.json", JSON.stringify(stats));
console.log(stats);
console.log("excluded as not-a-council:", groups.size - councils.length);
