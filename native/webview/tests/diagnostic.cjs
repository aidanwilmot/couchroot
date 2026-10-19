// Uses the repository's existing Playwright dependency; never contacts a TV.
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(path.join(__dirname, '../diagnostic/index.html')).href);
    await page.waitForFunction(() => document.querySelector('#features').textContent.includes('Two animation frames'));
    const selected = () => page.evaluate(() => document.activeElement.textContent);
    assert.equal(await selected(), 'One');
    await page.keyboard.press('ArrowRight');
    assert.equal(await selected(), 'Two');
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#input').textContent(), 'Activated Two');
    assert.equal(await page.title(), 'diag input Activated Two'); // Host log channel.
    await page.keyboard.press('Escape');
    assert.equal(await selected(), 'One');
    await page.keyboard.press('ArrowLeft');
    assert.equal(await selected(), 'Three');
    assert.match(await page.locator('#features').textContent(), /Tizen application API: false/);
    await page.setViewportSize({ width: 960, height: 540 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    if (process.env.WEBVIEW_SCREENSHOT) {
      await page.setViewportSize({ width: 1920, height: 1080 });
      await page.screenshot({ path: process.env.WEBVIEW_SCREENSHOT, fullPage: true });
    }
    assert.deepEqual(errors, []);
    console.log('Diagnostic page: local loading, feature report, arrows/OK/Back, narrow viewport passed');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
