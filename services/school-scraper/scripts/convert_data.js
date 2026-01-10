import fs from 'fs';
import path from 'path';
import { kml } from '@tmcw/togeojson';
import { DOMParser } from '@xmldom/xmldom';

const KML_PATH = '../../apps/frontend/public/data/junior-secondary-catchments-2025.kml';
const GEOJSON_PATH = '../../apps/frontend/public/data/catchments.geojson';
const RANKINGS_PATH = '../../apps/frontend/public/data/school_rankings.json';

// Ensure directories exist
const ensureDirectoryExistence = (filePath) => {
  const dirname = path.dirname(filePath);
  if (fs.existsSync(dirname)) {
    return true;
  }
  ensureDirectoryExistence(dirname);
  fs.mkdirSync(dirname);
};

// Convert KML to GeoJSON
const convertKmlToGeoJson = () => {
  console.log('Reading KML file...');
  const kmlContent = fs.readFileSync(KML_PATH, 'utf8');
  const kmlDom = new DOMParser().parseFromString(kmlContent);
  const geoJson = kml(kmlDom);

  console.log(`Converted ${geoJson.features.length} features.`);

  // Load Rankings
  const rankings = JSON.parse(fs.readFileSync(RANKINGS_PATH, 'utf8'));
  const rankingMap = new Map(rankings.map(r => [r['School Name'].toLowerCase(), r]));

  // Merge Data
  geoJson.features = geoJson.features.map(feature => {
    const schoolName = feature.properties.name;
    const cleanName = schoolName.replace(/\s+/g, ' ').trim().toLowerCase();

    // Fuzzy match or direct match
    let match = rankingMap.get(cleanName);

    // Try to match without "State High School" etc if not found? 
    // For now simple match.

    if (match) {
      feature.properties.rank = match['Overall Score'];
      feature.properties.locality = match['Locality'];
    }

    return feature;
  });

  fs.writeFileSync(GEOJSON_PATH, JSON.stringify(geoJson));
  console.log('Saved GeoJSON to', GEOJSON_PATH);
};

convertKmlToGeoJson();
