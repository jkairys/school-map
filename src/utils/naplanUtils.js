
// Utilities for processing NAPLAN data

/**
 * Calculates the state average scores for each Year level and Competency.
 * @param {Object} schoolData - The raw JSON data of schools.
 * @returns {Object} - Map of "Year X": { "Reading": 500, ... }
 */
export const calculateStateAverages = (schoolData) => {
  const sums = {};
  const counts = {};

  Object.values(schoolData).forEach((school) => {
    if (!school.naplan) return;

    const headers = school.naplan[0]; // ["", "Reading", ...]
    const rows = school.naplan.slice(1);

    rows.forEach((row) => {
      const year = row[0]; // "Year 7", "Year 9"
      if (!sums[year]) {
        sums[year] = {};
        counts[year] = {};
      }

      row.slice(1).forEach((val, idx) => {
        const competency = headers[idx + 1];
        const score = parseScore(val);

        if (score !== null) {
          if (!sums[year][competency]) {
            sums[year][competency] = 0;
            counts[year][competency] = 0;
          }
          sums[year][competency] += score;
          counts[year][competency] += 1;
        }
      });
    });
  });

  const averages = {};
  Object.keys(sums).forEach((year) => {
    averages[year] = {};
    Object.keys(sums[year]).forEach((comp) => {
      averages[year][comp] = sums[year][comp] / counts[year][comp];
    });
  });

  return averages;
};

/**
 * Calculates a school's relative performance score for a given competency.
 * Returns the average ratio across all available year levels.
 * 1.0 = Exact State Average. >1.0 = Above, <1.0 = Below.
 * 
 * @param {Object} school - The school object.
 * @param {String} competency - e.g. "Reading", "Numeracy"
 * @param {Object} stateAverages - result from calculateStateAverages
 * @returns {Number|null} - Relative score or null if no data
 */
export const getSchoolRelativeScore = (school, competency, stateAverages) => {
  if (!school.naplan) return null;

  const headers = school.naplan[0];
  const compIdx = headers.indexOf(competency);
  if (compIdx === -1) return null;

  let totalRatio = 0;
  let count = 0;

  school.naplan.slice(1).forEach((row) => {
    const year = row[0];
    const val = row[compIdx]; // adjust index logically? row[0] is year. headers[1] is Reading.
    // headers: ["", "Reading", ...] -> indexOf("Reading") = 1.
    // row: ["Year 7", "500", ...] -> score is at index 1.
    // Access using same index as headers works because row structure matches headers.

    // Wait, row array length should match header array length?
    // header[0] is ""
    // row[0] is Year
    // header[1] is Reading
    // row[1] is score

    const score = parseScore(val);
    if (score !== null && stateAverages[year] && stateAverages[year][competency]) {
      const avg = stateAverages[year][competency];
      totalRatio += score / avg;
      count++;
    }
  });

  if (count === 0) return null;
  return totalRatio / count;
};

const parseScore = (val) => {
  if (!val) return null;
  // Handle simple numbers "500"
  // Handle complex strings if any (though scraper seems to clean most, earlier sample showed just numbers mostly)
  // Just in case: "523\n513-533" -> take 523
  const str = val.toString();
  const match = str.match(/(\d+)/);
  return match ? parseFloat(match[1]) : null;
};
