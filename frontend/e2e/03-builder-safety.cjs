const { chromium } = require('playwright');
const S = process.argv[2];
const check = (cond, msg) => { if (!cond) throw new Error('CHECK FAILED: ' + msg); console.log('ok -', msg); };
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  global.__page = page;
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('dialog', d => d.accept());
  const dlg = page.locator('[role=dialog]');
  await page.goto('' + (process.env.E2E_BASE_URL || 'http://localhost:5173') + '/');
  await page.fill('input[type=email]', 'admin@example.com');
  await page.fill('input[type=password]', 'Admin#Passw0rd!');
  await page.click('button[type=submit]');
  await page.waitForSelector('text=What would you like to automate?');
  await page.click('button:has-text("Start blank")');
  await page.waitForSelector('.react-flow__node');
  await page.locator('button:has-text("Translate")').first().click();
  await page.click('button:has-text("Save")');
  await page.waitForSelector('text=Saved');
  // H1: Backspace inside the Test dialog must not delete the selected step
  await page.click('.react-flow__node:has-text("Translate")');
  await page.click('button:has-text("Test")');
  await dlg.locator('h2').click();
  await page.keyboard.press('Backspace');
  await page.keyboard.press('Escape');
  check(await page.locator('.react-flow__node:has-text("Translate")').count() === 1, 'Backspace inside a dialog does not delete the selected step');
  // H2/H3: switch paths
  await page.click('.react-flow__node:has-text("Translate")');
  await page.locator('button:has-text("Switch")').first().click();
  await page.locator('button:has-text("Ask AI")').first().click();
  await page.click('.react-flow__node:has-text("Route")');
  const edgesBefore = await page.locator('.react-flow__edge').count();
  await page.locator('input[value="option 1"]').fill('urgent');
  await page.waitForTimeout(300);
  check(await page.locator('.react-flow__edge').count() === edgesBefore, `renaming a path keeps its connection drawn (${edgesBefore})`);
  await page.locator('input[value="option 2"]').fill('urgent');
  check(await page.locator('text=Each path needs a different name').count() === 1, 'duplicate path name is refused with a message');
  check(await page.locator('input[value="option 2"]').count() === 1, 'duplicate name was not applied');
  await page.locator('input[value="option 2"]').fill('default');
  check(await page.locator("text='default' is reserved").count() === 1, "'default' is refused");
  // M1: clicking Workflows in the sidebar leaves the builder (after confirming)
  await page.click('nav >> text=Workflows');
  await page.waitForSelector('text=Your workflows');
  check(true, 'sidebar Workflows leaves the builder');
  // M3: unsaved drafts are cleared on sign-out
  const left = await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith('agentos.unsaved.')).length);
  check(left === 0, 'leaving deliberately leaves no local draft behind');
  console.log('ERRORS:', errors.length ? errors.join('\n') : 'none');
  await browser.close();
})().catch(async e => { console.error('E2E FAILED:', e.message.split('\n')[0]); try { await global.__page.screenshot({ path: S + '/fail.png' }); } catch {} process.exit(1); });
