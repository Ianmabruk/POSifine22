# Phase 2 Testing & Verification Guide

## Test Coverage Matrix

| Feature | Test | Status |
|---------|------|--------|
| Custom Plan Redirect | Routing logic | ✅ |
| Main Admin Dashboard | Access & rendering | ✅ |
| Subscriber Management | CRUD operations | ✅ |
| Analytics Dashboard | Chart rendering | ✅ |
| API Endpoints | Backend responses | ✅ |
| Authentication | Token validation | ✅ |
| Authorization | Role-based access | ✅ |

---

## Pre-Testing Checklist

- [ ] Backend running (Flask app started)
- [ ] Frontend built (`npm run build` successful)
- [ ] Database connected and migrated
- [ ] Environment variables configured
- [ ] Network connectivity verified
- [ ] Browser console clear (no errors)

---

## Test Suite 1: Custom Plan Redirection

### Test 1.1: Custom Plan → Build POS → Signup → Admin
**Steps**:
1. Open browser, go to `/plans`
2. Click "Get Started" on Custom plan
3. Should redirect to `/build-pos`
4. Select a business type (e.g., "Bar")
5. Click "Confirm"
6. Should redirect to `/auth/signup`
7. Fill signup form
8. Submit form
9. Should redirect to `/admin`
10. Verify business-specific admin dashboard loads

**Expected Result**: ✅ User sees Bar admin dashboard
**Actual Result**: 
- [ ] Pass
- [ ] Fail (document issue)

**Notes**:

---

### Test 1.2: Basic Plan Still Works
**Steps**:
1. Go to `/plans`
2. Click "Get Started" on Basic plan
3. Should redirect to `/auth/signup`
4. Fill signup form
5. Submit form
6. Should redirect to `/admin`

**Expected Result**: ✅ User sees generic admin dashboard
**Actual Result**:
- [ ] Pass
- [ ] Fail

---

### Test 1.3: Cashier Role Redirect
**Steps**:
1. As admin, create a cashier account
2. Cashier logs in
3. Should redirect to `/dashboard/cashier`

**Expected Result**: ✅ Cashier sees POS dashboard
**Actual Result**:
- [ ] Pass
- [ ] Fail

---

## Test Suite 2: Main Admin Dashboard

### Test 2.1: Owner Login & Main Admin Access
**Steps**:
1. Login as owner (role='owner')
2. Should redirect to `/main-admin`
3. Page should load with sidebar and metrics

**Expected Result**: ✅ Main Admin dashboard fully loaded
**Actual Result**:
- [ ] Pass
- [ ] Fail

**Debug Info**:
- Browser console errors?
- Network tab shows failed requests?
- Metrics cards populated?

---

### Test 2.2: Metrics Display
**Steps**:
1. On Main Admin dashboard
2. Check metrics cards:
   - Total Subscribers count
   - Active Subscribers count
   - Monthly Revenue amount
   - Growth Rate percentage

**Expected Result**: ✅ All metrics show numbers (not 0 or null)
**Actual Result**:
- [ ] Pass
- [ ] Fail

---

### Test 2.3: Dashboard Tab Navigation
**Steps**:
1. Click "Dashboard" in sidebar
2. Should show metrics + overview
3. Click "Subscribers" in sidebar
4. Should show subscriber table
5. Click "Analytics" in sidebar
6. Should show charts

**Expected Result**: ✅ All tabs switch without errors
**Actual Result**:
- [ ] Pass
- [ ] Fail

---

## Test Suite 3: Subscriber Management

### Test 3.1: Search Functionality
**Steps**:
1. Go to Subscribers tab
2. Type a subscriber name in search box
3. Table should filter in real-time
4. Clear search
5. Table should show all subscribers again

**Expected Result**: ✅ Search filters correctly
**Actual Result**:
- [ ] Pass
- [ ] Fail

---

### Test 3.2: Status Filter
**Steps**:
1. Click "Status" dropdown
2. Select "Active"
3. Table should show only active subscribers
4. Select "Suspended"
5. Table should show only suspended subscribers

**Expected Result**: ✅ Filter works for all options
**Actual Result**:
- [ ] Pass
- [ ] Fail

---

### Test 3.3: Plan Filter
**Steps**:
1. Click "Plan" dropdown
2. Select "Basic"
3. Table should show only Basic plan users
4. Select "Ultra"
5. Table should show only Ultra plan users

**Expected Result**: ✅ Filter works for all plans
**Actual Result**:
- [ ] Pass
- [ ] Fail

---

### Test 3.4: Suspend Subscriber
**Steps**:
1. Find active subscriber in table
2. Click yellow lock (🔒) button in Actions
3. Confirm suspension
4. Status should change to "Suspended"
5. Verify database updated

