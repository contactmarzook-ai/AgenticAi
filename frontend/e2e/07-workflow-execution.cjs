// Workflow execution in the builder: live validation, background test runs followed on the canvas,
// node logs, execution history, cancelling a slow run, failure details, re-run, versions.
const { chromium } = require('playwright');
const S = process.argv[2];
const check = (cond, msg) => { if (!cond) throw new Error('CHECK FAILED: ' + msg); console.log('ok -', msg); };
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  global.__page = page;
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !m.text().includes('401')) errors.push('console: ' + m.text()); });
  page.on('dialog', d => d.accept());
  const shot = n => page.screenshot({ path: `${S}/${n}.png` });
  const dlg = page.locator('[role=dialog]');
  const panel = page.locator('[data-testid=validation-panel]');
  const status = page.locator('[data-testid=run-status]');
  const node = label => page.locator(`.react-flow__node:has-text("${label}")`);
  const runStatusOf = label => node(label).locator('[data-run-status]').getAttribute('data-run-status');
  const startTest = async () => {
    await page.locator('button:has-text("Test")').first().click();
    await dlg.locator('button:has-text("Run test")').click();
    await dlg.waitFor({ state: 'detached' });
  };

  await page.goto('' + (process.env.E2E_BASE_URL || 'http://localhost:5173') + '/');
  await page.fill('input[type=email]', 'admin@example.com');
  await page.fill('input[type=password]', 'Admin#Passw0rd!');
  await page.click('button[type=submit]');
  await page.waitForSelector('text=What would you like to automate?');

  // 1. Live validation: a blank workflow is fine; an empty Calculate step is a problem until filled in.
  await page.click('button:has-text("Start blank")');
  await page.waitForSelector('.react-flow__node');
  await page.locator('[data-testid=validation-panel][data-errors="0"]').waitFor();
  check((await panel.innerText()).includes('No problems'), 'blank workflow validates without problems');
  await page.locator('button:has-text("Calculate")').first().click();
  await page.locator('[data-testid=validation-panel]:not([data-errors="0"])').waitFor();
  check((await node('Calculate').locator('[data-problems]').getAttribute('data-problems')) !== '0', 'step with a problem is marked on the canvas');
  await panel.locator('button').first().click();
  const problem = panel.locator('li button', { hasText: 'Formula' });
  check(await problem.count() === 1, 'problem list names the missing Formula: ' + (await panel.innerText()).replace(/\n/g, ' | '));
  await page.click('.react-flow__pane', { position: { x: 30, y: 30 } });
  await problem.click();
  await page.locator('label:has-text("Formula") input').waitFor();
  check(true, 'clicking a problem selects its step');
  await shot('e01-validation-problem');
  await page.locator('label:has-text("Formula") input').fill('6 * 7');
  await page.locator('[data-testid=validation-panel][data-errors="0"]').waitFor();
  check(await node('Calculate').locator('[data-problems]').count() === 0, 'problem clears once the formula is filled in');
  check((await page.locator('[data-testid=step-outputs]').innerText()).includes('result'), 'settings pane lists what the step outputs');
  await page.locator('summary:has-text("If this step fails")').click();
  await page.locator('label:has-text("Retry times") select').selectOption('2');
  check(await page.locator('label:has-text("Wait between retries") select').count() === 1 && await page.locator('label:has-text("Time limit") input').count() === 1, 'retry backoff and time limit settings shown');
  await page.locator('label:has-text("Retry times") select').selectOption('0');
  await page.locator('input[maxlength="200"]').first().fill('Execution demo');
  await page.click('button:has-text("Save")');
  await page.waitForSelector('text=Saved');

  // 2. Background test run followed on the canvas
  await startTest();
  await page.locator('[data-testid=run-panel]').waitFor();
  await page.locator('[data-testid=run-status][data-status=succeeded]').waitFor({ timeout: 20000 });
  await page.locator('.react-flow__node [data-run-status=success]').nth(2).waitFor();
  check(await page.locator('.react-flow__node [data-run-status=success]').count() === 3, 'every step shows success on the canvas');
  check((await page.locator('[data-testid=run-panel]').innerText()).includes('42'), 'run result shown in the run panel');
  await shot('e02-test-succeeded');

  // 3. Node logs
  await node('Calculate').click();
  const nodeRun = page.locator('[data-testid=node-run]');
  await nodeRun.waitFor();
  const nodeText = await nodeRun.innerText();
  check(nodeText.includes('done') && nodeText.includes('Output') && nodeText.includes('42'), 'node details show status and output');
  check(nodeText.includes('Logs'), 'node details show logs: ' + nodeText.replace(/\n/g, ' | ').slice(0, 200));
  await shot('e03-node-logs');

  // 4. Execution history
  await page.click('[role=tab]:has-text("History")');
  const history = page.locator('[data-testid=run-history]');
  await history.locator('li').first().waitFor();
  const firstRun = await history.locator('li').first().innerText();
  check(firstRun.includes('succeeded') && firstRun.includes('Test') && firstRun.includes('v1'), 'run listed in the history: ' + firstRun.replace(/\n/g, ' | '));
  await shot('e04-history');
  await page.locator('button:has-text("Back to editing")').click();
  check(await page.locator('.react-flow__node [data-run-status]').count() === 0, 'Back to editing clears the canvas overlay');
  await history.locator('li button').first().click();
  await page.locator('[data-testid=run-panel]').waitFor();
  await page.locator('.react-flow__node [data-run-status=success]').nth(2).waitFor();
  check(true, 'opening a run from history shows it on the canvas');
  await page.locator('button:has-text("Back to editing")').click();

  // 5. Slow run, cancelled
  await node('Calculate').click();
  await page.locator('button:has-text("Wait")').first().click();
  await page.locator('label:has-text("Seconds *") input').fill('4');
  await page.click('button:has-text("Save")');
  await page.waitForSelector('text=Saved');
  await startTest();
  await page.locator('.react-flow__node [data-run-status=running]').waitFor({ timeout: 10000 });
  check(await runStatusOf('Wait') === 'running', 'slow step shows as running');
  await shot('e05-running');
  await page.click('[data-testid=cancel-run]');
  await page.locator('[data-testid=run-status][data-status=cancelled]').waitFor({ timeout: 20000 });
  check(['cancelled', 'skipped', 'pending'].includes(await runStatusOf('Finish')), 'steps after the cancel did not run: ' + await runStatusOf('Finish'));
  check(await page.locator('[data-testid=cancel-run]').count() === 0, 'Cancel button gone once the run stopped');
  await shot('e06-cancelled');
  await page.locator('button:has-text("Back to editing")').click();

  // 6. Failing step: failure details, failed node marked, re-run
  await node('Wait').click();
  await page.locator('label:has-text("Seconds *") input').fill('0');
  await node('Calculate').click();
  await page.locator('label:has-text("Formula") input').fill('1/0');
  await page.locator('summary:has-text("If this step fails")').click();
  await page.locator('label:has-text("Retry times") select').selectOption('1');
  await page.click('button:has-text("Save")');
  await page.waitForSelector('text=Saved');
  await startTest();
  await page.locator('[data-testid=run-status][data-status=failed]').waitFor({ timeout: 20000 });
  check(await runStatusOf('Calculate') === 'failed', 'failed step marked on the canvas');
  const failText = await page.locator('[data-testid=run-panel]').innerText();
  check(failText.includes('The run failed at “Calculate”'), 'failure details name the failed step: ' + failText.replace(/\n/g, ' | ').slice(0, 200));
  await shot('e07-failed');
  await page.click('button:has-text("Show the failed step")');
  await nodeRun.waitFor();
  check((await nodeRun.getAttribute('data-run-status')) === 'failed', 'failed step details open');
  const failedNode = await nodeRun.innerText();
  check(failedNode.includes('2 attempts') && failedNode.includes('attempt 1 failed'), 'retry attempts and log lines shown: ' + failedNode.replace(/\n/g, ' | ').slice(0, 300));
  check((await node('Calculate').innerText()).includes('×2'), 'attempt count shown on the canvas');
  await shot('e07b-failed-node-logs');
  await page.click('[role=tab]:has-text("Run")');
  const before = await status.locator('..').innerText();
  await page.locator('[data-testid=run-panel] button:has-text("Re-run")').click();
  await page.waitForFunction(b => { const el = document.querySelector('[data-testid=run-status]'); return el && el.parentElement.innerText !== b && el.dataset.status === 'failed'; }, before, { timeout: 20000 });
  check(true, 'Re-run starts a new run (fails again)');
  await shot('e08-rerun');

  // 7. Versions: publish, read-only state, run a published version
  await page.click('button:has-text("Publish")');
  await page.waitForSelector('text=is now live');
  await page.locator('[data-testid=published-banner]').waitFor();
  check(true, 'published version shown as read-only');
  await page.click('[role=tab]:has-text("Versions")');
  const versions = page.locator('[data-testid=versions-panel]');
  await versions.locator('li[data-version="1"]:has-text("live")').waitFor();
  check((await versions.innerText()).includes('failed'), 'versions list shows run counts');
  await shot('e09a-versions-panel');
  await versions.locator('button:has-text("Run v1")').click();
  await dlg.locator('button:has-text("Run this version")').click();
  await page.locator('[data-testid=run-panel][data-status=failed]:has-text("API")').waitFor({ timeout: 20000 });
  check(true, 'published version run started from Versions and shown');
  await shot('e09-versions');

  console.log('ERRORS:', errors.length ? errors.join('\n') : 'none');
  check(!errors.length, 'no browser errors');
  await browser.close();
})().catch(async e => { console.error('E2E FAILED:', e.message.split('\n')[0]); try { await global.__page.screenshot({ path: S + '/fail.png' }); } catch {} process.exit(1); });
