// Read-only checks of the local app. Never creates work or changes a Brain note.
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
    const login = await page.request.post(session.origin + '/api/backend/auth/login', {
      data: { password: session.password }, headers: { Origin: session.origin },
    });
    if (!login.ok()) throw new Error('Local sign-in verification failed.');
    const capability = await page.request.get(session.origin + '/api/backend/application/connections/capabilities');
    if (!capability.ok()) throw new Error('Linked-work capability unavailable.');
    const settings = await capability.json();
    if (!settings.linked_work || settings.automatic_interpretation) throw new Error('Unexpected workflow capability state.');
    const catalogue = await page.request.get(session.origin + '/api/backend/notes/search?q=');
    if (!catalogue.ok()) throw new Error('Real Notes catalogue unavailable.');
    const notes = (await catalogue.json()).notes;
    if (!notes.length) throw new Error('No real note available for read verification.');
    const slug = notes[0].slug;
    const context = await page.request.get(session.origin + '/api/backend/application/connections/notes/' + encodeURIComponent(slug));
    if (!context.ok()) throw new Error('Live note-context read failed.');
    for (const [size, width, height] of [['desktop', 1344, 896], ['phone', 390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.goto(session.origin + '/notes?note=' + encodeURIComponent(slug), { waitUntil: 'domcontentloaded' });
      await expect(page.locator('.bn-editor')).toBeVisible({ timeout: 90000 });
      const toggle = page.getByRole('button', { name: 'Toggle note context' });
      if (await toggle.getAttribute('aria-expanded') !== 'true') await toggle.click();
      const work = page.getByRole('region', { name: 'Linked work', exact: true });
      await expect(work.getByRole('button', { name: 'Create task', exact: true })).toBeVisible({ timeout: 30000 });
      await expect(work.getByRole('button', { name: 'Create event', exact: true })).toBeVisible();
      if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Notes overflow at ' + size);
      await page.screenshot({ path: path.join(runtime, 'note-work-live-' + size + '.png'), animations: 'disabled' });
      console.log('Live Notes linked-work controls verified: ' + size + '.');
    }
    const graph = await page.request.get(session.origin + '/api/backend/graph/status');
    if (!graph.ok()) throw new Error('Existing Brain graph read failed.');
    const status = await graph.json();
    console.log('Read-only verification: ' + notes.length + ' real notes; Brain viewer ' + status.nodes + ' nodes and ' + status.links + ' links.');
    console.log('No work created and no Brain notes changed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
