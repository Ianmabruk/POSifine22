const { chromium } = require('playwright');

const FRONTEND_URL = 'https://posifine11.netlify.app';
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
  
  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
      log(`CONSOLE ERROR: ${msg.text().substring(0, 200)}`);
    }
  });
  
  page.on('response', async response => {
    const url = response.url();
    if (response.status() >= 500) {
      log(`SERVER ERROR: ${response.status()} ${response.request().method()} ${url}`);
    }
  });

  try {
    log('DEPLOYED FRONTEND TEST: Homepage');
    await page.goto(FRONTEND_URL, { waitUntil: 'networkidle', timeout: 30000 });
    log(`  URL: ${page.url()}`);
    log(`  Title: ${await page.title()}`);
    
    log('DEPLOYED FRONTEND TEST: Signup');
    await page.goto(`${FRONTEND_URL}/auth/signup`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('[placeholder="John Doe"]', { timeout: 15000 });
    
    await page.fill('[placeholder="John Doe"]', TEST_NAME);
    await page.fill('[placeholder="you@company.com"]', TEST_EMAIL);
    await page.fill('[placeholder="Enter your password"]', TEST_PASSWORD);
    await page.fill('[placeholder="Confirm your password"]', TEST_PASSWORD);
    
    const signupStart = Date.now();
    await page.click('button:has-text("Create Account")');
    await page.waitForTimeout(15000);
    const signupTime = Date.now() - signupStart;
    
    const postSignupUrl = page.url();
    const token = await page.evaluate(() => localStorage.getItem('token'));
    
    log(`  Signup duration: ${signupTime}ms`);
    log(`  Post-signup URL: ${postSignupUrl}`);
    log(`  Token exists: ${!!token}`);
    
    if (!token) {
      log('  Signup failed on deployed frontend');
      await page.screenshot({ path: '/tmp/deployed-signup-fail.png' });
    }
    
    log('DEPLOYED FRONTEND TEST: Login');
    await page.goto(`${FRONTEND_URL}/auth/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('[placeholder="you@company.com"]', { timeout: 15000 });
    
    await page.fill('[placeholder="you@company.com"]', TEST_EMAIL);
    await page.fill('[placeholder="Enter your password"]', TEST_PASSWORD);
    
    const loginStart = Date.now();
    await page.click('button:has-text("Sign In")');
    await page.waitForTimeout(15000);
    const loginTime = Date.now() - loginStart;
    
    const postLoginUrl = page.url();
    const loginToken = await page.evaluate(() => localStorage.getItem('token'));
    
    log(`  Login duration: ${loginTime}ms`);
    log(`  Post-login URL: ${postLoginUrl}`);
    log(`  Login token exists: ${!!loginToken}`);
    
  } catch (error) {
    log(`ERROR: ${error.message}`);
    console.error(error);
    await page.screenshot({ path: '/tmp/deployed-error.png' });
  } finally {
    await browser.close();
  }
}

runTests().catch(console.error);
