import { DOMParser } from 'xmldom';
import * as toGeoJSON from '@tmcw/togeojson';
import fs from 'fs';
import https from 'https';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const SITES_URL = 'https://www.data.qld.gov.au/dataset/b01b50fc-b8ab-4c88-bc4a-34d42930fea8/resource/9ca39d88-29ca-43ab-a928-3372024163b9/download/senior-secondary-sites-2025.kml';
const OUTPUT_PATH = path.join(__dirname, '..', 'src', 'data', 'schoolSites.json');
const TEMP_KML_PATH = path.join(__dirname, 'temp-sites.kml');

// Brisbane bounding box (approximate)
const BRISBANE_BOUNDS = {
  minLat: -27.7,
  maxLat: -27.0,
  minLng: 152.7,
  maxLng: 153.3
};

function downloadFile(url, dest) {
  return new Promise((resolve, reject) => {
    console.log('Downloading school sites data...');
    const file = fs.createWriteStream(dest);

    const request = (url) => {
      https.get(url, (response) => {
        if (response.statusCode === 301 || response.statusCode === 302) {
          request(response.headers.location);
          return;
        }
        response.pipe(file);
        file.on('finish', () => {
          file.close();
          console.log('Download complete!');
          resolve();
        });
      }).on('error', (err) => {
        fs.unlink(dest, () => {});
        reject(err);
      });
    };

    request(url);
  });
}

function isInBrisbane(coordinates) {
  const [lng, lat] = coordinates;
  return lat >= BRISBANE_BOUNDS.minLat &&
         lat <= BRISBANE_BOUNDS.maxLat &&
         lng >= BRISBANE_BOUNDS.minLng &&
         lng <= BRISBANE_BOUNDS.maxLng;
}

function parseDescription(description) {
  // Parse the HTML table in the description to extract school details
  const result = {};

  if (!description) return result;

  const descStr = typeof description === 'object' ? description.value : description;
  if (!descStr) return result;

  // Extract key-value pairs from the HTML table
  const rowRegex = /<tr><td>([^<]+)<\/td><td>([^<]*)<\/td><\/tr>/gi;
  let match;

  while ((match = rowRegex.exec(descStr)) !== null) {
    const key = match[1].trim();
    const value = match[2].trim();
    result[key] = value;
  }

  return result;
}

async function main() {
  try {
    // Download the KML file
    await downloadFile(SITES_URL, TEMP_KML_PATH);

    // Read and parse the KML
    console.log('Parsing KML...');
    const kmlContent = fs.readFileSync(TEMP_KML_PATH, 'utf-8');
    const dom = new DOMParser().parseFromString(kmlContent);

    // Convert to GeoJSON
    console.log('Converting to GeoJSON...');
    const geojson = toGeoJSON.kml(dom);

    console.log(`Found ${geojson.features.length} total school sites`);

    // Filter to Brisbane area and process
    const brisbaneSchools = geojson.features
      .filter(feature => {
        if (!feature.geometry || feature.geometry.type !== 'Point') return false;
        return isInBrisbane(feature.geometry.coordinates);
      })
      .map(feature => {
        const coords = feature.geometry.coordinates;
        const props = feature.properties || {};
        const details = parseDescription(props.description);

        return {
          name: props.name || details['Centre_name'] || 'Unknown',
          code: details['Centre_code'] || null,
          latitude: coords[1],
          longitude: coords[0],
          rawProperties: props
        };
      });

    console.log(`Filtered to ${brisbaneSchools.length} Brisbane area schools`);

    // Create output object with metadata
    const output = {
      metadata: {
        source: 'Queensland Government Open Data Portal',
        description: 'Senior Secondary School Sites (Years 11-12) - 2025',
        license: 'Creative Commons Attribution 4.0',
        downloadedAt: new Date().toISOString(),
        originalUrl: SITES_URL
      },
      schools: brisbaneSchools
    };

    // Write output
    fs.writeFileSync(OUTPUT_PATH, JSON.stringify(output, null, 2));
    console.log(`Saved to ${OUTPUT_PATH}`);

    // Cleanup temp file
    fs.unlinkSync(TEMP_KML_PATH);
    console.log('Cleanup complete!');

    // Print summary
    console.log('\nSchool sites summary:');
    brisbaneSchools.forEach(s => {
      console.log(`  - ${s.name} (${s.latitude.toFixed(4)}, ${s.longitude.toFixed(4)})`);
    });

  } catch (error) {
    console.error('Error:', error);
    process.exit(1);
  }
}

main();
