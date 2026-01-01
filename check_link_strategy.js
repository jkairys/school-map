import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const schoolsJsonPath = path.join(__dirname, 'scraper/schools.json');
const geoJsonPath = path.join(__dirname, 'public/data/catchments.geojson');
const outputDir = path.join(__dirname, 'scraper/output');

console.log('Reading data...');
const schools = JSON.parse(fs.readFileSync(schoolsJsonPath, 'utf8'));
const geoJson = JSON.parse(fs.readFileSync(geoJsonPath, 'utf8'));

// Create ACARA ID -> School Map
const acaraMap = new Map();
schools.forEach(s => {
  // StateProvinceId format "000002155" -> "2155"
  const stateIdParsed = parseInt(s.StateProvinceId, 10).toString();
  acaraMap.set(stateIdParsed, s.ACARAId);
});

console.log(`Loaded ${schools.length} schools from schools.json`);

// Check GeoJSON linkages
let matches = 0;
let total = 0;
let missing = [];

const availableScraperFiles = new Set(fs.readdirSync(outputDir).filter(f => f.endsWith('.json')));

geoJson.features.forEach(f => {
  total++;
  // Extract Centre_code from HTML description
  // Format: <tr><td>Centre_code</td><td>0517</td></tr>
  const match = f.properties.description.value.match(/Centre_code<\/td><td>(\d+)<\/td>/);

  if (match) {
    const centreCode = parseInt(match[1], 10).toString();
    const acaraId = acaraMap.get(centreCode);

    if (acaraId) {
      // Check if we actually have scraped data for this ACARA ID
      if (availableScraperFiles.has(`${acaraId}.json`)) {
        matches++;
      } else {
        // console.log(`Linked ${f.properties.name} (Code: ${centreCode}) to ACARA ${acaraId}, but no scraped file found.`);
        missing.push({ name: f.properties.name, code: centreCode, acaraId });
      }
    } else {
      // console.log(`No ACARA ID found for ${f.properties.name} (Code: ${centreCode})`);
      missing.push({ name: f.properties.name, code: centreCode, reason: "No ACARA ID" });
    }
  } else {
    console.log(`Could not find Centre_code for ${f.properties.name}`);
  }
});

console.log(`\nMatch Results:`);
console.log(`Total Catchments: ${total}`);
console.log(`Matches with Scraped Data: ${matches}`);
console.log(`Match Rate: ${((matches / total) * 100).toFixed(1)}%`);

if (missing.length > 0) {
  console.log(`\nSample Missing (${missing.length}):`);
  missing.slice(0, 10).forEach(m => console.log(`  ${m.name} (Code: ${m.code}) - ${m.reason || "Missing Scraped File"}`));
}
