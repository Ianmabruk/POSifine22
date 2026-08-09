const { chromium } = require('playwright');
const http = require('http');

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
  const apiResponses = [];
  
  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
      log(`CONSOLE ERROR: ${msg.text()}`);
    }
  });
  
  page.on('response', async response => {
    const url = response.url();
    if (url.includes('/api/auth/')) {
      try {
        const body = await response.text();
        apiResponses.push({ url, status: response.status(), body });
        log(`API RESPONSE: ${response.status()} ${response.request().method()} ${url}`);
        if (body.length < 1000) log(`  BODY: ${body}`);
      } catch (e) {
        log(`API RESPONSE: ${response.status()} ${response.request().method()} ${url} (error reading body)`);
      }
    }
  });

  try {
    // Direct API test first
    log('DIRECT API TEST: Signup');
    const signupResult = await apiPost('/auth/signup', {
      email: TEST_EMAIL,
      password: TEST_PASSWORD,
      name: TEST_NAME
    });
    log(`  Signup API status: ${signupResult.status}`);
    log(`  Signup API body: ${JSON.stringify(signupResult.data).substring(0, 200)}`);
    
    if (signupResult.data && signupResult.data.token) {
      log('DIRECT API TEST: Login');
      const loginResult = await apiPost('/auth/login', {
        email: TEST_EMAIL,
        password: TEST_PASSWORD
      });
      log(`  Login API status: ${loginResult.status}`);
      log(`  Login API body: ${JSON.stringify(loginResult.data).substring(0, 200)}`);
    }
    
    // TEST: Signup via UI
    log('UI TEST: Signup');
    await page.goto(`${FRONTEND_URL}/auth/signup`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForSelector('[placeholder="John Doe"]', { timeout: 15000 });
    
    await page.fill('[placeholder="John Doe"]', TEST_NAME + ' UI');
    await page.fill('[placeholder="you@company.com"]', TEST_EMAIL + '-ui');
    await page.fill('[placeholder="Enter your password"]', TEST_PASSWORD);
    await page.fill('[placeholder="Confirm your password"]', TEST_PASSWORD);
    
    await page.click('button:has-text("Create Account")');
    await page.waitForTimeout(10000);
    
    log(`  Post-signup URL: ${page.url()}`);
    log(`  Token: ${await page.evaluate(() => localStorage.getItem('token'))}`);
    log(`  User: ${await page.evaluate(() => localStorage.getItem('user'))}`);
    
    for (const resp of apiResponses) {
      log(`  CAPTURED: ${resp.status} ${resp.url}`);
      if (resp.body.length < 500) log(`    ${resp.body}`);
    }
    
  } catch (error) {
    log(`ERROR: ${error.message}`);
    console.error(error);
  } finally {
    await browser.close();
  }
}

function apiPost(endpoint, data) {
  return new Promise((resolve, reject) => {
    const url = new URL(API_BASE + endpoint);
    const body = JSON.stringify(data);
    const options = {
      hostname: url.hostname,
      port: url.port,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body)
      }
    };
    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, data: JSON.parse(data) });
        } catch (e) {
          resolve({ status: res.statusCode, data: data });
        }
      });
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

runTests().catch(console.error);
