const { chromium } = require('playwright');

const FRONTEND_URL = 'http://localhost:3000';
const API_BASE = 'http://localhost:8080/api';
const TIMESTAMP = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
const TEST_EMAIL = `e2e-test-${TIMESTAMP}@example.com`;
const TEST_PASSWORD = 'Testpass1';
const TEST_NAME = 'E2E Test User';

function log(msg) {
  console.log(`[${new Date().toISOString()}] ${msg}`);
}

async function runTests() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 }
  });
  const page = await context.newPage();
  
  const consoleErrors = [];
  
  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
      log(`CONSOLE ERROR: ${msg.text().substring(0, 200)}`);
    }
  });
  
  page.on('response', async response => {
    const url = response.url();
    if (url.includes('/api/') && response.status() >= 500) {
      log(`SERVER ERROR: ${response.status()} ${response.request().method()} ${url}`);
    }
  });

  try {
    // Wait for backend to be ready
    log('Waiting for backend...');
    for (let i = 0; i < 30; i++) {
      try {
        const resp = await page.request.get('http://localhost:8080/');
        if (resp.status() === 404) break; // server is up
      } catch (e) {
        // ignore
      }
      await new Promise(r => setTimeout(r, 1000));
    }
    
    // TEST 1: Homepage
    log('TEST 1: Homepage loads');
    await page.goto(FRONTEND_URL, { waitUntil: 'networkidle', timeout: 30000 });
    
    // Accept cookies if banner exists
    const acceptCookieBtn = page.locator('button:has-text("Accept"), button:has-text("Got it"), button:has-text("OK")').first();
    if (await acceptCookieBtn.count() > 0) {
      await acceptCookieBtn.click();
      await page.waitForTimeout(1000);
    }
    
    log(`  URL: ${page.url()}`);
    log(`  Console errors: ${consoleErrors.length}`);

    // TEST 2: Signup
    log('TEST 2: Signup');
    await page.goto(`${FRONTEND_URL}/auth/signup`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('[placeholder="John Doe"]', { timeout: 15000 });
    
    await page.fill('[placeholder="John Doe"]', TEST_NAME);
    await page.fill('[placeholder="you@company.com"]', TEST_EMAIL);
    await page.fill('[placeholder="Enter your password"]', TEST_PASSWORD);
    await page.fill('[placeholder="Confirm your password"]', TEST_PASSWORD);
    
    const signupStart = Date.now();
    await page.click('button:has-text("Create Account")');
    await page.waitForURL('**/admin**', { timeout: 15000 });
    const signupTime = Date.now() - signupStart;
    
    const postSignupUrl = page.url();
    const token = await page.evaluate(() => localStorage.getItem('token'));
    const user = await page.evaluate(() => localStorage.getItem('user'));
    
    log(`  Signup duration: ${signupTime}ms`);
    log(`  Post-signup URL: ${postSignupUrl}`);
    log(`  Token exists: ${!!token}`);
    log(`  User exists: ${!!user}`);

    // TEST 3: Dashboard
    log('TEST 3: Dashboard');
    await page.waitForLoadState('networkidle', { timeout: 30000 });
    await page.waitForTimeout(3000);
    log(`  Dashboard URL: ${page.url()}`);
    log(`  Dashboard title: ${await page.title()}`);

    // TEST 4: Inventory
    log('TEST 4: Inventory');
    const invStart = Date.now();
    await page.goto(`${FRONTEND_URL}/admin/inventory`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);
    const invTime = Date.now() - invStart;
    log(`  Inventory load: ${invTime}ms`);
    log(`  Inventory URL: ${page.url()}`);

    // TEST 5: Create product
    log('TEST 5: Create Product');
    await page.goto(`${FRONTEND_URL}/admin/inventory`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(2000);
    
    const productStart = Date.now();
    const addBtn = page.locator('button:has-text("Add Product")').first();
    if (await addBtn.count() > 0) {
      await addBtn.click();
      await page.waitForTimeout(2000);
      
      // Screenshot modal
      await page.screenshot({ path: '/tmp/product-modal.png' });
      log('  Screenshot saved: /tmp/product-modal.png');
      
      // Try to find any input in modal
      const inputs = await page.locator('input').all();
      log(`  Inputs found: ${inputs.length}`);
      for (let i = 0; i < Math.min(inputs.length, 5); i++) {
        const placeholder = await inputs[i].getAttribute('placeholder');
        const name = await inputs[i].getAttribute('name');
        log(`    Input ${i}: placeholder="${placeholder}" name="${name}"`);
      }
      
      const productName = `E2E Test Product ${TIMESTAMP}`;
      
      const nameInput = page.locator('input[placeholder="Product Name"]').first();
      if (await nameInput.count() > 0) {
        await nameInput.fill(productName);
        log(`  Filled product name: ${productName}`);
      } else {
        log('  Product Name input not found');
      }
      
      // Skip category select for now - may be custom dropdown
      // const categorySelect = page.locator('select').first();
      // if (await categorySelect.count() > 0) {
      //   await categorySelect.selectOption('Finished Product');
      //   log('  Selected category: Finished Product');
      // }
      
      const priceInput = page.locator('input[placeholder="Price"]').first();
      if (await priceInput.count() > 0) {
        await priceInput.fill('100');
        log('  Filled price: 100');
      }
      
      const submitBtn = page.locator('button:has-text("Add Product")').last();
      if (await submitBtn.count() > 0) {
        await submitBtn.click({ force: true });
        await page.waitForTimeout(3000);
        log('  Clicked submit');
      }
      
      const productTime = Date.now() - productStart;
      log(`  Product creation: ${productTime}ms`);
      
      const found = await page.locator(`text=${productName}`).count();
      log(`  Product found: ${found > 0}`);
    } else {
      log('  Add Product button not found');
      await page.screenshot({ path: '/tmp/inventory-no-modal.png' });
    }

    // TEST 6: Cashier/POS
    log('TEST 6: Cashier/POS');
    const cashierStart = Date.now();
    await page.goto(`${FRONTEND_URL}/dashboard/cashier`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);
    const cashierTime = Date.now() - cashierStart;
    log(`  Cashier page load: ${cashierTime}ms`);
    
    const posTab = await page.locator('button:has-text("POS")').count();
    log(`  POS tab found: ${posTab > 0}`);

    // TEST 7: Add to cart and checkout
    log('TEST 7: Add to cart and checkout');
    if (posTab > 0) {
      await page.locator('button:has-text("POS")').click();
      await page.waitForTimeout(2000);
    }
    
    const productButtons = await page.locator('button:has-text("KSH")').count();
    log(`  Product buttons in POS: ${productButtons}`);
    
    if (productButtons > 0) {
      await page.locator('button:has-text("KSH")').first.click();
      await page.waitForTimeout(1000);
      
      const checkoutBtn = page.locator('button:has-text("Checkout")');
      if (await checkoutBtn.count() > 0) {
        await checkoutBtn.click();
        await page.waitForTimeout(2000);
        
        const cashOption = page.locator('text=Cash').first();
        if (await cashOption.count() > 0) {
          await cashOption.click();
          await page.waitForTimeout(1000);
        }
        
        const completeBtn = page.locator('button:has-text("COMPLETE SALE"), button:has-text("Complete Sale")');
        if (await completeBtn.count() > 0) {
          await completeBtn.click();
          await page.waitForTimeout(3000);
          log('  Sale completed');
        }
      }
    }

    // TEST 8: Logout
    log('TEST 8: Logout');
    await page.goto(`${FRONTEND_URL}/dashboard/cashier`, { waitUntil: 'networkidle', timeout: 30000 });
    
    const logoutBtn = page.locator('button:has-text("Logout")');
    if (await logoutBtn.count() > 0) {
      await logoutBtn.click();
      await page.waitForTimeout(3000);
      log(`  Post-logout URL: ${page.url()}`);
    } else {
      log('  Logout button not found');
    }

    // TEST 9: Protected route blocked
    log('TEST 9: Protected route after logout');
    await page.goto(`${FRONTEND_URL}/admin`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(2000);
    
    const protectedUrl = page.url();
    log(`  Protected route URL: ${protectedUrl}`);
    const isBlocked = protectedUrl.includes('/auth/login');
    log(`  Properly blocked: ${isBlocked}`);

    // TEST 10: Wrong password
    log('TEST 10: Wrong password');
    await page.goto(`${FRONTEND_URL}/auth/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('[placeholder="you@company.com"]', { timeout: 15000 });
    
    await page.fill('[placeholder="you@company.com"]', TEST_EMAIL);
    await page.fill('[placeholder="Enter your password"]', 'Wrongpassword1');
    await page.click('button:has-text("Sign In")');
    await page.waitForTimeout(3000);
    
    const wrongPassUrl = page.url();
    log(`  Wrong password URL: ${wrongPassUrl}`);
    
    const errorShown = await page.locator('.bg-red-50, .text-red-700').count();
    log(`  Error shown: ${errorShown > 0}`);

  } catch (error) {
    log(`ERROR: ${error.message}`);
    console.error(error);
    await page.screenshot({ path: '/tmp/e2e-error.png' });
  } finally {
    await browser.close();
  }
}

runTests().catch(console.error);
