// Dumps the borough search result for all 33 London boroughs to
// data/london_boroughs.json, which scripts/export_london_boroughs_xlsx.py turns
// into the Excel breakdown. Going through matchByCouncil keeps the workbook and
// the live site in step instead of re-deriving coverage a second way.
//
//   node scripts/dump_london_boroughs.mjs
import { writeFileSync } from "node:fs";
import { matchByCouncil } from "../api/_lib/match.js";

const BOROUGHS = [
  "Barking and Dagenham", "Barnet", "Bexley", "Brent", "Bromley", "Camden",
  "City of London", "Croydon", "Ealing", "Enfield", "Greenwich", "Hackney",
  "Hammersmith and Fulham", "Haringey", "Harrow", "Havering", "Hillingdon",
  "Hounslow", "Islington", "Kensington and Chelsea", "Kingston upon Thames",
  "Lambeth", "Lewisham", "Merton", "Newham", "Redbridge", "Richmond upon Thames",
  "Southwark", "Sutton", "Tower Hamlets", "Waltham Forest", "Wandsworth",
  "Westminster",
];

const out = {};
let rowCount = 0;
for (const borough of BOROUGHS) {
  const m = matchByCouncil(borough);
  const rows = [];
  for (const tier of ["local", "county", "regional", "national"]) {
    for (const p of m[tier] || []) rows.push({ tier, p });
  }
  out[borough] = rows;
  rowCount += rows.length;
  console.log(`${borough.padEnd(26)} ${String(rows.length).padStart(4)} providers`);
}

writeFileSync(new URL("../data/london_boroughs.json", import.meta.url), JSON.stringify(out));
console.log(`\n${BOROUGHS.length} boroughs, ${rowCount} borough × provider rows`);
