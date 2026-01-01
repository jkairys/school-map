import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const schoolsJsonPath = path.join(__dirname, 'scraper/schools.json');
const geoJsonPath = path.join(__dirname, 'public/data/catchments.geojson');
const outputDir = path.join(__dirname, 'scraper/output');

const schools = JSON.parse(fs.readFileSync(schoolsJsonPath, 'utf8'));
const geoJson = JSON.parse(fs.readFileSync(geoJsonPath, 'utf8'));
const scraperFiles = fs.readdirSync(outputDir).filter(f => f.endsWith('.json'));

// 1. Build Lookup Maps
const acaraToStateId = new Map();
schools.forEach(s => {
  // StateProvinceId "000002155" -> "2155"
  const simpleId = parseInt(s.StateProvinceId, 10).toString();
  acaraToStateId.set(s.ACARAId, simpleId);
});

const geoByCode = new Map();
const geoByName = new Map();
const geoByNameNorm = new Map();

geoJson.features.forEach(f => {
  const name = f.properties.name;
  const match = f.properties.description?.value?.match(/Centre_code<\/td><td>(\d+)<\/td>/);
  if (match) {
    const code = parseInt(match[1], 10).toString();
    geoByCode.set(code, f);
  }

  geoByName.set(name, f);

  // Normalization
  let norm = name
    .replace(/SHS/g, 'State High School') // Reverse normalization for lookup? Or match standard
    .replace(/SS/g, 'State School')
    .replace(/State Secondary College/g, 'State Secondary College');

  // Wait, my previous script did Scraped Name -> Geo Name (SHS).
  // Let's normalize Geo Names to be like Scraped Names (or vice versa).
  // Easier: Normalize both to a common standard.
  // Let's use the successful logic from check_overlap.js
  // Scraped "State High School" -> "SHS"
  // Geo already "SHS".
  // So if I normalize Geo keys... wait Geo keys are already "SHS".
  // So I map "SHS" keys.
  geoByNameNorm.set(name, f);
});

// 2. Iterate Scraped Files
let linkedByName = 0;
let linkedByCode = 0;
let linkedByBoth = 0;
let codeFailures = []; // Have ID but failed to match Geo
let nameFailures = [];

scraperFiles.forEach(file => {
  const content = JSON.parse(fs.readFileSync(path.join(outputDir, file), 'utf8'));
  const acaraId = content.acaraId;
  const schoolName = content.schoolName.split(',')[0].trim();

  // Name Strategy
  let nameMatch = false;
  let normalizedName = schoolName
    .replace(/State High School/g, 'SHS')
    .replace(/State School/g, 'SS');

  if (geoByNameNorm.has(normalizedName) || geoByNameNorm.has(schoolName)) {
    nameMatch = true;
    linkedByName++;
  }

  // Code Strategy
  let codeMatch = false;
  const stateId = acaraToStateId.get(acaraId);
  if (stateId) {
    if (geoByCode.has(stateId)) {
      codeMatch = true;
      linkedByCode++;
    }
  }

  if (nameMatch && codeMatch) linkedByBoth++;

  if (nameMatch && !codeMatch) {
    // console.log(`[Name ONLY] ${schoolName} (ID: ${stateId})`);
  }
  if (!nameMatch && codeMatch) {
    console.log(`[Code ONLY] ${schoolName} (ID: ${stateId})`);
  }
});

console.log(`\nTotal Scraped Schools: ${scraperFiles.length}`);
console.log(`Linked by Name: ${linkedByName}`);
console.log(`Linked by Code: ${linkedByCode}`);
console.log(`Linked by Both: ${linkedByBoth}`);
