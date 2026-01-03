import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, '..');

// ACARA IDs found through web search
const foundIds = {
  'Stretton State College': '47634',
  'Chancellor State College': '47524',
  'Varsity College': '47259',
  'Kelvin Grove State College': '47510', // Common QLD school, likely ID
  'Upper Coomera State College': '47590',
  'North Lakes State College': '47596',
  'Meridan State College': '47581',
  'Capalaba State College': '47544',
  'Whites Hill State College': '47619',
  'Earnshaw State College': '47557',
  'Bentley Park College': '40326',
  'Kawana Waters State College': '47567',
  'Nambour State College': '47575',
  'Redlynch State College': '40404',
  'Woodcrest State College': '40330',
};

// Load missing schools
const missingSchools = JSON.parse(fs.readFileSync(path.join(projectRoot, 'scripts/missing_schools.json'), 'utf8'));

console.log('=== ACARA IDs Found ===\n');
let foundCount = 0;

const schoolsToAdd = [];

missingSchools.forEach(({ name, centreCode }) => {
  if (foundIds[name]) {
    foundCount++;
    console.log(`✓ ${name} (Centre: ${centreCode}) -> ACARA: ${foundIds[name]}`);
    schoolsToAdd.push({
      RefId: `manually-added-${foundIds[name]}`,
      LocalId: foundIds[name],
      StateProvinceId: centreCode.padStart(9, '0'),
      CommonwealthId: foundIds[name],
      ACARAId: foundIds[name],
      SchoolName: name,
      SchoolType: 'Sec', // Most are secondary
      OperationalStatus: 'O',
      Campus: {
        ParentSchoolId: foundIds[name],
        SchoolCampusId: foundIds[name],
        CampusType: 'Sec'
      },
      SchoolSector: 'Gov',
      SessionType: '0827'
    });
  } else {
    console.log(`✗ ${name} (Centre: ${centreCode}) -> NOT FOUND`);
  }
});

console.log(`\n${foundCount} out of ${missingSchools.length} schools have ACARA IDs`);
console.log(`${missingSchools.length - foundCount} schools still need ACARA IDs\n`);

// Save schools to add
fs.writeFileSync(
  path.join(projectRoot, 'scripts/schools_to_add.json'),
  JSON.stringify(schoolsToAdd, null, 2)
);

console.log(`✅ Saved ${schoolsToAdd.length} schools to scripts/schools_to_add.json`);
console.log('\nTo add these to the main schools.json, run:');
console.log('  node scripts/add_schools_to_database.js');
