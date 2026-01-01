
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Paths
const projectRoot = path.resolve(__dirname, '..');
const schoolsJsonPath = path.join(projectRoot, 'scraper/schools.json');
const geoJsonPath = path.join(projectRoot, 'public/data/catchments.geojson');
const scraperOutputDir = path.join(projectRoot, 'scraper/output');
const finalOutputPath = path.join(projectRoot, 'public/data/naplan_data.json');

console.log('Starting NAPLAN data processing...');

// 1. Load Data
try {
  const schools = JSON.parse(fs.readFileSync(schoolsJsonPath, 'utf8'));
  const geoJson = JSON.parse(fs.readFileSync(geoJsonPath, 'utf8'));
  const scraperFiles = fs.readdirSync(scraperOutputDir).filter(f => f.endsWith('.json'));

  console.log(`Loaded ${schools.length} schools from database.`);
  console.log(`Loaded ${geoJson.features.length} catchment zones.`);
  console.log(`Found ${scraperFiles.length} scraped school files.`);

  // 2. Build Lookup Maps

  // Map ACARA ID -> StateProvinceId (normalized to string without leading zeros)
  const acaraToStateId = new Map();
  schools.forEach(s => {
    // StateProvinceId format "000002155" -> "2155"
    const simpleId = parseInt(s.StateProvinceId, 10).toString();
    acaraToStateId.set(s.ACARAId, simpleId);
  });

  // Map StateProvinceId (Centre Code) -> GeoJSON Feature Name
  const codeToGeoName = new Map();
  // Map Normalized Geo Name -> GeoJSON Feature Name (for name fallback)
  const normGeoNameMap = new Map();

  geoJson.features.forEach(f => {
    const name = f.properties.name;

    // Extract Centre_code
    const match = f.properties.description?.value?.match(/Centre_code<\/td><td>(\d+)<\/td>/);
    if (match) {
      const code = parseInt(match[1], 10).toString();
      codeToGeoName.set(code, name);
    }

    // Normalize Name
    const norm = name.replace(/SHS/g, 'State High School').replace(/SS/g, 'State School').toLowerCase();
    normGeoNameMap.set(norm, name);
    normGeoNameMap.set(name.toLowerCase(), name); // Also map exact name
  });

  // 3. Process Scraped Data
  const finalData = {};
  let stats = {
    total: scraperFiles.length,
    linkedByCode: 0,
    linkedByName: 0,
    unlinked: 0
  };

  scraperFiles.forEach(file => {
    const content = JSON.parse(fs.readFileSync(path.join(scraperOutputDir, file), 'utf8'));
    const { acaraId, schoolName, profileData, results } = content;

    let linkedName = null;

    // Strategy 1: Link via Code
    const stateId = acaraToStateId.get(acaraId);
    if (stateId && codeToGeoName.has(stateId)) {
      linkedName = codeToGeoName.get(stateId);
      stats.linkedByCode++;
    }

    // Strategy 2: Link via Name (Fallback)
    if (!linkedName) {
      const normScraped = schoolName.split(',')[0].trim().toLowerCase();
      // Try direct match or normalized match
      // Note: Scraped has "State High School", Geo has "SHS".
      // We need to normalize Scraped "State High School" -> "SHS" OR match against full expanded geo map.
      // In step 2 we normalized Geo "SHS" -> "State High School". So we can match "state high school" to "state high school".

      if (normGeoNameMap.has(normScraped)) {
        linkedName = normGeoNameMap.get(normScraped);
        stats.linkedByName++;
      } else {
        // Try cleaning "State High School" -> "SHS" manually just in case
        const variant = normScraped.replace(/state high school/g, 'shs').replace(/state school/g, 'ss');
        if (normGeoNameMap.has(variant)) {
          linkedName = normGeoNameMap.get(variant);
          stats.linkedByName++;
        }
      }
    }

    if (linkedName) {
      finalData[linkedName] = {
        acaraId,
        schoolName, // Original full name
        profile: profileData,
        naplan: results?.tableData
      };
    } else {
      stats.unlinked++;
      // console.warn(`Unlinked: ${schoolName} (${acaraId})`);
    }
  });

  // 4. Output Result
  fs.writeFileSync(finalOutputPath, JSON.stringify(finalData, null, 2));

  console.log('\nProcessing Complete!');
  console.log(`Generated: ${finalOutputPath}`);
  console.log('Statistics:', stats);
  console.log(`Match Rate: ${((stats.total - stats.unlinked) / stats.total * 100).toFixed(1)}%`);

} catch (err) {
  console.error('Error processing NAPLAN data:', err);
  process.exit(1);
}
