
import fs from 'fs';

const schoolsToCheck = [
  "North Lakes State College",
  "Capalaba State College",
  "Whites Hill State College",
  "Kelvin Grove State College",
  "Earnshaw State College",
  "Ormeau Woods State High School",
  "Ormeau Woods SHS"
];

const naplanPath = '../../apps/frontend/public/data/naplan_data.json';
const schoolsPath = 'schools.json';

console.log("--- Checking naplan_data.json ---");
try {
  const naplan = JSON.parse(fs.readFileSync(naplanPath, 'utf8'));
  schoolsToCheck.forEach(name => {
    if (naplan[name]) {
      console.log(`Key: "${name}" -> Name: "${naplan[name].schoolName}", ACARA: ${naplan[name].acaraId}`);
    } else {
      console.log(`Key: "${name}" -> NOT FOUND`);
    }
  });
} catch (e) {
  console.log("Error reading naplan_data.json", e.message);
}

console.log("\n--- Checking scraper/schools.json ---");
try {
  const schools = JSON.parse(fs.readFileSync(schoolsPath, 'utf8'));
  schoolsToCheck.forEach(name => {
    // Try exact match or match containing
    const found = schools.filter(s => s.SchoolName === name || s.SchoolName.includes(name));
    if (found.length > 0) {
      found.forEach(s => {
        console.log(`Found "${s.SchoolName}": ACARA: ${s.ACARAId}, StateID: ${s.StateProvinceId}`);
      });
    } else {
      console.log(`"${name}" -> NOT FOUND in schools.json`);
    }
  });
} catch (e) {
  console.log("Error reading schools.json", e.message);
}
