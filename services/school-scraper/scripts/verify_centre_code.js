
import fs from 'fs';
const geoJson = JSON.parse(fs.readFileSync('../../apps/frontend/public/data/catchments.geojson', 'utf8'));
const feature = geoJson.features.find(f => f.properties.name === "North Lakes State College");
if (feature) {
  const match = feature.properties.description.value.match(/Centre_code<\/td><td>(\d+)<\/td>/);
  console.log('Centre Code:', match ? match[1] : 'Not Found');
} else {
  console.log('Feature Not Found');
}
