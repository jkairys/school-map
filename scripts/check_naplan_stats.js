
import fs from 'fs';

const data = JSON.parse(fs.readFileSync('./public/data/naplan_data.json', 'utf8'));
const competencies = ['Reading', 'Writing', 'Spelling', 'Grammar', 'Numeracy'];

const scoresByComp = {};

Object.values(data).forEach(school => {
  if (!school.naplan) return;

  // Parse naplan table
  const headerRow = school.naplan[0]; // ["", "Reading", ...]
  const yearRows = school.naplan.slice(1);

  yearRows.forEach(row => {
    const year = row[0]; // "Year 7" or "Year 9"
    row.slice(1).forEach((scoreStr, idx) => {
      const comp = headerRow[idx + 1];
      if (!scoresByComp[comp]) scoresByComp[comp] = [];

      // Clean score (handle ranges or newlines if any, though sample looked cleanish mostly)
      // Sample: "530", or "523\n513 - 533"
      let score = parseFloat(scoreStr);
      if (isNaN(score)) {
        // Try taking the first number found
        const match = scoreStr.toString().match(/(\d+)/);
        if (match) score = parseFloat(match[1]);
      }

      if (!isNaN(score)) {
        scoresByComp[comp].push(score);
      }
    });
  });
});

console.log("--- Distribution Stats ---");
for (const comp of competencies) {
  const scores = scoresByComp[comp];
  if (!scores || scores.length === 0) continue;

  // simple avg
  const sum = scores.reduce((a, b) => a + b, 0);
  const avg = sum / scores.length;

  // standard dev
  const squareDiffs = scores.map(value => Math.pow(value - avg, 2));
  const avgSquareDiff = squareDiffs.reduce((a, b) => a + b, 0) / squareDiffs.length;
  const stdDev = Math.sqrt(avgSquareDiff);

  console.log(`${comp}: Avg=${avg.toFixed(1)}, StdDev=${stdDev.toFixed(1)}`);
  // % variance
  console.log(`   1 StdDev Range: ${(avg - stdDev).toFixed(1)} - ${(avg + stdDev).toFixed(1)}`);
  console.log(`   Spread Ratio: ${((avg - stdDev) / avg).toFixed(2)} - ${((avg + stdDev) / avg).toFixed(2)}`);
}
