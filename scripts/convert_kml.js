import fs from 'fs';
import path from 'path';
import { DOMParser } from '@xmldom/xmldom';
import { kml } from '@tmcw/togeojson';

const kmlPath = path.join(process.cwd(), 'scripts', 'junior-secondary-sites-2025.kml');
const outputPath = path.join(process.cwd(), 'public', 'data', 'school_sites.geojson');

// Ensure output directory exists
const outputDir = path.dirname(outputPath);
if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}

console.log(`Reading KML from ${kmlPath}...`);
const kmlContent = fs.readFileSync(kmlPath, 'utf8');

const parser = new DOMParser();
const kmlDom = parser.parseFromString(kmlContent, 'text/xml');

console.log('Converting to GeoJSON...');
const geoJSON = kml(kmlDom);

// Process features to extract detailed properties from the description HTML table
console.log('Processing features...');
const processedFeatures = geoJSON.features.map(feature => {
  const properties = feature.properties || {};
  let description = properties.description || '';

  // Ensure description is a string
  if (typeof description !== 'string') {
    if (description && description.value) {
      description = description.value;
    } else {
      description = String(description);
    }
  }

  // Extract Centre_code from the description HTML
  // The description typically contains a table with Centre_code
  // Example: <tr><td>Centre_code</td><td>2155</td></tr>

  let centreCode = null;
  const centreCodeMatch = description.match(/<td>Centre_code<\/td>\s*<td>(.*?)<\/td>/);
  if (centreCodeMatch && centreCodeMatch[1]) {
    centreCode = centreCodeMatch[1].trim();
  }

  // Clean up properties
  const newProperties = {
    name: properties.name,
    centreCode: centreCode,
  };

  return {
    ...feature,
    properties: newProperties
  };
});

const outputGeoJSON = {
  type: 'FeatureCollection',
  features: processedFeatures
};

console.log(`Writing ${processedFeatures.length} features to ${outputPath}...`);
fs.writeFileSync(outputPath, JSON.stringify(outputGeoJSON, null, 2));
console.log('Done.');
