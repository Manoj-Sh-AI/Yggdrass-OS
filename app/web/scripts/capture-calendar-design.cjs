// Read-only captures of the real local Calendar; no records are created or edited.
const { chromium, expect } = require('@playwright/test');
const { readFileSync } = require('node:fs');
const path = require('node:path');
(async () => {
  const runtime = path.resolve(__dirname, '../../api/runtime');
  const session = JSON.parse(readFileSync(path.join(runtime, 'preview-session.json'), 'utf8'));
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage();
    await page.route('https://api.open-meteo.com/**', route => route.abort());
    const response = await page.request.post(session.origin + '/api/backend/auth/login', {
      data: { password: session.password }, headers: { Origin: session.origin },
    });
    if (!response.ok()) throw new Error('Local sign-in failed');
    for (const [size, width, height] of [['desktop', 1344, 896], ['tablet', 820, 1180], ['phone', 390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.goto(session.origin + '/calendar', { waitUntil: 'domcontentloaded' });
      await expect(page.locator('.calendar-surface')).toBeVisible({ timeout: 60000 });
      await expect(page.locator('.planning-time-scroll')).toBeVisible({ timeout: 60000 });
      const dismiss = page.getByRole('button', { name: 'Dismiss location suggestion' });
      if (await dismiss.isVisible()) await dismiss.click();
      for (const view of ['Week', 'Month']) {
        await page.getByRole('tab', { name: view, exact: true }).click();
        await expect(page.locator('.calendar-surface')).toHaveAttribute('data-view', view.toLowerCase());
        if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Calendar overflow at ' + size);
        await page.screenshot({ path: path.join(runtime, `calendar-live-${view.toLowerCase()}-${size}.png`), animations: 'disabled' });
      }
      console.log('Calendar ' + size + ' verified and captured.');
    }
    console.log('Read-only Calendar verification complete.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
