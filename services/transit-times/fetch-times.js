import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import 'dotenv/config';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const STATIONS_FILE = path.join(__dirname, '../public/data/railway-station-locations.geojson');
const OUTPUT_FILE = path.join(__dirname, '../public/data/station-transit-times.json');

// Central Station coordinates (destination)
const CENTRAL_STATION = {
  name: 'Central',
  lat: -27.465665943606396,
  lng: 153.0259340348434
};

// Gold Coast Light Rail (G:link) station names to exclude
const LIGHT_RAIL_STATIONS = new Set([
  'Nerang Street',
  'Southport',
  'Southport South',
  'Broadwater Parklands',
  'Main Beach',
  'Surfers Paradise North',
  'Surfers Paradise',
  'Cypress Avenue',
  'Cavill Avenue',
  'Florida Gardens',
  'Northcliffe',
  'Broadbeach North',
  'Broadbeach South',
  'Gold Coast University Hospital',
  'Griffith University',
  'Queen Street',
  'Parkwood East'
]);

// Filter function to identify heavy rail stations
function isHeavyRailStation(feature) {
  const name = feature.properties.name;
  const lon = feature.geometry.coordinates[0];

  // Exclude known light rail stations
  if (LIGHT_RAIL_STATIONS.has(name)) {
    return false;
  }

  // Parkwood at lon > 153.34 is light rail
  if (name === 'Parkwood' && lon > 153.34) {
    return false;
  }

  // Helensvale has two entries - keep only one (the one with lower objectid, which is heavy rail)
  // We'll deduplicate by name later

  return true;
}

// Deduplicate stations by name (keep first occurrence)
function deduplicateStations(stations) {
  const seen = new Map();
  return stations.filter(station => {
    const name = station.properties.name;
    if (seen.has(name)) {
      return false;
    }
    seen.set(name, true);
    return true;
  });
}

async function fetchTransitTime(origin, destination, departureTime, apiKey) {
  const url = new URL('https://maps.googleapis.com/maps/api/directions/json');
  url.searchParams.set('origin', `${origin.lat},${origin.lng}`);
  url.searchParams.set('destination', `${destination.lat},${destination.lng}`);
  url.searchParams.set('mode', 'transit');
  url.searchParams.set('transit_mode', 'rail');
  url.searchParams.set('departure_time', Math.floor(departureTime.getTime() / 1000).toString());
  url.searchParams.set('key', apiKey);

  const response = await fetch(url);
  const data = await response.json();

  if (data.status !== 'OK') {
    throw new Error(`API error: ${data.status} - ${data.error_message || 'Unknown error'}`);
  }

  const route = data.routes[0];
  const leg = route.legs[0];

  return {
    durationSeconds: leg.duration.value,
    durationText: leg.duration.text,
    departureTime: leg.departure_time?.text || null,
    arrivalTime: leg.arrival_time?.text || null,
    steps: leg.steps
      .filter(step => step.travel_mode === 'TRANSIT')
      .map(step => ({
        line: step.transit_details?.line?.short_name || step.transit_details?.line?.name,
        departureStop: step.transit_details?.departure_stop?.name,
        arrivalStop: step.transit_details?.arrival_stop?.name,
        numStops: step.transit_details?.num_stops
      }))
  };
}

function getNextWeekday8AM() {
  const now = new Date();
  const target = new Date(now);

  // Move to next weekday
  while (target.getDay() === 0 || target.getDay() === 6) {
    target.setDate(target.getDate() + 1);
  }

  // If today is a weekday but past 8am, move to tomorrow
  if (target.getDate() === now.getDate() && now.getHours() >= 8) {
    target.setDate(target.getDate() + 1);
    // Skip weekends
    while (target.getDay() === 0 || target.getDay() === 6) {
      target.setDate(target.getDate() + 1);
    }
  }

  // Set to 8:00 AM
  target.setHours(8, 0, 0, 0);

  return target;
}

