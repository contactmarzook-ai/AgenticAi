// Agent contracts: build input/output schemas in the editor, save, test with valid and invalid
// input, see validation results, and confirm the contract persists.
const { chromium } = require('playwright');
const S = process.argv[2];
const check = (cond, msg) => { if (!cond) throw new Error('CHECK FAILED: ' + msg); console.log('ok -', msg); };
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  global.__page = page;
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !m.text().includes('401') && !m.text().includes('422')) errors.push('console: ' + m.text()); });
  const dlg = page.locator('[role=dialog]');
  const field = (label) => dlg.locator('label', { has: page.locator(`span:text-is("${label}")`) }).locator('input,textarea,select').last();
  await page.goto((process.env.E2E_BASE_URL || 'http://localhost:5173') + '/');
  await page.fill('input[type=email]', 'admin@example.com');
  await page.fill('input[type=password]', 'Admin#Passw0rd!');
  await page.click('button[type=submit]');
  await page.waitForSelector('text=Sign out');

  await page.click('nav >> text=Agents');
  await page.click('text=New agent');
  await field('Name').fill('Order checker');
  await field('Who can use it').selectOption('public');
  await field('Capabilities').fill('order.lookup');
  await field('Tags').fill('sales');
  await dlg.locator('summary:has-text("Input and output contract")').click();

  // Input: message -> order_id (whole number, required) + optional note
  const inp = dlg.locator('[data-contract=input]');
  const nameBox = (box, i) => box.locator('input.font-mono').nth(i);
  await nameBox(inp, 0).fill('order_id');
  await nameBox(inp, 0).blur();
  await inp.locator('select[aria-label=Type]').first().selectOption('integer');
  await inp.locator('button:has-text("Add field")').last().click();
  await nameBox(inp, 1).fill('note');
  await nameBox(inp, 1).blur();
  await inp.locator('text=✓ Valid contract').waitFor();
  check(true, 'input contract built in the field editor and accepted by the server');

  // Output: answer -> status (enum) + total (number, required)
  const out = dlg.locator('[data-contract=output]');
  await nameBox(out, 0).fill('status');
  await nameBox(out, 0).blur();
  await out.locator('input[placeholder^="Allowed values"]').first().fill('open, shipped');
  await out.locator('input[placeholder^="Allowed values"]').first().blur();
  await out.locator('button:has-text("Add field")').last().click();
  await nameBox(out, 1).fill('total');
  await nameBox(out, 1).blur();
  await out.locator('select[aria-label=Type]').nth(1).selectOption('number');
  await out.locator('label:has-text("Req.") input').nth(1).check();
  await out.locator('text=✓ Valid contract').waitFor();

  // A broken schema typed as JSON is reported by the server.
  await out.locator('button:has-text("JSON Schema")').click();
  const json = await out.locator('textarea[aria-label="JSON Schema"]').inputValue();
  check(json.includes('"enum"') && json.includes('"open"') && json.includes('"total"'), 'the JSON view shows the same schema');
  await out.locator('textarea[aria-label="JSON Schema"]').fill('{"type": "object", "properties": {"x": {"type": "array"}}}');
  await out.locator('text=an array must say what its items are').waitFor();
  check(true, 'invalid schema reported while editing');
  await out.locator('textarea[aria-label="JSON Schema"]').fill(json);
  await out.locator('text=✓ Valid contract').waitFor();
  await page.screenshot({ path: S + '/c01-contract-editor.png', fullPage: true });

  await dlg.locator('button:has-text("Save")').click();
  await page.waitForSelector('h3:has-text("Order checker")');
  const card = page.locator('div.rounded-lg', { has: page.locator('h3:has-text("Order checker")') });
  const cardText = await card.innerText();
  check(cardText.includes('order.lookup') && cardText.includes('#sales') && cardText.includes('order_id, note → status, total'), 'card shows capabilities, tags and contract: ' + cardText.replace(/\s+/g, ' '));

  // Test: invalid input first
  await card.locator('button:has-text("Try")').click();
  await dlg.locator('button:has-text("Check input")').click();
  await dlg.locator('text=Input validation: failed').waitFor();
  check((await dlg.innerText()).includes("'order_id' is required"), 'missing required input reported');
  await dlg.locator('button:has-text("Edit as JSON")').click();
  await dlg.locator('textarea[aria-label="Input JSON"]').fill('{"order_id": "abc"}');
  await dlg.locator('button:has-text("Run")').click();
  await dlg.locator('text=Input validation: failed').waitFor();
  check((await dlg.innerText()).includes('must be an integer') && !(await dlg.innerText()).includes('Execution'), 'wrong type rejected before running');

  // Then valid input through the generated form
  await dlg.locator('button:has-text("Use the form")').click();
  await dlg.locator('[data-field=order_id] input').fill('42');
  await dlg.locator('button:has-text("Run")').click();
  await dlg.locator('text=Output validation: passed').waitFor();
  const res = await dlg.innerText();
  check(res.includes('Input validation: passed') && res.includes('succeeded') && /\d+\.\d\d s/.test(res), 'execution status and duration shown');
  check(res.includes('open') && res.includes('1.5'), 'structured output shown');
  await page.screenshot({ path: S + '/c02-test-modal.png', fullPage: true });
  await page.keyboard.press('Escape');

  // Persistence: reopen the editor
  await card.locator('button:has-text("Edit")').click();
  const inJson = dlg.locator('[data-contract=input]');
  await inJson.locator('button:has-text("JSON Schema")').click();
  const saved = await inJson.locator('textarea[aria-label="JSON Schema"]').inputValue();
  check(saved.includes('"order_id"') && saved.includes('"integer"') && saved.includes('"additionalProperties": false'), 'contract persisted and normalised');
  console.log('ERRORS:', errors.length ? errors.join('\n') : 'none');
  await browser.close();
})().catch(async e => { console.error('E2E FAILED:', e.message.split('\n')[0]); try { await global.__page.screenshot({ path: S + '/fail.png' }); } catch {} process.exit(1); });
