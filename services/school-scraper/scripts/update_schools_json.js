
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const schoolsPath = path.join(__dirname, '../schools.json');

const schools = JSON.parse(fs.readFileSync(schoolsPath, 'utf8'));

const updates = [
  { name: "North Lakes State College", acaraId: "47574", stateId: "000002324" },
  { name: "Whites Hill State College", acaraId: "47580", stateId: "000002410" },
  { name: "Ormeau Woods State High School", acaraId: "47644", stateId: "000006136" },
  { name: "Capalaba State College", acaraId: "47716", stateId: "000005534" },
  { name: "Kelvin Grove State College", acaraId: "47570", stateId: "000002409" },
  { name: "Earnshaw State College", acaraId: "4930", stateId: "000005180" }
];

let updatedCount = 0;
let addedCount = 0;

updates.forEach(update => {
  const existingIndex = schools.findIndex(s => s.SchoolName === update.name);

  if (existingIndex !== -1) {
    // Update existing
    console.log(`Updating ${update.name}...`);
    schools[existingIndex].ACARAId = update.acaraId;
    schools[existingIndex].StateProvinceId = update.stateId;
    updatedCount++;
  } else {
    // Add new (create a minimal plausible entry based on others)
    console.log(`Adding ${update.name}...`);
    schools.push({
      RefId: `manually-added-${update.acaraId}`,
      LocalId: update.acaraId,
      StateProvinceId: update.stateId,
      CommonwealthId: update.acaraId,
      ACARAId: update.acaraId,
      SchoolName: update.name,
      SchoolType: "Combined", // Assumption, can be fixed if needed but mainly needs ID
      OperationalStatus: "O",
      Campus: {
        ParentSchoolId: update.acaraId,
        SchoolCampusId: update.acaraId,
        CampusType: "Main"
      }
    });
    addedCount++;
  }
});

fs.writeFileSync(schoolsPath, JSON.stringify(schools, null, 2));
console.log(`Done. Updated ${updatedCount}, Added ${addedCount}.`);
