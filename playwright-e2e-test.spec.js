const { test, expect } = require('@playwright/test');

const FRONTEND_URL = 'http://localhost:3000';
const API_BASE = 'http://localhost:8080/api';
const TIMESTAMP = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
const TEST_EMAIL = `e2e-test-${TIMESTAMP}@example.com`;
const TEST_PASSWORD = 'Testpass1';
const TEST_NAME = 'E2E Test User';

let authToken = null;
let refreshToken = null;
let csrfToken = null;
let userId = null;
let accountId = null;

test.describe('POSify End-to-End Test', () => {
  test.beforeAll(async () => {
    // Pre-clean any existing test user with same email pattern
    const api = require('playwright').request.newContext();
    try {
      await api.post(`${API_BASE}/auth/signup`, {
        data: { email: TEST_EMAIL, password: TEST_PASSWORD, name: TEST_NAME }
      });
    } catch (e) {
      // user might already exist, that's fine
    }
  });

  test('1. Homepage loads successfully', async ({ page }) => {
    const start = Date.now();
    const response = await page.goto(FRONTEND_URL);
    const loadTime = Date.now() - start;
    
    console.log(`HOME PAGE LOAD TIME: ${loadTime}ms`);
    expect(response.status()).toBe(200);
    
    await page.waitForLoadState('networkidle', { timeout: 15000 });
    
    const consoleErrors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    
    console.log(`HOME PAGE CONSOLE ERRORS: ${consoleErrors.length}`);
    for (const err of consoleErrors.slice(0, 10)) {
      console.log(`  CONSOLE ERROR: ${err}`);
    }
    
    const failedRequests = [];
    page.on('response', response => {
      if (response.status() >= 400) failedRequests.push(`${response.status()} ${response.url()}`);
    });
    
    console.log(`HOME PAGE FAILED REQUESTS: ${failedRequests.length}`);
    for (const req of failedRequests.slice(0, 10)) {
      console.log(`  FAILED REQUEST: ${req}`);
    }
  });

  test('2. Signup creates account and redirects', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/auth/signup`);
    await page.waitForLoadState('networkidle', { timeout: 15000 });
    
    await page.waitForSelector('[placeholder="John Doe"]', { timeout: 10000 });
    
    const signupStart = Date.now();
    
    await page.fill('[placeholder="John Doe"]', TEST_NAME);
    await page.fill('[placeholder="you@company.com"]', TEST_EMAIL);
    await page.fill('[placeholder="Enter your password"]', TEST_PASSWORD);
    await page.fill('[placeholder="Confirm your password"]', TEST_PASSWORD);
    
    await page.click('button:has-text("Create Account")');
    
    // Wait for navigation or API response
    await page.waitForTimeout(8000);
    
    const signupTime = Date.now() - signupStart;
    console.log(`SIGNUP DURATION: ${signupTime}ms`);
    
    const url = page.url();
    console.log(`POST-SIGNUP URL: ${url}`);
    
    // Check localStorage for tokens
    const token = await page.evaluate(() => localStorage.getItem('token'));
    const user = await page.evaluate(() => localStorage.getItem('user'));
    
    console.log(`SIGNUP TOKEN EXISTS: ${!!token}`);
    console.log(`SIGNUP USER EXISTS: ${!!user}`);
    
    if (token) {
      authToken = token;
      refreshToken = await page.evaluate(() => localStorage.getItem('refreshToken'));
      csrfToken = await page.evaluate(() => localStorage.getItem('csrfToken'));
      const userData = JSON.parse(user || '{}');
      userId = userData.id;
      accountId = userData.account_id;
      console.log(`SIGNUP USER ID: ${userId}`);
      console.log(`SIGNUP ACCOUNT ID: ${accountId}`);
    }
    
    // Should redirect away from signup page
    expect(url).not.toContain('/auth/signup');
  });

  test('3. Login with credentials', async ({ page }) => {
    // Clear any existing auth
    await page.goto(FRONTEND_URL);
    await page.evaluate(() => localStorage.clear());
    
    await page.goto(`${FRONTEND_URL}/auth/login`);
    await page.waitForLoadState('networkidle', { timeout: 15000 });
    
    await page.waitForSelector('[placeholder="you@company.com"]', { timeout: 10000 });
    
    const loginStart = Date.now();
    
    await page.fill('[placeholder="you@company.com"]', TEST_EMAIL);
    await page.fill('[placeholder="Enter your password"]', TEST_PASSWORD);
    
    await page.click('button:has-text("Sign In")');
    await page.waitForTimeout(8000);
    
    const loginTime = Date.now() - loginStart;
    console.log(`LOGIN TIME: ${loginTime}ms`);
    
    const token = await page.evaluate(() => localStorage.getItem('token'));
    console.log(`LOGIN TOKEN EXISTS: ${!!token}`);
    expect(token).toBeTruthy();
    authToken = token;
  });

  test('4. Dashboard loads after login', async ({ page }) => {
    // Ensure logged in
    if (!authToken) {
      await page.goto(`${FRONTEND_URL}/auth/login`);
      await page.waitForLoadState('networkidle');
      await page.fill('[placeholder="you@company.com"]', TEST_EMAIL);
      await page.fill('[placeholder="Enter your password"]', TEST_PASSWORD);
      await page.click('button:has-text("Sign In")');
      await page.waitForTimeout(5000);
    }
    
    const dashboardStart = Date.now();
    await page.goto(`${FRONTEND_URL}/admin`);
    await page.waitForLoadState('networkidle', { timeout: 20000 });
    await page.waitForTimeout(3000);
    const dashboardTime = Date.now() - dashboardStart;
    
    console.log(`DASHBOARD LOAD TIME: ${dashboardTime}ms`);
    
    const sidebar = await page.locator('text=Inventory').count();
    console.log(`DASHBOARD INVENTORY LINK: ${sidebar > 0}`);
  });

  test('5. Products/Inventory page loads', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/admin/inventory`);
    await page.waitForLoadState('networkidle', { timeout: 20000 });
    
    const invStart = Date.now();
    await page.waitForTimeout(3000);
    const invTime = Date.now() - invStart;
    
    console.log(`INVENTORY LOAD TIME: ${invTime}ms`);
    
    const searchInput = await page.locator('input[placeholder="Search products..."]').count();
    console.log(`INVENTORY SEARCH INPUT: ${searchInput > 0}`);
  });

  test('6. Create test product', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/admin/inventory`);
    await page.waitForLoadState('networkidle', { timeout: 20000 });
    
    const productStart = Date.now();
    
    // Try to find Add Product button
    const addBtn = page.locator('button:has-text("Add Product")').first();
    if (await addBtn.count() > 0) {
      await addBtn.click();
      await page.waitForTimeout(2000);
      
      const productName = `E2E Test Product ${TIMESTAMP}`;
      
      // Try different possible selectors for product name input
      const nameInput = page.locator('input[placeholder="Product name"]').first();
      if (await nameInput.count() > 0) {
        await nameInput.fill(productName);
      } else {
        await page.fill('input[type="text"]', productName);
      }
      
      // Try to select category
      const categorySelect = page.locator('select').first();
      if (await categorySelect.count() > 0) {
        await categorySelect.selectOption('Finished Product');
      }
      
      // Fill price
      const priceInput = page.locator('input[placeholder="0.00"], input[placeholder="Selling price"], input[placeholder="Price"]').first();
      if (await priceInput.count() > 0) {
        await priceInput.fill('100');
      }
      
      // Submit
      const submitBtn = page.locator('button:has-text("Add Product")').last();
      if (await submitBtn.count() > 0) {
        await submitBtn.click();
        await page.waitForTimeout(3000);
      }
      
      const productTime = Date.now() - productStart;
      console.log(`PRODUCT CREATION TIME: ${productTime}ms`);
      
      // Verify
      const found = await page.locator(`text=${productName}`).count();
      console.log(`PRODUCT FOUND AFTER CREATE: ${found > 0}`);
    } else {
      console.log('ADD PRODUCT BUTTON NOT FOUND');
      console.log(await page.content());
    }
  });

  test('7. Navigate to Cashier/POS', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/dashboard/cashier`);
    await page.waitForLoadState('networkidle', { timeout: 20000 });
    
    const cashierStart = Date.now();
    await page.waitForTimeout(3000);
    const cashierTime = Date.now() - cashierStart;
    
    console.log(`CASHIER PAGE LOAD TIME: ${cashierTime}ms`);
    
    const posTab = await page.locator('button:has-text("POS")').count();
    console.log(`POS TAB FOUND: ${posTab > 0}`);
  });

  test('8. Add product to cart and checkout', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/dashboard/cashier`);
    await page.waitForLoadState('networkidle', { timeout: 20000 });
    
    // Ensure POS tab is active
    const posTab = page.locator('button:has-text("POS")');
    if (await posTab.count() > 0) {
      await posTab.click();
      await page.waitForTimeout(2000);
    }
    
    // Find product buttons with KSH price
    const productButtons = await page.locator('button:has-text("KSH")').count();
    console.log(`PRODUCT BUTTONS IN POS: ${productButtons}`);
    
    if (productButtons > 0) {
      await page.locator('button:has-text("KSH")').first.click();
      await page.waitForTimeout(1000);
      
      // Look for checkout button
      const checkoutBtn = page.locator('button:has-text("Checkout")');
      if (await checkoutBtn.count() > 0) {
        await checkoutBtn.click();
        await page.waitForTimeout(2000);
        
        // Select cash payment
        const cashOption = page.locator('text=Cash').first();
        if (await cashOption.count() > 0) {
          await cashOption.click();
          await page.waitForTimeout(1000);
        }
        
        // Complete sale
        const completeBtn = page.locator('button:has-text("COMPLETE SALE"), button:has-text("Complete Sale")');
        if (await completeBtn.count() > 0) {
          await completeBtn.click();
          await page.waitForTimeout(3000);
          console.log('SALE COMPLETED');
        }
      }
    }
  });

  test('9. Logout', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/dashboard/cashier`);
    await page.waitForLoadState('networkidle', { timeout: 20000 });
    
    const logoutBtn = page.locator('button:has-text("Logout")');
    if (await logoutBtn.count() > 0) {
      await logoutBtn.click();
      await page.waitForTimeout(3000);
      
      const url = page.url();
      console.log(`POST-LOGOUT URL: ${url}`);
    }
  });

  test('10. Protected route blocked after logout', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/admin`);
    await page.waitForLoadState('networkidle', { timeout: 15000 });
    
    const url = page.url();
    console.log(`PROTECTED ROUTE AFTER LOGOUT: ${url}`);
    
    // Should redirect to login
    expect(url).toMatch(/\/auth\/login/);
  });

  test('11. Wrong password fails gracefully', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/auth/login`);
    await page.waitForLoadState('networkidle', { timeout: 15000 });
    
    await page.fill('[placeholder="you@company.com"]', TEST_EMAIL);
    await page.fill('[placeholder="Enter your password"]', 'Wrongpassword1');
    await page.click('button:has-text("Sign In")');
    await page.waitForTimeout(3000);
    
    const url = page.url();
    console.log(`WRONG PASSWORD URL: ${url}`);
    expect(url).toContain('/auth/login');
    
    const errorMsg = await page.locator('.bg-red-50, .text-red-700').count();
    console.log(`ERROR MESSAGE SHOWN: ${errorMsg > 0}`);
  });
});