**Expected Result**: ✅ Subscriber status changed to suspended
**Actual Result**:
- [ ] Pass
- [ ] Fail

**Network Check**:
- PUT request to `/api/v2/admin/subscribers/{id}` returned 200?

---

### Test 3.5: Activate Subscriber
**Steps**:
1. Find suspended subscriber in table
2. Click green unlock (🔓) button in Actions
3. Confirm activation
4. Status should change to "Active"
5. Verify database updated

**Expected Result**: ✅ Subscriber status changed to active
**Actual Result**:
- [ ] Pass
- [ ] Fail

---

### Test 3.6: Export CSV
**Steps**:
1. Click "Export CSV" button
2. File should download: `subscribers-YYYY-MM-DD.csv`
3. Open file in Excel/Sheets
4. Verify columns: Business, Owner, Email, Plan, Status, Date

**Expected Result**: ✅ CSV file downloaded and readable
**Actual Result**:
- [ ] Pass
- [ ] Fail

**File Check**:
- File size > 100 bytes?
- Contains header row?
- Data rows present?

---

## Test Suite 4: Analytics Dashboard

### Test 4.1: Charts Display
**Steps**:
1. Go to Analytics tab
2. Wait for page to load
3. Verify all charts render:
   - Revenue Trend (line chart)
   - Plan Distribution (pie chart)
   - Subscriptions Growth (bar chart)
   - Revenue Breakdown (stat cards)

**Expected Result**: ✅ All charts display without errors
**Actual Result**:
- [ ] Pass
- [ ] Fail

**Render Check**:
- Any console errors?
- Chart SVG elements present?
- Data labels visible?

---

### Test 4.2: Time Range Selector
**Steps**:
1. Default should be "Last 30 Days"
2. Click dropdown
3. Select "Last 7 Days"
4. Charts should update
5. Select "Last 90 Days"
6. Charts should update
7. Select "Last Year"
8. Charts should update

**Expected Result**: ✅ Charts re-render for each time range
**Actual Result**:
- [ ] Pass
- [ ] Fail

**Performance**:
- Each change takes < 500ms?
- No freeze/lag?

---

### Test 4.3: Export Report
**Steps**:
1. Click "Export Report"
2. File should download: `analytics-report-YYYY-MM-DD.json`
3. Open in text editor
4. Verify JSON structure

**Expected Result**: ✅ JSON file downloaded with analytics data
**Actual Result**:
- [ ] Pass
- [ ] Fail

**JSON Check**:
- Valid JSON format?
- Contains revenueByPlan?
- Contains usageOverTime?
- Contains planDistribution?

---

## Test Suite 5: API Endpoints

### Test 5.1: GET /api/v2/admin/metrics
**Using curl**:
```bash
curl -X GET http://localhost:5000/api/v2/admin/metrics \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

**Expected Response**:
```json
{
  "totalSubscribers": 45,
  "activeSubscribers": 42,
  "revenue": 97500,
  "growth": 12.5
}
```

**Verification**:
- [ ] Status code 200
- [ ] Response contains all fields
- [ ] Numbers are realistic
- [ ] No null values

---

### Test 5.2: GET /api/v2/admin/subscribers
**Using curl**:
```bash
curl -X GET http://localhost:5000/api/v2/admin/subscribers \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected Response**:
```json
[
  {
    "id": "uuid",
    "name": "John",
    "email": "john@example.com",
    "businessName": "Bar",
    "plan": "custom",
    "isActive": true,
    "isSuspended": false,
    "createdAt": "2024-01-15T10:30:00"
  }
]
```

**Verification**:
- [ ] Status code 200
- [ ] Returns array
- [ ] Each item has all fields
- [ ] Data is recent

---

### Test 5.3: PUT /api/v2/admin/subscribers/{id}
**Using curl**:
```bash
curl -X PUT http://localhost:5000/api/v2/admin/subscribers/UUID \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"isSuspended": true}'
```

**Expected Response**:
```json
{
  "success": true,
  "message": "Subscriber updated"
}
```

**Verification**:
- [ ] Status code 200
- [ ] Response indicates success
- [ ] Database updated
- [ ] Frontend reflects change

---

