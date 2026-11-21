const { chromium } = require('playwright');
const S = process.argv[2];
const check = (cond, msg) => { if (!cond) throw new Error('CHECK FAILED: ' + msg); console.log('ok -', msg); };
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  global.__page = page;
  const errors = [];
  const dialogs = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !m.text().includes('401')) errors.push('console: ' + m.text()); });
  page.on('dialog', d => { dialogs.push(d.message()); d.accept(); });
  const shot = n => page.screenshot({ path: `${S}/${n}.png` });
  const dlg = page.locator('[role=dialog]');
  const nodeCount = () => page.locator('.react-flow__node').count();

  await page.goto('' + (process.env.E2E_BASE_URL || 'http://localhost:5173') + '/');
  await page.fill('input[type=email]', 'admin@example.com');
  await page.fill('input[type=password]', 'Admin#Passw0rd!');
  await page.click('button[type=submit]');
  await page.waitForSelector('text=What would you like to automate?');

  // Blank automation: add a step with nothing selected -> goes before Finish, connected
  await page.click('button:has-text("Start blank")');
  await page.waitForSelector('.react-flow__node');
  await page.locator('aside, div').locator('button:has-text("Compose text")').first().click();
  check(await page.locator('.react-flow__edge').count() === 2, 'step added with nothing selected is connected Start -> step -> Finish');
  // Start cannot be deleted with the keyboard
  await page.click('.react-flow__node:has-text("Start")');
  await page.keyboard.press('Delete');
  check(await page.locator('.react-flow__node:has-text("START")').count() === 1, 'Delete key does not remove Start');
  // Form field + reference, then rename field -> reference follows
  await page.click('button:has-text("Add field")');
  await page.locator('input[placeholder="Label"]').fill('Message');
  await page.click('.react-flow__node:has-text("Compose text")');
  await page.locator('label:has-text("Text") textarea').fill('Got {{input.message}}');
  await page.click('.react-flow__node:has-text("Start")');
  await page.locator('input[placeholder="Label"]').fill('Customer note');
  await page.click('.react-flow__node:has-text("Compose text")');
  const t = await page.locator('label:has-text("Text") textarea').inputValue();
  check(t === 'Got {{input.customer_note}}', 'renaming a form field updates references: ' + t);
  // Undo
  const before = await nodeCount();
  await page.locator('button:has-text("Translate")').first().click();
  check(await nodeCount() === before + 1, 'step added');
  await page.click('.react-flow__pane', { position: { x: 50, y: 50 } });
  await page.keyboard.press('Control+z');
  check(await nodeCount() === before, 'Ctrl+Z undoes adding a step');
  // Switch: add, connect a path, rename it -> still valid
  await page.click('.react-flow__node:has-text("Compose text")');
  await page.locator('button:has-text("Switch")').first().click();
  await page.locator('label:has-text("Route by this value") input').fill('{{input.customer_note}}');
  await page.locator('button:has-text("Ask AI")').first().click(); // goes on first free path
  await page.locator('label:has-text("Instruction") textarea').fill('hello');
  await page.click('.react-flow__node:has-text("Route")');
  await page.locator('input[value="option 1"]').fill('sales');
  await page.click('button:has-text("Save")');
  await page.waitForSelector('text=Saved');
  await shot('b01-builder');
  // test then check result
  await page.click('button:has-text("Test")');
  await dlg.locator('input').first().fill('sales');
  await dlg.locator('button:has-text("Run test")').click();
  await dlg.getByText('Succeeded', { exact: true }).waitFor();
  await dlg.locator('button:has-text("Show on canvas")').click();
  // publish: the renamed path must not break validation
  await page.click('button:has-text("Publish")');
  await page.waitForSelector('text=is now live');
  check(true, 'renamed Switch path publishes without errors');

  // How it starts: public form link + schedule with picker
  await page.click('button:has-text("How it starts")');
  await dlg.locator('button:has-text("Form link")').click();
  await dlg.locator('label:has-text("Show the workflow") input').check();
  await dlg.locator('button:has-text("Add")').click();
  const link = await dlg.locator('code').first().innerText();
  check(link.includes('/#/f/'), 'form link shown: ' + link);
  await dlg.locator('button:has-text("Schedule")').click();
  await dlg.locator('select').first().selectOption('weekdays');
  await dlg.locator('label:has-text("Customer note") input').fill('sales');
  await dlg.locator('button:has-text("Add")').click();
  await dlg.locator('text=Weekdays at').waitFor();
  await shot('b02-how-it-starts');
  await page.keyboard.press('Escape');

  // unsaved guard on navigation
  await page.click('.react-flow__pane', { position: { x: 30, y: 30 } });
  await page.locator('label:has-text("Description") textarea').fill('changed');
  await page.click('nav >> text=History');
  check(dialogs.some(d => d.includes('unsaved')), 'leaving with unsaved changes asks first');
  await page.click('nav >> text=Workflows');
  await page.waitForSelector('text=Your workflows');

  // Public form, signed out in a fresh context
  const ctx2 = await browser.newContext();
  const anon = await ctx2.newPage();
  await anon.goto(link.replace(/^https?:\/\/[^/]+/, '' + (process.env.E2E_BASE_URL || 'http://localhost:5173') + ''));
  await anon.waitForSelector('text=Submit');
  await anon.locator('input').first().fill('sales');
  await anon.click('button:has-text("Submit")');
  await anon.waitForSelector('text=Submit another response');
  await anon.screenshot({ path: `${S}/b03-public-form.png` });
  check(true, 'public form submitted without signing in');
  await ctx2.close();

  // list actions: duplicate, history filter, turn off/on, delete
  await page.reload();
  await page.waitForSelector('text=Your workflows');
  await page.locator('button[aria-label="Duplicate"]').first().click();
  await page.waitForSelector('text=Copy of');
  await page.locator('button[aria-label="History"]').first().click();
  await page.waitForSelector('text=Only “');
  await shot('b04-history-filtered');
  check(true, 'History opens filtered to one automation');
  await page.click('nav >> text=Workflows');
  await page.locator('button:has-text("Edit")').last().click();
  await page.waitForSelector('button:has-text("Turn off")');
  await page.click('button:has-text("Turn off")');
  await page.waitForSelector('text=Turned off');
  await page.click('button:has-text("Back")');
  await page.waitForSelector('button:has-text("Turn on")');
  check(true, 'turned-off automation stays in the list with Turn on');
  await page.click('button:has-text("Turn on")');
  await page.waitForSelector('text=is live again');
  const rowsBefore = await page.locator('button[aria-label="Delete"]').count();
  await page.locator('button[aria-label="Delete"]').first().click();
  await page.waitForTimeout(800);
  check(await page.locator('button[aria-label="Delete"]').count() === rowsBefore - 1, 'automation deleted from the list');
  await shot('b05-list');
  console.log('ERRORS:', errors.length ? errors.join('\n') : 'none');
  await browser.close();
})().catch(async e => { console.error('E2E FAILED:', e.message.split('\n')[0]); try { await global.__page.screenshot({ path: S + '/fail.png' }); } catch {} process.exit(1); });
