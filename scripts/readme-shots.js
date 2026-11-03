// See scripts/readme-shots, which runs this with scripts/playwright.
const { launch, open, shoot } = require('browser');

// Cash flow over the last 12 complete months, so it draws a year of bars rather than one month's.
const now = new Date();
const lastMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
const last12 = `last12-${lastMonth.getFullYear()}-${String(lastMonth.getMonth() + 1).padStart(2, '0')}`;
const PAGES = {
  spending: '/spending/', cashflow: `/cashflow/?period=${last12}`, 'money-flow': '/money-flow/', review: '/review/',
};
const [base, out] = process.argv.slice(2);

(async () => {
  const browser = await launch();
  for (const scheme of ['light', 'dark']) {
    const page = await open(browser, base, { scheme, size: 'desk' });
    for (const [name, url] of Object.entries(PAGES)) {
      await page.goto(base + url, { waitUntil: 'networkidle' });
      await shoot(page, out, `${name}-${scheme}`);
    }
    await page.context().close();
  }
  await browser.close();
  console.log(`${Object.keys(PAGES).length * 2} shots in ${out}`);
})().catch(e => { console.error(e); process.exit(1); });
