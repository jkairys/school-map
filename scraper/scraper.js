import { chromium } from 'playwright-extra';
import stealthPlugin from 'puppeteer-extra-plugin-stealth';
import fs from 'fs';
import path from 'path';

// Add stealth plugin
chromium.use(stealthPlugin());

const OUTPUT_DIR = path.join(process.cwd(), 'output');
const SCHOOLS_FILE = path.join(process.cwd(), 'schools.json');

if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR);
}

async function scrapeSchool(page, acaraId) {
  console.log(`[${acaraId}] Scraping school...`);

  const outputPath = path.join(OUTPUT_DIR, `${acaraId}.json`);
  if (fs.existsSync(outputPath)) {
    console.log(`[${acaraId}] Already scraped. Skipping.`);
    return true;
  }

  try {
    // 1. Navigate to School Profile
    const profileUrl = `https://myschool.edu.au/school/${acaraId}`;
    await page.goto(profileUrl, { waitUntil: 'networkidle', timeout: 60000 });

    // Handle potential Cloudflare/Turnstile wall
    const wallText = await page.evaluate(() => document.body.innerText.includes('Checking your browser'));
    if (wallText) {
      console.log(`[${acaraId}] Cloudflare wall detected, waiting for challenge to resolve...`);
      await page.waitForTimeout(10000);
    }

    // Extract School Name and Profile Data
    const { schoolName, profileData } = await page.evaluate(() => {
      const getName = () => {
        const header = document.querySelector('.school-name, h1, .cmp-school-header__name');
        return header ? header.innerText.trim() : document.title;
      };

      const getValueByLabel = (labelText) => {
        const elements = Array.from(document.querySelectorAll('*'));
        const labelEl = elements.find(el => el.innerText && el.innerText.trim().toLowerCase().includes(labelText.toLowerCase()) && el.children.length === 0);
        if (labelEl && labelEl.parentElement) {
          return labelEl.parentElement.innerText.trim();
        }
        return null;
      };

      const data = {};

      // ICSEA
      const icseaRaw = getValueByLabel('ICSEA');
      if (icseaRaw) {
        const valMatch = icseaRaw.match(/School ICSEA value(\d+)/i);
        const percMatch = icseaRaw.match(/School ICSEA percentile(\d+)/i);
        data.icsea = valMatch ? valMatch[1] : null;
        data.icseaPercentile = percMatch ? percMatch[1] : null;
      }

      // Enrollment
      const enrolmentsRaw = getValueByLabel('Total enrolments');
      if (enrolmentsRaw) {
        const boysMatch = enrolmentsRaw.match(/Boys(\d+)/i);
        const girlsMatch = enrolmentsRaw.match(/Girls(\d+)/i);
        if (boysMatch && girlsMatch) {
          data.enrolmentsBoys = boysMatch[1];
          data.enrolmentsGirls = girlsMatch[1];
          data.totalEnrolments = (parseInt(boysMatch[1]) + parseInt(girlsMatch[1])).toString();
        } else {
          const totalMatch = enrolmentsRaw.match(/(\d+)/);
          data.totalEnrolments = totalMatch ? totalMatch[1] : null;
        }
      }

      // Demographics
      const indigenousRaw = getValueByLabel('Indigenous');
      if (indigenousRaw) {
        const match = indigenousRaw.match(/(\d+)%/);
        data.indigenousPercent = match ? match[1] : null;
      }

      const lboteRaw = getValueByLabel('Language background other than English');
      if (lboteRaw) {
        const match = lboteRaw.match(/Yes\((\d+)%\)/i);
        data.lbotePercent = match ? match[1] : null;
      }

      return { schoolName: getName(), profileData: data };
    });

    console.log(`[${acaraId}] Success: ${schoolName}`);

    // 2. Navigate to NAPLAN Results
    const naplanUrl = `${profileUrl}/naplan/results`;
    await page.goto(naplanUrl, { waitUntil: 'networkidle', timeout: 60000 });

    // Wait for the results table or specific content to load
    await page.waitForSelector('.naplan-results-container, .cmp-naplan-results, table', { timeout: 30000 }).catch(() => {
      console.log(`[${acaraId}] NAPLAN results container not found.`);
    });

    // Extract NAPLAN results data
    const results = await page.evaluate(() => {
      const data = {};

      const yearSelect = document.querySelector('select[name="year"]');
      if (yearSelect) {
        data.availableYears = Array.from(yearSelect.options).map(opt => opt.value);
        data.latestYear = data.availableYears[0];
      }

      const table = document.querySelector('table');
      if (table) {
        const rows = Array.from(table.querySelectorAll('tr'));
        data.tableData = rows.map(row => {
          const cells = Array.from(row.querySelectorAll('td, th'));
          return cells.map(cell => cell.innerText.trim());
        });
      }

      return data;
    });

    fs.writeFileSync(outputPath, JSON.stringify({ acaraId, schoolName, profileData, results }, null, 2));
    return true;

  } catch (error) {
    console.error(`[${acaraId}] Error:`, error.message);
    await page.screenshot({ path: path.join(OUTPUT_DIR, `error_${acaraId}.png`) }).catch(() => { });
    return false;
  }
}

async function run() {
  const isBatch = process.argv.includes('--batch');
  const singleId = process.argv[2] && !process.argv[2].startsWith('--') ? process.argv[2] : null;

  if (!isBatch && !singleId) {
    console.error('Usage: node scraper.js <acaraId> OR node scraper.js --batch');
    process.exit(1);
  }

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
    viewport: { width: 1280, height: 720 }
  });

  const page = await context.newPage();

  if (isBatch) {
    if (!fs.existsSync(SCHOOLS_FILE)) {
      console.error(`Schools file not found: ${SCHOOLS_FILE}`);
      process.exit(1);
    }
    const schools = JSON.parse(fs.readFileSync(SCHOOLS_FILE, 'utf8'));
    console.log(`Found ${schools.length} schools. Starting batch processing...`);

    for (let i = 0; i < schools.length; i++) {
      const school = schools[i];
      const acaraId = school.ACARAId;

      const success = await scrapeSchool(page, acaraId);

      if (success && i < schools.length - 1) {
        const delay = Math.floor(Math.random() * 5000) + 5000; // 5-10 second delay
        console.log(`Waiting ${delay}ms before next school...`);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  } else {
    await scrapeSchool(page, singleId);
  }

  await browser.close();
  console.log('Finished.');
}

run();
