import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const projectRoot = path.resolve(__dirname, '..');
const geoJsonPath = path.join(projectRoot, 'public/data/catchments.geojson');
const schoolsJsonPath = path.join(projectRoot, 'scraper/schools.json');
const naplanDataPath = path.join(projectRoot, 'public/data/naplan_data.json');

// Load data
const geoJson = JSON.parse(fs.readFileSync(geoJsonPath, 'utf8'));
const schools = JSON.parse(fs.readFileSync(schoolsJsonPath, 'utf8'));
const naplanData = JSON.parse(fs.readFileSync(naplanDataPath, 'utf8'));

// Build maps
const stateIdToSchool = new Map();
schools.forEach(s => {
  const simpleId = parseInt(s.StateProvinceId, 10).toString();
  if (!stateIdToSchool.has(simpleId)) {
    stateIdToSchool.set(simpleId, []);
  }
  stateIdToSchool.get(simpleId).push(s);
});

// Find missing schools
const missing = [];
const hasData = new Set(Object.keys(naplanData));

geoJson.features.forEach(f => {
  const name = f.properties.name;
  const match = f.properties.description?.value?.match(/Centre_code<\/td><td>(\d+)<\/td>/);

  if (!match) {
    console.log(`⚠️  No centre code found for: ${name}`);
    return;
  }

  const code = parseInt(match[1], 10).toString();

  if (!hasData.has(name)) {
    const schoolsWithCode = stateIdToSchool.get(code);
    missing.push({
      catchmentName: name,
      centreCode: code,
      inDatabase: schoolsWithCode ? `Yes (${schoolsWithCode.length})` : 'No',
      schoolDetails: schoolsWithCode ? schoolsWithCode.map(s => `${s.SchoolName} (${s.ACARAId})`).join(', ') : 'N/A'
    });
  }
});

console.log('\n=== MISSING NAPLAN DATA ===\n');
console.log(`Total catchments: ${geoJson.features.length}`);
console.log(`Catchments with data: ${Object.keys(naplanData).length}`);
console.log(`Missing data: ${missing.length}\n`);

// Group by reason
const notInDatabase = missing.filter(m => m.inDatabase === 'No');
const inDatabaseButNotLinked = missing.filter(m => m.inDatabase !== 'No');

console.log(`\n📋 NOT IN DATABASE (${notInDatabase.length}):`);
console.log('These catchments have no matching school in schools.json\n');
notInDatabase.forEach(m => {
  console.log(`  • ${m.catchmentName} (Centre Code: ${m.centreCode})`);
});

console.log(`\n\n🔗 IN DATABASE BUT NOT LINKED (${inDatabaseButNotLinked.length}):`);
console.log('These schools exist but failed to match to catchments\n');
inDatabaseButNotLinked.forEach(m => {
  console.log(`  • ${m.catchmentName} (Centre Code: ${m.centreCode})`);
  console.log(`    Schools: ${m.schoolDetails}\n`);
});

// Export list of missing centre codes for scraping
const missingCodes = notInDatabase.map(m => ({
  name: m.catchmentName,
  centreCode: m.centreCode
}));

fs.writeFileSync(
  path.join(projectRoot, 'scripts/missing_schools.json'),
  JSON.stringify(missingCodes, null, 2)
);

console.log(`\n✅ Wrote missing_schools.json with ${missingCodes.length} schools to add to scraper`);
