// End-to-end check of the running app in a real browser (Chromium via Playwright).
// Start the app first:  streamlit run app.py --server.port 8765
// Then:                 node tests/browser_check.js [output-folder]
// It expects an EMPTY database at the start (use a fresh BALANSE_LOCAL_DB file).
const { chromium } = require('playwright');
const path = require('path');
const BASE = process.env.BALANSE_URL || 'http://localhost:8765';
const OUT = process.argv[2] || '.';
const ROOT = path.resolve(__dirname, '..');
const R = [];
const ok = (name, pass, info) => { R.push((pass ? 'PASS ' : 'FAIL ') + name + (info ? '  [' + info + ']' : '')); };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1360, height: 900 } });
  const consoleErrors = [];
  page.on('pageerror', e => consoleErrors.push(String(e)));
  const settle = async () => {
    await page.waitForLoadState('networkidle').catch(() => {});
    await page.waitForFunction(() => !document.querySelector('[data-testid="stStatusWidget"]') &&
      !document.querySelector('[data-testid="stSpinner"]'), null, { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(700);
  };
  const open = async (p) => { const t = Date.now(); await page.goto(BASE + '/' + p); await page.waitForSelector('h1', { timeout: 20000 }); await settle(); return (Date.now() - t) / 1000; };
  const noError = async () => (await page.locator('[data-testid="stException"]').count()) === 0;
  const text = async () => (await page.locator('[data-testid="stMain"]').innerText()).toLowerCase();   // text-transform makes some headings upper case
  const shot = async (name) => page.screenshot({ path: path.join(OUT, name + '.png'), fullPage: true });

  // 1. empty start
  await open('');
  ok('empty dashboard explains what to do', (await text()).includes('no products yet') && await noError());

  // 2. load demonstration data
  await open('data-input');
  await page.getByRole('tab', { name: 'Demonstration data' }).click();
  await page.getByRole('button', { name: 'Load demonstration data' }).click();
  await settle();
  ok('demonstration data loads and is labelled', (await text()).includes('demonstration data: not real business records') && await noError());

  // 3. every page opens without an exception, within 10 seconds
  const pages = [['', 'Dashboard'], ['inventory', 'Inventory'], ['stock-alerts', 'Stock Alerts'], ['reorder', 'Reorder Recommendations'],
    ['sales-history', 'Sales History'], ['product', 'Product Details'], ['data-input', 'Data Input'], ['price-market', 'Price Market'], ['settings', 'Settings']];
  for (const [url, title] of pages) {
    const seconds = await open(url);
    const heading = await page.locator('h1').first().innerText();
    ok('page ' + (url || 'dashboard'), heading.toLowerCase().includes(title.toLowerCase()) || url === 'product' && await noError() && seconds < 10, heading + ', ' + seconds.toFixed(1) + 's');
    await shot('page-' + (url || 'dashboard'));
  }

  // 4. dashboard numbers
  await open('');
  let body = await text();
  const cards = await page.locator('.bal-key .n').allInnerTexts();
  ok('dashboard status counts (stockout, understock, no sales, overstock, optimal = 2/3/1/2/6) and 14 products', cards.join(',') === '2,3,1,2,6' && body.includes('14 products'), cards.join(','));
  ok('dashboard shows Needs review with reasons and actions', body.includes('needs review') && body.includes('suggested: review the purchase order') && body.includes('delivery takes'));
  ok('dashboard says the decision stays with the user', body.includes('balanse supports your decision'));

  // 5. inventory: search and status filter
  await open('inventory');
  await page.getByRole('textbox', { name: 'Search' }).fill('ginger');
  await page.keyboard.press('Enter'); await settle();
  ok('inventory search', (await text()).includes('1 of 14 products'));
  await page.getByRole('textbox', { name: 'Search' }).fill(''); await page.keyboard.press('Enter'); await settle();

  // 6. stock alerts: mark as reviewed
  await open('stock-alerts');
  body = await text();
  ok('8 alerts to review, most urgent first', body.includes('to review (8)') && body.indexOf('stockout') < body.indexOf('understock'));
  await page.getByRole('button', { name: 'Mark as reviewed' }).first().click(); await settle();
  body = await text();
  ok('mark as reviewed moves the alert, status unchanged', body.includes('to review (7)') && body.includes('reviewed (1)') && body.includes('its status and stock are unchanged'));
  await open('');
  ok('reviewing did not change the status counts', (await page.locator('.bal-key .n').allInnerTexts()).join(',') === '2,3,1,2,6');

  // 7. reorder page
  await open('reorder');
  body = await text();
  ok('reorder page shows the formula and the no-orders note', body.includes('suggested quantity = target stock − current stock') && body.includes('units already on order are not counted') && body.includes('does not place orders'));

  // 8. product details
  await open('product');
  body = await text();
  ok('product details: why, action, projection, excess, history, coverage', ['why this status', 'suggested action', 'projection (an estimate)', 'excess stock (an estimate)', 'stock and sales history', 'coverage'].every(s => body.includes(s)) && (await page.locator('.js-plotly-plot').count()) >= 1);

  // 9. settings: invalid is refused, valid is saved and recalculates
  await open('settings');
  const target = page.getByLabel('Target days of supply', { exact: true });
  await target.fill('99'); await target.press('Tab');
  await page.getByRole('button', { name: 'Save settings' }).click(); await settle();
  ok('invalid settings are refused with a reason', (await text()).includes('cannot be more than maximum days of supply'));
  await open('settings');
  const period = page.getByLabel('Sales period (days)', { exact: true });
  await period.fill('14'); await period.press('Tab');
  await page.getByRole('button', { name: 'Save settings' }).click(); await settle();
  ok('valid settings are saved', (await text()).includes('settings saved'));
  await open('');
  const after = (await page.locator('.bal-key .n').allInnerTexts()).join(',');
  ok('changing the sales period recalculates (Sports Drink becomes Understock: 2 / 4 / 1 / 2 / 5)', after === '2,4,1,2,5', after);
  await open('settings');
  await page.getByLabel('Sales period (days)', { exact: true }).fill('30'); await page.getByLabel('Sales period (days)', { exact: true }).press('Tab');
  await page.getByRole('button', { name: 'Save settings' }).click(); await settle();

  // 10. price market stays a placeholder
  await open('price-market');
  body = await text();
  ok('price market is a placeholder only', body.includes('coming soon') && body.includes('under development') && body.includes('specialist or economist') && (await page.locator('input, textarea').count()) === 0);

  // 11. real entries are blocked while demo data is loaded; then clear it
  await open('data-input');
  ok('own entries are kept apart from demonstration data', (await text()).includes('clear the demonstration data') && await page.getByRole('button', { name: 'Save product' }).isDisabled());
  await page.getByRole('tab', { name: 'Demonstration data' }).click();
  await page.getByRole('button', { name: 'Clear demonstration data' }).click(); await settle();
  ok('demonstration data can be cleared', (await text()).includes('demonstration data cleared'));

  // 12. manual product entry: errors, then success
  await open('data-input');
  await page.getByLabel('Product name', { exact: true }).fill('Test Juice 1 L');
  await page.getByLabel('Product category', { exact: true }).fill('Beverages');
  await page.getByLabel('Current stock quantity', { exact: true }).fill('-5');
  await page.getByLabel('Unit cost').fill('50');
  await page.getByLabel('Replenishment lead time (days)', { exact: true }).fill('4');
  await page.getByRole('button', { name: 'Save product' }).click(); await settle();
  ok('negative stock is refused', (await text()).includes('current stock cannot be negative'));
  await page.getByLabel('Current stock quantity', { exact: true }).fill('40');
  await page.getByRole('button', { name: 'Save product' }).click(); await settle();
  ok('manual product is saved', (await text()).includes("'test juice 1 l' saved"));
  await page.getByRole('button', { name: 'Save product' }).click(); await settle();   // the form is empty again after a save
  ok('missing fields are refused', (await text()).includes('product name is required') && (await text()).includes('current stock is required'));

  // 13. record a sale
  await page.getByRole('tab', { name: 'Record a sale' }).click();
  await page.getByLabel('Quantity sold', { exact: true }).fill('8');
  await page.getByRole('button', { name: 'Save sale' }).click(); await settle();
  const saleMessage = (await text()).includes('sale saved: 8 units');
  await page.getByRole('tab', { name: 'Record a sale' }).click(); await settle();
  ok('sale saved and stock reduced (40 - 8 = 32)', saleMessage && (await text()).includes('current stock: 32 units'));

  // 14. CSV imports with preview
  const importCsv = async (kind, file) => {
    await open('data-input');
    await page.getByRole('tab', { name: 'Import CSV' }).click();
    await page.getByText(kind, { exact: true }).click(); await settle();
    await page.locator('input[type=file]').setInputFiles(path.join(ROOT, 'sample_data', file)); await settle();
    return text();
  };
  body = await importCsv('Products', 'products_with_errors.csv');
  ok('CSV with errors: preview lists rejected rows and reasons', body.includes('1 valid row(s), 5 rejected row(s)') && body.includes('will not be saved'));
  body = await importCsv('Products', 'products.csv');
  ok('products CSV preview', body.includes('8 valid row(s), 0 rejected row(s)'));
  await page.getByRole('button', { name: 'Save 8 valid row(s)' }).click(); await settle();
  ok('products CSV saved', (await text()).includes('8 products row(s) saved'));
  body = await importCsv('Sales records', 'sales.csv');
  const salesCount = (body.match(/(\d+) valid row\(s\), 0 rejected/) || [])[1];
  ok('sales CSV preview', !!salesCount, salesCount + ' rows');
  await page.getByRole('button', { name: new RegExp('Save ' + salesCount) }).click(); await settle();
  ok('sales CSV saved', (await text()).includes('sales records row(s) saved'));
  body = await importCsv('Sales records', 'sales.csv');
  ok('importing the same sales file twice is caught', body.includes('0 valid row(s), ' + salesCount + ' rejected row(s)') && body.includes('no valid rows to save'));
  body = await importCsv('Stock records', 'stock_records.csv');
  const stockCount = (body.match(/(\d+) valid row\(s\), 0 rejected/) || [])[1];
  await page.getByRole('button', { name: new RegExp('Save ' + stockCount) }).click(); await settle();
  ok('stock records CSV saved', (await text()).includes('stock records row(s) saved'), stockCount + ' rows');

  // 15. results from imported data
  await open('');
  const imported = (await page.locator('[data-testid="stMain"]').innerText()).toLowerCase();
  ok('imported data is analyzed (9 products)', imported.includes('9 products') && await noError(), '');
  await shot('after-import-dashboard');

  // 16. phone width
  await page.setViewportSize({ width: 390, height: 800 });
  await open('');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  ok('phone width: no sideways scrolling', overflow <= 0 && await noError(), 'overflow ' + overflow + 'px');
  await shot('phone-dashboard');

  ok('no browser script errors', consoleErrors.length === 0, consoleErrors.join(' ; ').slice(0, 300));
  console.log(R.join('\n'));
  console.log('\n' + R.filter(r => r.startsWith('PASS')).length + ' passed, ' + R.filter(r => r.startsWith('FAIL')).length + ' failed');
  await browser.close();
})().catch(e => { console.log(R.join('\n')); console.log('STOPPED: ' + String(e.message).split('\n')[0]); process.exit(1); });
