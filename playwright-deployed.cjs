const { chromium } = require('playwright');

const FRONTEND_URL = 'https://posifine11.netlify.app';
const API_BASE = 'https://posifine22.onrender.com/api';
const TIMESTAMP = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
const TEST_EMAIL = `e2e-deploy-${TIMESTAMP}@example.com`;
const TEST_PASSWORD = 'Testpass1';
const TEST_NAME = 'E2E Deploy Test';

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
  const networkLog = [];
  
  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
      log(`CONSOLE ERROR: ${msg.text().substring(0, 300)}`);
    }
  });
  
  page.on('response', async response => {
    const url = response.url();
    const status = response.status();
    if (status >= 400 || url.includes('/api/')) {
      networkLog.push({ url, status, method: response.request().method() });
      if (status >= 400) {
        log(`NETWORK ERROR: ${status} ${response.request().method()} ${url}`);
      }
    }
  });

  try {
    // STEP 1: Open deployed POS
    log('STEP 1: Open deployed POS');
    const start1 = Date.now();
    await page.goto(FRONTEND_URL, { waitUntil: 'networkidle', timeout: 30000 });
    const time1 = Date.now() - start1;
    log(`  URL: ${page.url()}`);
    log(`  Title: ${await page.title()}`);
    log(`  Load time: ${time1}ms`);
    log(`  Console errors: ${consoleErrors.length}`);
    await page.screenshot({ path: '/tmp/step1-homepage.png' });
    log('  Screenshot: /tmp/step1-homepage.png');

    // STEP 2: Open authentication page
    log('STEP 2: Open authentication page');
    await page.goto(`${FRONTEND_URL}/auth/signup`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('[placeholder="John Doe"]', { timeout: 15000 });
    log(`  Auth page URL: ${page.url()}`);
    log(`  Auth page title: ${await page.title()}`);
    
    // Count network requests during auth page load
    const authRequests = networkLog.filter(r => r.url.includes('/api/'));
    log(`  API requests during auth load: ${authRequests.length}`);
    for (const req of authRequests) {
      log(`    ${req.method} ${req.url} -> ${req.status}`);
    }
    await page.screenshot({ path: '/tmp/step2-auth-page.png' });
    log('  Screenshot: /tmp/step2-auth-page.png');

    // STEP 3: Sign up
    log('STEP 3: Sign up with test account');
    await page.fill('[placeholder="John Doe"]', TEST_NAME);
    await page.fill('[placeholder="you@company.com"]', TEST_EMAIL);
    await page.fill('[placeholder="Enter your password"]', TEST_PASSWORD);
    await page.fill('[placeholder="Confirm your password"]', TEST_PASSWORD);
    
    const signupStart = Date.now();
    await page.click('button:has-text("Create Account")');
    
    // Wait for either success (redirect) or error
    try {
      await page.waitForURL('**/admin**', { timeout: 20000 });
      const signupTime = Date.now() - signupStart;
      log(`  Signup SUCCESS in ${signupTime}ms`);
      log(`  Redirected to: ${page.url()}`);
    } catch (e) {
      const signupTime = Date.now() - signupStart;
      log(`  Signup FAILED after ${signupTime}ms`);
      log(`  Current URL: ${page.url()}`);
      
      // Check for error message
      const errorMsg = await page.locator('.bg-red-50, .text-red-700').count();
      log(`  Error message visible: ${errorMsg > 0}`);
      
      // Check network errors
      const signupErrors = networkLog.filter(r => r.status >= 400 && r.url.includes('signup'));
      log(`  Signup API errors: ${signupErrors.length}`);
      for (const err of signupErrors) {
        log(`    ${err.status} ${err.url}`);
      }
    }
    
    const token = await page.evaluate(() => localStorage.getItem('token'));
    const user = await page.evaluate(() => localStorage.getItem('user'));
    log(`  Token in localStorage: ${!!token}`);
    log(`  User in localStorage: ${!!user}`);
    await page.screenshot({ path: '/tmp/step3-signup-result.png' });
    log('  Screenshot: /tmp/step3-signup-result.png');

    // STEP 4: Verify database (via API if possible)
    log('STEP 4: Database verification via API');
    if (token) {
      const meResp = await page.request.get(`${API_BASE}/auth/me`);
      log(`  /auth/me status: ${meResp.status()}`);
      if (meResp.ok()) {
        const meData = await meResp.json();
        log(`  User email: ${meData.user?.email}`);
        log(`  User role: ${meData.user?.role}`);
        log(`  Account ID: ${meData.user?.account_id}`);
      }
    } else {
      log('  Cannot verify database - no token');
    }

    // STEP 5: Logout
    log('STEP 5: Logout');
    if (token) {
      await page.goto(`${FRONTEND_URL}/dashboard/cashier`, { waitUntil: 'networkidle', timeout: 30000 });
      const logoutBtn = page.locator('button:has-text("Logout")');
      if (await logoutBtn.count() > 0) {
        await logoutBtn.click();
        await page.waitForTimeout(3000);
        log(`  Post-logout URL: ${page.url()}`);
      } else {
        log('  Logout button not found');
      }
    } else {
      log('  Skipping logout - not logged in');
    }
    await page.screenshot({ path: '/tmp/step5-logout.png' });
    log('  Screenshot: /tmp/step5-logout.png');

    // STEP 6: Login
    log('STEP 6: Login with test credentials');
    await page.goto(`${FRONTEND_URL}/auth/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('[placeholder="you@company.com"]', { timeout: 15000 });
    
    await page.fill('[placeholder="you@company.com"]', TEST_EMAIL);
    await page.fill('[placeholder="Enter your password"]', TEST_PASSWORD);
    
    const loginStart = Date.now();
    await page.click('button:has-text("Sign In")');
    
    try {
      await page.waitForURL('**/admin**', { timeout: 20000 });
      const loginTime = Date.now() - loginStart;
      log(`  Login SUCCESS in ${loginTime}ms`);
      log(`  Redirected to: ${page.url()}`);
    } catch (e) {
      const loginTime = Date.now() - loginStart;
      log(`  Login FAILED after ${loginTime}ms`);
      log(`  Current URL: ${page.url()}`);
    }
    
    const loginToken = await page.evaluate(() => localStorage.getItem('token'));
    log(`  Login token exists: ${!!loginToken}`);
    await page.screenshot({ path: '/tmp/step6-login-result.png' });
    log('  Screenshot: /tmp/step6-login-result.png');

    // STEP 7: Measure login
    log('STEP 7: Login measurement');
    // Already measured above

    // STEP 8: Dashboard
    log('STEP 8: Dashboard inspection');
    await page.goto(`${FRONTEND_URL}/admin`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);
    log(`  Dashboard URL: ${page.url()}`);
    
    // Try to navigate to key pages
    const pages = ['Inventory', 'Products', 'Sales', 'Cashier'];
    for (const pageName of pages) {
      const link = page.locator(`text=${pageName}`).first();
      if (await link.count() > 0) {
        log(`  Found link: ${pageName}`);
      } else {
        log(`  Missing link: ${pageName}`);
      }
    }
    await page.screenshot({ path: '/tmp/step8-dashboard.png' });
    log('  Screenshot: /tmp/step8-dashboard.png');

    // STEP 9: Create test product
    log('STEP 9: Create test product');
    await page.goto(`${FRONTEND_URL}/admin/inventory`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);
    
    const addBtn = page.locator('button:has-text("Add Product")').first();
    if (await addBtn.count() > 0) {
      await addBtn.click();
      await page.waitForTimeout(2000);
      
      const productName = 'E2E TEST PRODUCT';
      await page.locator('input[placeholder="Product Name"]').first.fill(productName);
      await page.locator('input[placeholder="Price"]').first.fill('100');
      
      const submitBtn = page.locator('button:has-text("Add Product")').last();
      if (await submitBtn.count() > 0) {
        await submitBtn.click({ force: true });
        await page.waitForTimeout(3000);
        log('  Product submitted');
      }
      
      const found = await page.locator(`text=${productName}`).count();
      log(`  Product found after create: ${found > 0}`);
      await page.screenshot({ path: '/tmp/step9-product-created.png' });
      log('  Screenshot: /tmp/step9-product-created.png');
    } else {
      log('  Add Product button not found');
      await page.screenshot({ path: '/tmp/step9-no-modal.png' });
    }

    // STEP 11: Cashier/POS
    log('STEP 11: Cashier/POS');
    await page.goto(`${FRONTEND_URL}/dashboard/cashier`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);
    
    const posTab = page.locator('button:has-text("POS")');
    if (await posTab.count() > 0) {
      await posTab.click();
      await page.waitForTimeout(2000);
      log('  POS tab clicked');
    }
    
    const productButtons = await page.locator('button:has-text("KSH")').count();
    log(`  Product buttons visible: ${productButtons}`);
    await page.screenshot({ path: '/tmp/step11-cashier.png' });
    log('  Screenshot: /tmp/step11-cashier.png');

    // STEP 13: Refresh everything
    log('STEP 13: Refresh pages');
    await page.reload({ waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);
    log(`  After reload URL: ${page.url()}`);
    const tokenAfterReload = await page.evaluate(() => localStorage.getItem('token'));
    log(`  Token after reload: ${!!tokenAfterReload}`);
    await page.screenshot({ path: '/tmp/step13-reload.png' });
    log('  Screenshot: /tmp/step13-reload.png');

    // STEP 5 (again): Logout
    log('STEP 5b: Logout');
    const logoutBtn = page.locator('button:has-text("Logout")');
    if (await logoutBtn.count() > 0) {
      await logoutBtn.click();
      await page.waitForTimeout(3000);
      log(`  Post-logout URL: ${page.url()}`);
    } else {
      log('  Logout button not found');
    }

    // STEP 14: Protected route blocked
    log('STEP 14: Protected route blocked');
    await page.goto(`${FRONTEND_URL}/admin`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(2000);
    const protectedUrl = page.url();
    log(`  Protected route URL: ${protectedUrl}`);
    const isBlocked = protectedUrl.includes('/auth/login');
    log(`  Properly blocked: ${isBlocked}`);
    await page.screenshot({ path: '/tmp/step14-blocked.png' });
    log('  Screenshot: /tmp/step14-blocked.png');

    // Summary
    log('TEST SUMMARY');
    log(`  Total console errors: ${consoleErrors.length}`);
    log(`  Total network errors: ${networkLog.filter(r => r.status >= 400).length}`);
    for (const err of consoleErrors.slice(0, 10)) {
      log(`  CONSOLE: ${err.substring(0, 200)}`);
    }

  } catch (error) {
    log(`FATAL ERROR: ${error.message}`);
    console.error(error);
    await page.screenshot({ path: '/tmp/e2e-fatal-error.png' });
  } finally {
    await browser.close();
  }
}

runTests().catch(console.error);
