// The demo app in headless Chromium, for scripts/shots.js and for scratchpad scripts that check a
// change by hand (open a panel, press keys, shoot a state). Run either with scripts/playwright,
// which puts playwright-core and this file on NODE_PATH:
//
//   const { launch, open, shoot } = require('browser');
//   const browser = await launch();
//   const page = await open(browser, 'http://127.0.0.1:8109', { scheme: 'dark', size: 'phone' });
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const SIZES = { desk: [1440, 1000], phone: [390, 844] };
const PASSWORD = 'demo-pass-123';  // seed_demo's

// The newest Chromium Playwright has cached.
function launch() {
  const cache = path.join(process.env.HOME, '.cache/ms-playwright');
  const chrome = fs.readdirSync(cache).filter(d => /^chromium-\d+$/.test(d))
    .sort((a, b) => a.split('-')[1] - b.split('-')[1]).pop();
  return chromium.launch({ executablePath: path.join(cache, chrome, 'chrome-linux64/chrome') });
}

// A page of its own at SIZE in SCHEME, logged in as USER (ana is the admin) unless USER is null.
async function open(browser, base, { scheme = 'light', size = 'desk', user = 'ana' } = {}) {
  const [width, height] = SIZES[size];
  // Reduced motion, so charts are drawn at once rather than mid-entrance.
  const context = await browser.newContext({ viewport: { width, height }, colorScheme: scheme, reducedMotion: 'reduce' });
  const page = await context.newPage();
  if (user) await logIn(page, base, user);
  return page;
}

async function logIn(page, base, user = 'ana') {
  await page.goto(base + '/login/', { waitUntil: 'networkidle' });
  await page.fill('input[name=username]', user);
  await page.fill('input[name=password]', PASSWORD);
  await Promise.all([page.waitForURL(u => u.pathname !== '/login/'), page.click('button[type=submit]')]);
}

const scrollsSideways = page => page.evaluate(() => document.documentElement.scrollWidth > innerWidth);

// Shoots the viewport as DIR/NAME.png, saying so if the page scrolls sideways.
async function shoot(page, dir, name) {
  if (await scrollsSideways(page)) console.log(`sideways scroll: ${name}`);
  fs.mkdirSync(dir, { recursive: true });
  await page.screenshot({ path: path.join(dir, `${name}.png`) });
}

module.exports = { SIZES, launch, open, logIn, shoot };
