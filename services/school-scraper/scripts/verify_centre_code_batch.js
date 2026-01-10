
import fs from 'fs';
const geoJson = JSON.parse(fs.readFileSync('../../apps/frontend/public/data/catchments.geojson', 'utf8'));

const schools = [
  "North Lakes State College",
  "Whites Hill State College",
  "Capalaba State College",
  "Kelvin Grove State College",
  "Earnshaw State College",
  "Ormeau Woods State High School",
  "Ormeau Woods SHS" // Check alias
];

console.log("--- Extracting Centre Codes ---");
schools.forEach(name => {
  const feature = geoJson.features.find(f => f.properties.name === name);
  if (feature) {
    const match = feature.properties.description.value.match(/Centre_code<\/td><td>(\d+)<\/td>/);
    console.log(`"${name}": ${match ? match[1] : 'No Code Found'}`);
  } else {
    console.log(`"${name}": Feature Not Found`);
  }
});
