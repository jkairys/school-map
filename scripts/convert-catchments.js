import { DOMParser } from 'xmldom';
import * as toGeoJSON from '@tmcw/togeojson';
import fs from 'fs';
import https from 'https';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CATCHMENT_URL = 'https://www.data.qld.gov.au/dataset/b01b50fc-b8ab-4c88-bc4a-34d42930fea8/resource/930ba950-9661-4edb-bb04-8cdfb3305d33/download/senior-secondary-catchments-2025.kml';
const OUTPUT_PATH = path.join(__dirname, '..', 'src', 'data', 'catchments.json');
const TEMP_KML_PATH = path.join(__dirname, 'temp-catchments.kml');

// Brisbane bounding box (approximate)
const BRISBANE_BOUNDS = {
  minLat: -27.7,
  maxLat: -27.0,
  minLng: 152.7,
  maxLng: 153.3
};

function downloadFile(url, dest) {
  return new Promise((resolve, reject) => {
    console.log('Downloading catchment data...');
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
  // Check if any coordinate is within Brisbane bounds
  const checkCoord = (coord) => {
    const [lng, lat] = coord;
    return lat >= BRISBANE_BOUNDS.minLat &&
           lat <= BRISBANE_BOUNDS.maxLat &&
           lng >= BRISBANE_BOUNDS.minLng &&
           lng <= BRISBANE_BOUNDS.maxLng;
  };

  const flattenAndCheck = (coords) => {
    if (typeof coords[0] === 'number') {
      return checkCoord(coords);
    }
    return coords.some(c => flattenAndCheck(c));
  };

  return flattenAndCheck(coordinates);
}

async function main() {
  try {
    // Download the KML file
    await downloadFile(CATCHMENT_URL, TEMP_KML_PATH);

    // Read and parse the KML
    console.log('Parsing KML...');
    const kmlContent = fs.readFileSync(TEMP_KML_PATH, 'utf-8');
    const dom = new DOMParser().parseFromString(kmlContent);

    // Convert to GeoJSON
    console.log('Converting to GeoJSON...');
    const geojson = toGeoJSON.kml(dom);

    console.log(`Found ${geojson.features.length} total catchment areas`);

    // Filter to Brisbane area only
    const brisbaneCatchments = geojson.features.filter(feature => {
      if (!feature.geometry || !feature.geometry.coordinates) return false;
      return isInBrisbane(feature.geometry.coordinates);
    });

    console.log(`Filtered to ${brisbaneCatchments.length} Brisbane area catchments`);

    // Create output object with metadata
    const output = {
      type: 'FeatureCollection',
      metadata: {
        source: 'Queensland Government Open Data Portal',
        description: 'Senior Secondary School Catchments (Years 11-12) - 2025',
        license: 'Creative Commons Attribution 4.0',
        downloadedAt: new Date().toISOString(),
        originalUrl: CATCHMENT_URL
      },
      features: brisbaneCatchments.map(feature => ({
        type: 'Feature',
        properties: {
          name: feature.properties?.name || feature.properties?.Name || 'Unknown',
          description: feature.properties?.description || feature.properties?.Description || '',
          ...feature.properties
        },
        geometry: feature.geometry
      }))
    };

    // Write output
    fs.writeFileSync(OUTPUT_PATH, JSON.stringify(output, null, 2));
    console.log(`Saved to ${OUTPUT_PATH}`);

    // Cleanup temp file
    fs.unlinkSync(TEMP_KML_PATH);
    console.log('Cleanup complete!');

    // Print summary
    console.log('\nCatchment summary:');
    output.features.forEach(f => {
      console.log(`  - ${f.properties.name}`);
    });

  } catch (error) {
    console.error('Error:', error);
    process.exit(1);
  }
}

main();
