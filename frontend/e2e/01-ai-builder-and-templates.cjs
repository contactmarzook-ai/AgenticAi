const { chromium } = require('playwright');
const S = process.argv[2];
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  global.__page = page;
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  page.on('dialog', d => d.accept());
  const shot = n => page.screenshot({ path: `${S}/${n}.png` });
  const dlg = page.locator('[role=dialog]');

  await page.goto('' + (process.env.E2E_BASE_URL || 'http://localhost:5173') + '/');
  await page.fill('input[type=email]', 'admin@example.com');
  await page.fill('input[type=password]', 'Admin#Passw0rd!');
  await page.click('button[type=submit]');
  await page.waitForSelector('text=What would you like to automate?');
  await shot('a01-home');

  // 1. AI draft
  await page.fill('textarea', 'When a support ticket comes in, decide if it is urgent and alert the team');
  await page.click('button:has-text("Create with AI")');
  await page.waitForSelector('.react-flow__node:has-text("How urgent is it?")');
  await shot('a02-ai-draft');
  await page.click('button:has-text("Test")');
  await dlg.locator('textarea').first().fill('Our checkout is down, customers cannot pay. Fix ASAP!');
  await dlg.locator('button:has-text("Run test")').click();
  await dlg.getByText('Succeeded', { exact: true }).waitFor();
  await dlg.locator('button:has-text("Show on canvas")').click();
  await page.click('.react-flow__node:has-text("How urgent is it?")');
  await page.waitForSelector('text=Last test');
  await shot('a03-tested');
  await page.click('button:has-text("Publish")');
  await page.waitForSelector('text=is now live');
  await page.click('button:has-text("Back")');

  // 2. Run from the list
  await page.waitForSelector('text=Your workflows');
  await page.locator('button:has-text("Run")').first().click();
  await dlg.locator('textarea').first().fill('Just a question about my plan, no rush.');
  await dlg.locator('button:has-text("Run now")').click();
  await dlg.locator('text=Step by step').waitFor();
  await shot('a04-run-result');
  await page.keyboard.press('Escape');

  // 3. Template
  await page.click('button:has-text("Start from a template")');
  await dlg.locator('text=Invoice check & approval').waitFor();
  await shot('a05-templates');
  await dlg.locator('button:has-text("Invoice check & approval")').click();
  await page.waitForSelector('.react-flow__node:has-text("Read the invoice")');
  await page.click('button:has-text("Test")');
  await dlg.locator('textarea').first().fill('Vendor: Acme Corp\nInvoice number: INV-778\nTotal amount: 25000\nDue date: 2026-12-31');
  await dlg.locator('input[type=number]').fill('10000');
  await dlg.locator('button:has-text("Run test")').click();
  await dlg.getByText('Succeeded', { exact: true }).waitFor();
  await shot('a06-template-test');
  await dlg.locator('button:has-text("Show on canvas")').click();
  await page.click('button:has-text("Back")');

  // 4. Blank build with a form field and Insert data
  await page.click('button:has-text("Start blank")');
  await page.click('.react-flow__node:has-text("Start")');
  await page.click('button:has-text("Add field")');
  await page.locator('input[placeholder="Label"]').fill('Customer name');
  await page.click('.react-flow__node:has-text("Start")');
  await page.locator('button:has-text("Ask AI")').first().click();
  await page.waitForSelector('text=Instruction *');
  await page.locator('label:has-text("Instruction") textarea').fill('Write a one-line welcome for ');
  await page.locator('label:has-text("Instruction") button:has-text("Insert data")').click();
  await page.locator('button:has-text("customer_name")').click();
  const instr = await page.locator('label:has-text("Instruction") textarea').inputValue();
  if (!instr.includes('{{input.customer_name}}')) throw new Error('variable not inserted: ' + instr);
  await page.click('button:has-text("Test")');
  await dlg.locator('input').first().fill('Ravi');
  await dlg.locator('button:has-text("Run test")').click();
  await dlg.getByText('Succeeded', { exact: true }).waitFor();
  const out = await dlg.locator('pre').first().innerText();
  if (!out.includes('Ravi')) throw new Error('variable not resolved: ' + out);
  await dlg.locator('button:has-text("Show on canvas")').click();
  await shot('a07-blank-build');
  await page.click('button:has-text("Back")');

  // 5. Connections and admin settings
  await page.click('nav >> text=Connections');
  await page.click('button:has-text("New connection")');
  await dlg.locator('select').first().selectOption('slack_webhook');
  await dlg.locator('label:has-text("Name") input').fill('Ops Slack');
  await dlg.locator('input[type=password]').fill('https://hooks.slack.com/services/T000/B000/XXXX');
  await dlg.locator('button:has-text("Save connection")').click();
  await page.waitForSelector('text=Ops Slack');
  await shot('a08-connections');
  await page.click('nav >> text=Settings');
  await page.locator('label:has-text("HTTP request") input[type=checkbox]').uncheck();
  await page.fill('textarea', 'api.example.com');
  await page.click('button:has-text("Save settings")');
  await page.waitForSelector('text=Settings saved');
  await shot('a09-settings');
  await page.click('nav >> text=History');
  await page.waitForTimeout(500);
  await shot('a10-history');
  console.log('ERRORS:', errors.length ? errors.join('\n') : 'none');
  await browser.close();
})().catch(async e => { console.error('E2E FAILED:', e.message.split('\n')[0]); try { await global.__page.screenshot({ path: S + '/fail.png' }); } catch {} process.exit(1); });
