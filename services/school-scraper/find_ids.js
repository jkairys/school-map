
import { chromium } from 'playwright-extra';
import stealthPlugin from 'puppeteer-extra-plugin-stealth';
import UserAgent from 'user-agents';

chromium.use(stealthPlugin());

const schoolsToFind = [
  "North Lakes State College",
  "Whites Hill State College",
  "Capalaba State College",
  "Kelvin Grove State College",
  "Earnshaw State College",
  "Ormeau Woods State High School"
];

async function acceptTermsOfUse(page) {
  // Simplified terms acceptance from scraper.js
  const isTermsPage = await page.evaluate(() => {
    return document.body.innerText.includes('My School – terms of use');
  });

  if (isTermsPage) {
    console.log('Accepting terms...');
    const label = await page.$('label.tou-checkbox-inline');
    if (label) await label.click();

    const acceptButton = await page.waitForSelector('button:has-text("Accept"), input[type="submit"][value*="Accept"]', { timeout: 5000 }).catch(() => { });
    if (acceptButton) {
      await acceptButton.click();
      await page.waitForLoadState('networkidle');
    }
    return true;
  }
  return false;
}

async function findId(page, schoolName) {
  console.log(`Searching for: ${schoolName}`);
  try {
    await page.goto('https://myschool.edu.au', { waitUntil: 'networkidle' });
    await acceptTermsOfUse(page);

    // Type in search box
    await page.fill('#search-school', schoolName);
    await page.waitForTimeout(1000); // Wait for dropdown

    // Wait for results
    // The dropdown usually appears. We pick the first one.
    // Selector might be .ui-menu-item or similar.
    // Let's press Enter to search if dropdown doesn't facilitate easy click, 
    // or wait for the autocomplete list.

    // Strategy: Press Enter and wait for navigation or search results page
    await page.keyboard.press('Enter');
    await page.waitForLoadState('networkidle');

    // If we are on a list page, find the link matches the name
    // If we are on the profile page, we are done.

    const url = page.url();
    if (url.includes('/school/')) {
      const match = url.match(/\/school\/(\d+)/);
      if (match) {
        console.log(`FOUND ${schoolName}: ${match[1]}`);
        return match[1];
      }
    }

    // If we are on search results page (likely if multiple matches)
    // Look for a link text that strongly matches
    // Selector for results: .search-result-title a ?
    // We'll dump the first link that looks like a school profile
    const firstLink = await page.$('a[href*="/school/"]');
    if (firstLink) {
      const href = await firstLink.getAttribute('href');
      const match = href.match(/\/school\/(\d+)/);
      if (match) {
        console.log(`FOUND ${schoolName}: ${match[1]} (from list)`);
        return match[1];
      }
    }

    console.log(`NOT FOUND: ${schoolName}`);
    return null;

  } catch (e) {
    console.log(`ERROR ${schoolName}: ${e.message}`);
    return null;
  }
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent: new UserAgent({ deviceCategory: 'desktop' }).toString()
  });
  const page = await context.newPage();

  for (const school of schoolsToFind) {
    await findId(page, school);
    await page.waitForTimeout(2000);
  }

  await browser.close();
}

run();
