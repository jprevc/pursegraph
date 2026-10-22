// See scripts/shots, which runs this with scripts/playwright.
const { SIZES, launch, open, logIn, shoot } = require('browser');

const PAGES = {
  login: '/login/', spending: '/spending/', cashflow: '/cashflow/', trends: '/trends/',
  'per-member': '/per-member/', 'money-flow': '/money-flow/', transactions: '/transactions/',
  review: '/review/', import: '/import/', accounts: '/accounts/', categories: '/categories/',
  rules: '/rules/', 'new-rule': '/rules/new/', suggestions: '/suggestions/', members: '/members/',
};
const [base, out, ...only] = process.argv.slice(2);
const unknown = only.filter(name => !(name in PAGES));
if (!base || !out || unknown.length) {
  console.error(`usage: scripts/shots BASE_URL OUT_DIR [page...]; pages: ${Object.keys(PAGES).join(' ')}`);
  process.exit(2);
}

(async () => {
  const browser = await launch();
  let count = 0;
  for (const scheme of ['light', 'dark']) for (const size of Object.keys(SIZES)) {
    // Logged out, so the login page is shot as a visitor sees it; the first other page logs in.
    const page = await open(browser, base, { scheme, size, user: null });
    for (const [name, url] of Object.entries(PAGES)) {
      if (only.length && !only.includes(name)) continue;
      await page.goto(base + url, { waitUntil: 'networkidle' });
      if (name !== 'login' && new URL(page.url()).pathname === '/login/') {
        await logIn(page, base);
        await page.goto(base + url, { waitUntil: 'networkidle' });
      }
      await shoot(page, out, `${name}-${scheme}-${size}`);
      count++;
    }
    await page.context().close();
  }
  await browser.close();
  console.log(`${count} shots in ${out}`);
})().catch(e => { console.error(e); process.exit(1); });
