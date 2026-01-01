import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const scraperDir = path.join(__dirname, 'scraper/output');
const geoJsonPath = path.join(__dirname, 'public/data/catchments.geojson');

console.log('Reading scraper output...');
const scraperFiles = fs.readdirSync(scraperDir).filter(f => f.endsWith('.json'));
const scrapedSchools = scraperFiles.map(f => {
  const content = JSON.parse(fs.readFileSync(path.join(scraperDir, f), 'utf8'));

  let rawName = content.schoolName.split(',')[0].trim();
  // Normalize
  let normalized = rawName
    .replace(/State High School/g, 'SHS')
    .replace(/State School/g, 'SS')
    .replace(/State Secondary College/g, 'State Secondary College') // Keep explicit?
    //.replace(/State College/g, 'SC') // GeoJSON seems to use "State College" often
    .replace(/Community College/g, 'Community College');

  return {
    id: content.acaraId,
    name: rawName,
    normalized: normalized
  };
});

console.log('Reading GeoJSON...');
const geoJson = JSON.parse(fs.readFileSync(geoJsonPath, 'utf8'));
const geoSchools = geoJson.features.map(f => ({
  name: f.properties.name,
}));

let matches = 0;

scrapedSchools.forEach(s => {
  const match = geoSchools.find(g =>
    g.name === s.name ||
    g.name === s.normalized ||
    g.name.toLowerCase() === s.normalized.toLowerCase()
  );
  if (match) {
    matches++;
  } else {
    // console.log(`No match: ${s.name} (norm: ${s.normalized})`);
  }
});

console.log(`Total Matches: ${matches} out of ${scrapedSchools.length}`);

// Debug non-matches
console.log('\nSample non-matches:');
scrapedSchools.filter(s => !geoSchools.find(g => g.name === s.normalized || g.name === s.name))
  .slice(0, 10)
  .forEach(s => console.log(`${s.name} -> ${s.normalized}`));