### Test 5.4: GET /api/v2/admin/analytics
**Using curl**:
```bash
curl -X GET "http://localhost:5000/api/v2/admin/analytics?range=30days" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected Response**:
```json
{
  "revenueByPlan": [...],
  "usageOverTime": [...],
  "planDistribution": [...],
  "revenueTrend": [...]
}
```

**Verification**:
- [ ] Status code 200
- [ ] Contains all required arrays
- [ ] Arrays have data
- [ ] Time range correctly applied

---

## Test Suite 6: Access Control

### Test 6.1: Non-Owner Can't Access Main Admin
**Steps**:
1. Login as admin (not owner)
2. Navigate to `/main-admin`
3. Should redirect to `/auth/login` or show 403

**Expected Result**: ✅ Access denied
**Actual Result**:
- [ ] Pass
- [ ] Fail

---

### Test 6.2: Unauthenticated Can't Access Main Admin
**Steps**:
1. Don't login
2. Navigate to `/main-admin`
3. Should redirect to `/auth/login`

**Expected Result**: ✅ Redirected to login
**Actual Result**:
- [ ] Pass
- [ ] Fail

---

### Test 6.3: Invalid Token Rejected
**Steps**:
1. Modify token in localStorage to invalid value
2. Refresh page
3. Should show error or redirect

**Expected Result**: ✅ Invalid token rejected
**Actual Result**:
- [ ] Pass
- [ ] Fail

---

## Test Suite 7: Performance

### Test 7.1: Dashboard Load Time
**Measure**:
1. Open DevTools Network tab
2. Reload Main Admin dashboard
3. Note Time to Interactive (TTI)

**Expected**: < 2 seconds
**Actual**: ____ seconds

---

### Test 7.2: Metrics Endpoint Response Time
**Measure**:
1. Network tab
2. Call GET /api/v2/admin/metrics
3. Note response time

**Expected**: < 100ms
**Actual**: ____ ms

---

### Test 7.3: Subscribers List Response Time
**Measure**:
1. Call GET /api/v2/admin/subscribers
2. Note response time

**Expected**: < 500ms
**Actual**: ____ ms

---

### Test 7.4: Charts Render Time
**Measure**:
1. Go to Analytics tab
2. Use Performance tab to measure render time
3. Note Time to Paint (TTP)

**Expected**: < 500ms
**Actual**: ____ ms

---

## Test Suite 8: Edge Cases

### Test 8.1: Empty Subscriber List
**Steps**:
1. Delete all test subscribers
2. Go to Subscribers tab
3. Should show "No subscribers found"

**Expected Result**: ✅ Graceful empty state
**Actual Result**:
- [ ] Pass
- [ ] Fail

---

### Test 8.2: Search No Results
**Steps**:
1. Search for non-existent name
2. Table should be empty
3. Message should say "No subscribers found"

**Expected Result**: ✅ Empty state displayed
**Actual Result**:
- [ ] Pass
- [ ] Fail

---

### Test 8.3: Large CSV Export
**Steps**:
1. Add 100+ test subscribers
2. Export CSV
3. File should handle large dataset

**Expected Result**: ✅ CSV generated without errors
**Actual Result**:
- [ ] Pass
- [ ] Fail

---

## Test Suite 9: Browser Compatibility

### Browsers to Test
- [ ] Chrome (latest)
- [ ] Firefox (latest)
- [ ] Safari (latest)
- [ ] Edge (latest)

### Test on Each:
1. Main Admin dashboard loads
2. All tabs work
3. Filters work
4. Export works
5. Charts display
6. Responsive on mobile

---

## Issue Reporting Template

```
**Title**: [Brief description]

**Severity**: Critical / High / Medium / Low

**Steps to Reproduce**:
1. 
2. 
3. 

**Expected Result**: 

**Actual Result**: 

**Browser**: Chrome v120

**Screenshots**: [Attach if applicable]

**Console Errors**: [Paste error messages]

**Network Errors**: [Any failed requests?]
```

---

## Sign-Off Checklist

- [ ] All Test Suites 1-9 passed
- [ ] No critical issues
- [ ] Performance acceptable
- [ ] Security verified
- [ ] Documentation complete
- [ ] Ready for production

---

## Test Execution Record

| Suite | Tests | Pass | Fail | Status |
|-------|-------|------|------|--------|
| 1. Custom Redirect | 3 | 0 | 0 | ⏳ |
| 2. Main Admin | 3 | 0 | 0 | ⏳ |
| 3. Subscribers | 6 | 0 | 0 | ⏳ |
| 4. Analytics | 3 | 0 | 0 | ⏳ |
| 5. API Endpoints | 4 | 0 | 0 | ⏳ |
| 6. Access Control | 3 | 0 | 0 | ⏳ |
| 7. Performance | 4 | 0 | 0 | ⏳ |
| 8. Edge Cases | 3 | 0 | 0 | ⏳ |
| 9. Browser Compat | 5 | 0 | 0 | ⏳ |

**Total**: 34 tests

---

**Test Date**: ___________
**Tester**: ___________
**Sign-Off**: ___________

