import { chromium } from 'playwright-extra';
import stealthPlugin from 'puppeteer-extra-plugin-stealth';
import fs from 'fs';
import path from 'path';

// Add stealth plugin
chromium.use(stealthPlugin());

const OUTPUT_DIR = path.join(process.cwd(), 'output');
const SCHOOLS_FILE = path.join(process.cwd(), 'schools.json');
const MAX_RETRIES = 3;

if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR);
}

async function acceptTermsOfUse(page) {
  // Check if we're on the terms of use page
  const isTermsPage = await page.evaluate(() => {
    return document.body.innerText.includes('My School – terms of use') ||
      document.body.innerText.includes('terms of use') &&
      document.body.innerText.includes('Please accept the terms of use');
  });

  if (isTermsPage) {
    console.log('Terms of use page detected, accepting...');

    // Find and check the checkbox by clicking its label
    // The actual input is hidden (opacity: 0), so we must click the label
    const label = await page.$('label.tou-checkbox-inline');
    if (label) {
      await label.click();
    } else {
      // Fallback: try checking with force: true if label is missing (unlikely)
      const checkbox = await page.$('input[type="checkbox"]');
      if (checkbox) {
        await checkbox.check({ force: true });
      }
    }

    // click the Accept button
    // Wait for button to be enabled first
    const acceptButton = await page.waitForSelector('button:has-text("Accept"), input[type="submit"][value*="Accept"], a:has-text("Accept")', { state: 'visible' });

    if (acceptButton) {
      // Ensure it's not disabled (sometimes there's a slight delay after checking)
      await page.waitForFunction(btn => !btn.disabled, acceptButton, { timeout: 5000 }).catch(() => { });

      await acceptButton.click();
      await page.waitForLoadState('networkidle', { timeout: 30000 });
      console.log('Terms accepted successfully.');
      return true;
    } else {
      // Try finding by text content as last resort
      await page.click('text=Accept', { timeout: 5000 }).catch(() => { });
      await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => { });
      return true;
    }
  }
  return false;
}

async function navigateWithTermsHandling(page, url, options = {}) {
  const { timeout = 60000 } = options;

  await page.goto(url, { waitUntil: 'networkidle', timeout });

  // Check and handle terms page after navigation
  const acceptedTerms = await acceptTermsOfUse(page);

  if (acceptedTerms) {
    // If we accepted terms, we may have been redirected. Navigate again.
    await page.goto(url, { waitUntil: 'networkidle', timeout });
  }

  // Final check - if still on terms page, throw error
  const stillOnTerms = await page.evaluate(() => {
    return document.body.innerText.includes('My School – terms of use');
  });

  if (stillOnTerms) {
    throw new Error('Failed to navigate past terms of use page');
  }
}

async function scrapeSchool(page, acaraId) {
  console.log(`[${acaraId}] Scraping school...`);

  const outputPath = path.join(OUTPUT_DIR, `${acaraId}.json`);
  if (fs.existsSync(outputPath)) {
    console.log(`[${acaraId}] Already scraped. Skipping.`);
    return { success: true, skipped: true };
  }

  try {
    // 1. Navigate to School Profile
    const profileUrl = `https://myschool.edu.au/school/${acaraId}`;
    await navigateWithTermsHandling(page, profileUrl);

    // Handle potential Cloudflare/Turnstile wall
    const wallText = await page.evaluate(() => document.body.innerText.includes('Checking your browser'));
    if (wallText) {
      console.log(`[${acaraId}] Cloudflare wall detected, waiting for challenge to resolve...`);
      await page.waitForTimeout(10000);
    }

    // Validate we're on the school page, not an error page or terms page
    const pageValidation = await page.evaluate(() => {
      const bodyText = document.body.innerText;
      const isTermsPage = bodyText.includes('terms of use') && bodyText.includes('Please accept');
      const isNotFoundPage = bodyText.includes('Page not found') || bodyText.includes('404');
      const isErrorPage = bodyText.includes('Something went wrong') || bodyText.includes('Error');
      const hasSchoolContent = document.querySelector('.school-name, .cmp-school-header, h1') !== null;
      return { isTermsPage, isNotFoundPage, isErrorPage, hasSchoolContent };
    });

    if (pageValidation.isTermsPage) {
      throw new Error('Still on terms of use page after navigation');
    }
    if (pageValidation.isNotFoundPage) {
      throw new Error('School page not found (404)');
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
    await navigateWithTermsHandling(page, naplanUrl);

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
    return { success: true, skipped: false };

  } catch (error) {
    console.error(`[${acaraId}] Error:`, error.message);
    await page.screenshot({ path: path.join(OUTPUT_DIR, `error_${acaraId}.png`) }).catch(() => { });
    return { success: false, skipped: false };
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

    // Accept terms of use before starting batch
    console.log('Navigating to site to accept terms of use...');
    try {
      await page.goto('https://myschool.edu.au', { waitUntil: 'networkidle', timeout: 60000 });
      await acceptTermsOfUse(page);
    } catch (e) {
      console.log('Initial terms acceptance navigation failed, will retry per-school:', e.message);
    }

    const failedSchools = [];

    for (let i = 0; i < schools.length; i++) {
      const school = schools[i];
      const acaraId = school.ACARAId;

      let success = false;
      let skipped = false;
      let attempts = 0;

      while (!success && attempts < MAX_RETRIES) {
        attempts++;
        if (attempts > 1) {
          console.log(`[${acaraId}] Retry attempt ${attempts}/${MAX_RETRIES}...`);
          // Wait longer between retries
          await new Promise(resolve => setTimeout(resolve, 10000));
        }

        const result = await scrapeSchool(page, acaraId);
        success = result.success;
        skipped = result.skipped;

        // If failed, check if we need to re-accept terms (session might have expired)
        if (!success && attempts < MAX_RETRIES) {
          console.log(`[${acaraId}] Attempting to refresh session...`);
          try {
            await page.goto('https://myschool.edu.au', { waitUntil: 'networkidle', timeout: 60000 });
            await acceptTermsOfUse(page);
          } catch (e) {
            console.log(`[${acaraId}] Session refresh failed:`, e.message);
          }
        }
      }

      if (!success) {
        failedSchools.push(acaraId);
      }

      if (i < schools.length - 1 && !skipped) {
        const delay = Math.floor(Math.random() * 5000) + 5000; // 5-10 second delay
        console.log(`Waiting ${delay}ms before next school...`);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }

    if (failedSchools.length > 0) {
      console.log(`\n=== Failed schools (${failedSchools.length}): ===`);
      console.log(failedSchools.join(', '));
      fs.writeFileSync(path.join(OUTPUT_DIR, 'failed_schools.json'), JSON.stringify(failedSchools, null, 2));
    }
  } else {
    // Accept terms of use before scraping single school
    console.log('Navigating to site to accept terms of use...');
    try {
      await page.goto('https://myschool.edu.au', { waitUntil: 'networkidle', timeout: 60000 });
      await acceptTermsOfUse(page);
    } catch (e) {
      console.log('Initial terms acceptance failed, will handle during scrape:', e.message);
    }
    await scrapeSchool(page, singleId);
  }

  await browser.close();
  console.log('Finished.');
}

run();
