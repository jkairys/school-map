import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, '..');

// Load data
const schoolsPath = path.join(projectRoot, 'scraper/schools.json');
const schools = JSON.parse(fs.readFileSync(schoolsPath, 'utf8'));
const schoolsToAdd = JSON.parse(fs.readFileSync(path.join(projectRoot, 'scripts/schools_to_add.json'), 'utf8'));

console.log(`Current schools count: ${schools.length}`);
console.log(`Schools to add: ${schoolsToAdd.length}`);

// Check for duplicates
const existingAcaraIds = new Set(schools.map(s => s.ACARAId));
const newSchools = schoolsToAdd.filter(s => !existingAcaraIds.has(s.ACARAId));

if (newSchools.length < schoolsToAdd.length) {
  console.log(`⚠️  ${schoolsToAdd.length - newSchools.length} schools already exist in database`);
}

// Add new schools
const updatedSchools = [...schools, ...newSchools];

// Write back
fs.writeFileSync(schoolsPath, JSON.stringify(updatedSchools, null, 2));

console.log(`✅ Added ${newSchools.length} schools to ${schoolsPath}`);
console.log(`New total: ${updatedSchools.length} schools`);

// Output list of ACARA IDs to scrape
const idsToScrape = newSchools.map(s => s.ACARAId);
console.log(`\nACARA IDs to scrape:`);
console.log(idsToScrape.join(' '));
