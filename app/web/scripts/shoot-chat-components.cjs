// Screenshot every chat component in the gallery (/chat/components) at desktop and phone
// width, light and dark. Needs the synthetic local preview (app/api/scripts/local_preview.py
// with YGGDRAS_GALLERY=1); reads its generated test password from app/api/runtime.
const { chromium } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const runtime = path.resolve(__dirname, '../../api/runtime');
const out = path.join(runtime, 'screenshots', 'chat-components');
const { origin, password } = JSON.parse(fs.readFileSync(path.join(runtime, 'preview-session.json'), 'utf8'));
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const shots = [];
  try {
    for (const [label, viewport] of [['desktop', { width: 1280, height: 900 }], ['phone', { width: 390, height: 844 }]]) {
      for (const scheme of ['light', 'dark']) {
        const context = await browser.newContext({ viewport, colorScheme: scheme, reducedMotion: 'reduce' });
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', (e) => errors.push(String(e)));
        await page.goto(`${origin}/login`);
        await page.fill('input[type=password]', password);
        await page.keyboard.press('Enter');
        await page.waitForURL((u) => !u.pathname.startsWith('/login'));
        await page.goto(`${origin}/chat/components`);
        await page.waitForSelector('[data-gallery]');
        await page.waitForTimeout(800); // xterm draws after its lazy import
        const wide = await page.evaluate(() => {
          if (document.documentElement.scrollWidth <= window.innerWidth) return '';
          const el = [...document.querySelectorAll('body *')].find((e) => e.getBoundingClientRect().right > window.innerWidth + 1);
          return el ? `${el.tagName.toLowerCase()}.${String(el.className).slice(0, 60)}` : 'unknown';
        });
        if (wide) errors.push(`horizontal scroll at ${label}: ${wide}`);
        for (const section of await page.$$('[data-gallery]')) {
          const name = (await section.getAttribute('data-gallery')).toLowerCase().replace(/[^a-z0-9]+/g, '-');
          const file = path.join(out, `${name}.${label}.${scheme}.png`);
          await section.screenshot({ path: file });
          shots.push(path.relative(runtime, file));
        }
        if (errors.length) throw new Error(`${label}/${scheme}: ${errors.join('; ')}`);
        await context.close();
      }
    }
    // Real pages (Phases C, D, E): reported, not failed, so a page's older errors show up
    // in the log instead of hiding the screenshots.
    const pages = path.join(runtime, 'screenshots', 'pages');
    fs.mkdirSync(pages, { recursive: true });
    for (const [label, viewport] of [['desktop', { width: 1440, height: 900 }], ['phone', { width: 390, height: 844 }]]) {
      const context = await browser.newContext({ viewport, colorScheme: 'dark', reducedMotion: 'reduce' });
      const page = await context.newPage();
      const problems = [];
      page.on('pageerror', (e) => problems.push(String(e).slice(0, 160)));
      await page.goto(`${origin}/login`);
      await page.fill('input[type=password]', password);
      await page.keyboard.press('Enter');
      await page.waitForURL((u) => !u.pathname.startsWith('/login'));
      for (const route of ['/notes', '/calendar']) {
        await page.goto(origin + route);
        await page.waitForTimeout(2500);
        await page.screenshot({ path: path.join(pages, `${route.slice(1)}.${label}.png`) });
        shots.push(`pages/${route.slice(1)}.${label}.png`);
      }
      await page.keyboard.press('Control+j');
      await page.waitForTimeout(800);
      const open = await page.evaluate(() => document.querySelector('aside[aria-label="Side chat"]')?.getAttribute('aria-hidden') === 'false');
      const chip = await page.locator('aside[aria-label="Side chat"]').getByLabel("Don't share this page").count();
      await page.screenshot({ path: path.join(pages, `side-chat.${label}.png`) });
      shots.push(`pages/side-chat.${label}.png`);
      const wide = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      console.log(`${label}: side chat open=${open} chip=${chip > 0} horizontal-scroll=${wide} page-errors=${problems.length ? problems.join(' | ') : 0}`);
      await context.close();
    }
  } finally {
    await browser.close();
  }
  console.log(`${shots.length} screenshots in ${path.relative(process.cwd(), out)}`);
})().catch((e) => { console.error(e); process.exit(1); });
