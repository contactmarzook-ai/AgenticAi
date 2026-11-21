// Organizations and roles: a platform admin creates an organization and its admin; that admin
// sees only their own organization and none of the platform pages.
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
  const dlg = page.locator('[role=dialog]');
  const field = (label) => dlg.locator('label', { has: page.locator(`span:text-is("${label}")`) }).locator('input,textarea,select').last();
  const base = process.env.E2E_BASE_URL || 'http://localhost:5173';
  const signIn = async (email, password) => {
    await page.fill('input[type=email]', email);
    await page.fill('input[type=password]', password);
    await page.click('button[type=submit]');
    await page.waitForSelector('text=Sign out');  // the app reopens the last page, so wait for the shell
  };

  await page.goto(base + '/');
  await page.screenshot({ path: S + '/o01-login.png' });
  await signIn('admin@example.com', 'Admin#Passw0rd!');
  check((await page.locator('aside, nav').first().innerText()).includes('Platform admin'), 'sidebar shows the role name');

  await page.click('nav >> text=Users');
  await page.waitForSelector('text=Organizations');
  await page.click('button:has-text("Add organization")');
  await field('Name').fill('Beta Finance');
  await field('Short name').fill('beta-finance');
  await dlg.locator('button:has-text("Save")').click();
  await page.waitForSelector('td:has-text("beta-finance")');
  check(true, 'platform admin creates an organization');

  await page.click('button:has-text("Add user")');
  await field('Email').fill('boss@beta.com');
  await field('Initial password').fill('Boss#Passw0rd!');
  await field('Role').selectOption('org_admin');
  await field('Organization').selectOption({ label: 'Beta Finance' });
  await dlg.locator('button:has-text("Save")').click();
  await page.waitForSelector('text=boss@beta.com');
  const row = await page.locator('tr', { hasText: 'boss@beta.com' }).innerText();
  check(row.includes('Organization admin') && row.includes('Beta Finance'), 'user created in the new organization: ' + row.replace(/\s+/g, ' '));
  await page.screenshot({ path: S + '/o02-users-platform.png', fullPage: true });

  await page.click('text=Sign out');
  await page.waitForSelector('button[type=submit]');
  await signIn('boss@beta.com', 'Boss#Passw0rd!');
  const nav = await page.locator('nav').innerText();
  check(nav.includes('Users') && nav.includes('Audit log') && !nav.includes('Models') && !nav.includes('Settings'),
    'org admin sees organization pages only: ' + nav.replace(/\n/g, ' | '));
  await page.click('nav >> text=Users');
  await page.waitForSelector('text=boss@beta.com');
  const body = await page.locator('main, body').first().innerText();
  check(!body.includes('admin@example.com') && !body.includes('Organizations'), 'org admin sees only their own organization');
  await page.click('button:has-text("Add user")');
  const roles = await field('Role').locator('option').allInnerTexts();
  check(!roles.includes('Platform admin') && roles.includes('Auditor'), 'org admin cannot grant platform admin: ' + roles.join(', '));
  await page.screenshot({ path: S + '/o03-users-org-admin.png' });
  console.log('ERRORS:', errors.length ? errors.join('\n') : 'none');
  await browser.close();
})().catch(async e => { console.error('E2E FAILED:', e.message.split('\n')[0]); try { await global.__page.screenshot({ path: S + '/fail.png' }); } catch {} process.exit(1); });
