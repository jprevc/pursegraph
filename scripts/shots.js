// See scripts/shots, which runs this with playwright-core on NODE_PATH.
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const PAGES = {
  login: '/login/', spending: '/spending/', cashflow: '/cashflow/', trends: '/trends/',
  'per-member': '/per-member/', 'money-flow': '/money-flow/', transactions: '/transactions/',
  review: '/review/', import: '/import/', accounts: '/accounts/', categories: '/categories/',
  rules: '/rules/', 'new-rule': '/rules/new/', suggestions: '/suggestions/', members: '/members/',
};
const SIZES = { desk: [1440, 1000], phone: [390, 844] };

const [base, out, ...only] = process.argv.slice(2);
const unknown = only.filter(name => !(name in PAGES));
if (!base || !out || unknown.length) {
  console.error(`usage: scripts/shots BASE_URL OUT_DIR [page...]; pages: ${Object.keys(PAGES).join(' ')}`);
  process.exit(2);
}
const cache = path.join(process.env.HOME, '.cache/ms-playwright');
const chrome = fs.readdirSync(cache).filter(d => /^chromium-\d+$/.test(d))
  .sort((a, b) => a.split('-')[1] - b.split('-')[1]).pop();

(async () => {
  const browser = await chromium.launch({ executablePath: path.join(cache, chrome, 'chrome-linux64/chrome') });
  fs.mkdirSync(out, { recursive: true });
  let count = 0;
  for (const scheme of ['light', 'dark']) for (const [size, [width, height]] of Object.entries(SIZES)) {
    // Reduced motion, so charts are drawn at once rather than mid-entrance.
    const context = await browser.newContext({ viewport: { width, height }, colorScheme: scheme, reducedMotion: 'reduce' });
    const page = await context.newPage();
    for (const [name, url] of Object.entries(PAGES)) {
      if (only.length && !only.includes(name)) continue;
      await page.goto(base + url, { waitUntil: 'networkidle' });
      if (name !== 'login' && new URL(page.url()).pathname === '/login/') {
        await page.fill('input[name=username]', 'ana');
        await page.fill('input[name=password]', 'demo-pass-123');
        await Promise.all([page.waitForURL(u => u.pathname !== '/login/'), page.click('button[type=submit]')]);
        await page.goto(base + url, { waitUntil: 'networkidle' });
      }
      if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) {
        console.log(`sideways scroll: ${name} ${scheme} ${size}`);
      }
      await page.screenshot({ path: path.join(out, `${name}-${scheme}-${size}.png`) });
      count++;
    }
    await context.close();
  }
  await browser.close();
  console.log(`${count} shots in ${out}`);
})().catch(e => { console.error(e); process.exit(1); });