async function main() {
  const isDryRun = process.argv.includes('--dry-run');
  const apiKey = process.env.GOOGLE_MAPS_API_KEY;

  if (!apiKey && !isDryRun) {
    console.error('Error: GOOGLE_MAPS_API_KEY environment variable not set');
    console.error('Create a .env file with: GOOGLE_MAPS_API_KEY=your_key_here');
    process.exit(1);
  }

  // Read stations
  const geojson = JSON.parse(fs.readFileSync(STATIONS_FILE, 'utf8'));
  console.log(`Loaded ${geojson.features.length} total stations`);

  // Filter to heavy rail only
  let stations = geojson.features.filter(isHeavyRailStation);
  console.log(`After filtering light rail: ${stations.length} stations`);

  // Deduplicate by name
  stations = deduplicateStations(stations);
  console.log(`After deduplication: ${stations.length} unique stations`);

  // Filter to operational only
  const operationalStations = stations.filter(s => s.properties.operational_status === 'Operational');
  const underConstructionStations = stations.filter(s => s.properties.operational_status === 'Under Construction');

  console.log(`Operational: ${operationalStations.length}, Under Construction: ${underConstructionStations.length}`);

  // Exclude Central Station itself from the list (it's our destination)
  const stationsToProcess = operationalStations.filter(s => s.properties.name !== 'Central');
  console.log(`Stations to process (excluding Central): ${stationsToProcess.length}`);

  if (isDryRun) {
    console.log('\n=== DRY RUN - Stations that would be processed ===\n');
    stationsToProcess.forEach((station, i) => {
      const coords = station.geometry.coordinates;
      console.log(`${i + 1}. ${station.properties.name} (${coords[1].toFixed(4)}, ${coords[0].toFixed(4)})`);
    });
    console.log(`\nTotal API calls that would be made: ${stationsToProcess.length}`);
    console.log(`Estimated cost: ~$${(stationsToProcess.length * 0.005).toFixed(2)} USD`);
    return;
  }

  const departureTime = getNextWeekday8AM();
  console.log(`\nUsing departure time: ${departureTime.toLocaleString()}`);

  const results = [];
  const errors = [];

  for (let i = 0; i < stationsToProcess.length; i++) {
    const station = stationsToProcess[i];
    const name = station.properties.name;
    const coords = station.geometry.coordinates;
    const origin = { lat: coords[1], lng: coords[0] };

    console.log(`[${i + 1}/${stationsToProcess.length}] Fetching: ${name}...`);

    try {
      const transitData = await fetchTransitTime(origin, CENTRAL_STATION, departureTime, apiKey);

      results.push({
        name,
        objectid: station.properties.objectid,
        coordinates: coords,
        transitToCentral: transitData
      });

      console.log(`  -> ${transitData.durationText} (${transitData.departureTime} - ${transitData.arrivalTime})`);

      // Rate limiting - 50 requests per second is the limit, but let's be gentle
      await new Promise(r => setTimeout(r, 200));

    } catch (error) {
      console.error(`  -> Error: ${error.message}`);
      errors.push({ name, error: error.message });
    }
  }

  // Sort by duration
  results.sort((a, b) => a.transitToCentral.durationSeconds - b.transitToCentral.durationSeconds);

  // Save results
  const output = {
    generatedAt: new Date().toISOString(),
    departureTime: departureTime.toISOString(),
    destination: CENTRAL_STATION,
    stations: results,
    errors: errors.length > 0 ? errors : undefined
  };

  fs.writeFileSync(OUTPUT_FILE, JSON.stringify(output, null, 2));
  console.log(`\nResults saved to: ${OUTPUT_FILE}`);
  console.log(`Successfully processed: ${results.length} stations`);
  if (errors.length > 0) {
    console.log(`Errors: ${errors.length} stations`);
  }
}

main().catch(console.error);
