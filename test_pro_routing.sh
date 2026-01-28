#!/bin/bash

# ================================================================
# Pro Plan Dashboard Routing Test Suite
# ================================================================
# Tests the complete Pro subscription dashboard routing flow:
# 1. Backend auth response includes subscription from account
# 2. Login returns subscription, plan, businessType, businessRole
# 3. Frontend routes Pro users to /pro-dashboard
# 4. Basic/Ultra users remain unchanged
# ================================================================

echo "============================================"
echo "🧪 PRO PLAN ROUTING TEST SUITE"
echo "============================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Base URL (adjust if needed)
BASE_URL="http://localhost:5000"

echo "📍 Testing against: $BASE_URL"
echo ""

# ================================================================
# Test Helper Functions
# ================================================================

test_passed() {
    echo -e "${GREEN}✅ PASS:${NC} $1"
    ((TESTS_PASSED++))
}

test_failed() {
    echo -e "${RED}❌ FAIL:${NC} $1"
    ((TESTS_FAILED++))
}

test_warning() {
    echo -e "${YELLOW}⚠️  WARN:${NC} $1"
}

test_info() {
    echo -e "${BLUE}ℹ️  INFO:${NC} $1"
}

# ================================================================
# TEST 1: Backend Auth Response Structure
# ================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 1: Backend Auth Response Structure"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Test Pro plan signup
test_info "Testing Pro plan signup..."
SIGNUP_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Pro User",
    "email": "test-pro-'$RANDOM'@example.com",
    "password": "password123",
    "plan": "pro"
  }')

echo "Response: $SIGNUP_RESPONSE" | jq '.' 2>/dev/null || echo "$SIGNUP_RESPONSE"

# Check if response contains required fields
if echo "$SIGNUP_RESPONSE" | jq -e '.user.subscription' >/dev/null 2>&1; then
    test_passed "Response includes 'subscription' field"
else
    test_failed "Response missing 'subscription' field"
fi

if echo "$SIGNUP_RESPONSE" | jq -e '.user.plan' >/dev/null 2>&1; then
    test_passed "Response includes 'plan' field"
else
    test_failed "Response missing 'plan' field"
fi

if echo "$SIGNUP_RESPONSE" | jq -e '.user.role' >/dev/null 2>&1; then
    test_passed "Response includes 'role' field"
else
    test_failed "Response missing 'role' field"
fi

# Check if subscription is 'pro'
SUBSCRIPTION=$(echo "$SIGNUP_RESPONSE" | jq -r '.user.subscription // empty')
if [ "$SUBSCRIPTION" = "pro" ]; then
    test_passed "Subscription correctly set to 'pro'"
else
    test_failed "Subscription is '$SUBSCRIPTION', expected 'pro'"
fi

echo ""

# ================================================================
# TEST 2: Pro User Login Response
# ================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 2: Pro User Login Response"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Extract email and test login
EMAIL=$(echo "$SIGNUP_RESPONSE" | jq -r '.user.email // empty')
if [ -z "$EMAIL" ]; then
    test_failed "Could not extract email from signup response"
else
    test_info "Testing login with email: $EMAIL"
    
    LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/login" \
      -H "Content-Type: application/json" \
      -d "{
        \"email\": \"$EMAIL\",
        \"password\": \"password123\"
      }")
    
    echo "Response: $LOGIN_RESPONSE" | jq '.' 2>/dev/null || echo "$LOGIN_RESPONSE"
    
    # Check login response structure
    if echo "$LOGIN_RESPONSE" | jq -e '.user.subscription' >/dev/null 2>&1; then
        test_passed "Login response includes 'subscription' field"
    else
        test_failed "Login response missing 'subscription' field"
    fi
    
    if echo "$LOGIN_RESPONSE" | jq -e '.token' >/dev/null 2>&1; then
        test_passed "Login response includes 'token' field"
    else
        test_failed "Login response missing 'token' field"
    fi
    
    # Check if subscription is 'pro'
    LOGIN_SUBSCRIPTION=$(echo "$LOGIN_RESPONSE" | jq -r '.user.subscription // empty')
    if [ "$LOGIN_SUBSCRIPTION" = "pro" ]; then
        test_passed "Login returns subscription='pro'"
    else
        test_failed "Login subscription is '$LOGIN_SUBSCRIPTION', expected 'pro'"
    fi
fi

echo ""

# ================================================================
# TEST 3: Basic Plan User (Control Test)
# ================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 3: Basic Plan User (Control Test)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

test_info "Testing Basic plan signup..."
BASIC_SIGNUP=$(curl -s -X POST "$BASE_URL/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Basic User",
    "email": "test-basic-'$RANDOM'@example.com",
    "password": "password123",
    "plan": "basic"
  }')

echo "Response: $BASIC_SIGNUP" | jq '.' 2>/dev/null || echo "$BASIC_SIGNUP"

BASIC_SUBSCRIPTION=$(echo "$BASIC_SIGNUP" | jq -r '.user.subscription // .user.plan // empty')
if [ "$BASIC_SUBSCRIPTION" = "basic" ]; then
    test_passed "Basic user has subscription='basic'"
else
    test_failed "Basic user subscription is '$BASIC_SUBSCRIPTION', expected 'basic'"
fi

echo ""

# ================================================================
# TEST 4: Pro User with Business Type
# ================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 4: Pro User with Business Type"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Get token from login response
TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.token // empty')

if [ -z "$TOKEN" ]; then
    test_warning "No token available, skipping business type tests"
else
    test_info "Selecting business type: supermarket"
    
    SELECT_RESPONSE=$(curl -s -X POST "$BASE_URL/api/business/select" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" \
      -d '{
        "businessType": "supermarket"
      }')
    
    echo "Response: $SELECT_RESPONSE" | jq '.' 2>/dev/null || echo "$SELECT_RESPONSE"
    
    if echo "$SELECT_RESPONSE" | jq -e '.success' >/dev/null 2>&1; then
        test_passed "Business type selected successfully"
        
        # Login again to get updated user data
        test_info "Re-logging in to verify business type persistence..."
        LOGIN_AFTER_SELECT=$(curl -s -X POST "$BASE_URL/auth/login" \
          -H "Content-Type: application/json" \
          -d "{
            \"email\": \"$EMAIL\",
            \"password\": \"password123\"
          }")
        
        BUSINESS_TYPE=$(echo "$LOGIN_AFTER_SELECT" | jq -r '.user.businessType // .user.business_type // empty')
        if [ "$BUSINESS_TYPE" = "supermarket" ]; then
            test_passed "Login returns businessType='supermarket' after selection"
        else
            test_failed "Login businessType is '$BUSINESS_TYPE', expected 'supermarket'"
        fi
        
        # Check subscription still pro
        SUBSCRIPTION_AFTER=$(echo "$LOGIN_AFTER_SELECT" | jq -r '.user.subscription // .user.plan // empty')
        if [ "$SUBSCRIPTION_AFTER" = "pro" ]; then
            test_passed "Subscription remains 'pro' after business type selection"
        else
            test_failed "Subscription is '$SUBSCRIPTION_AFTER', expected 'pro'"
        fi
    else
        test_failed "Business type selection failed"
    fi
fi

echo ""

# ================================================================
# TEST 5: Frontend Routing Logic (Static Analysis)
# ================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 5: Frontend Routing Logic (Static Analysis)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check if dashboardRouting.js exists
if [ -f "my-react-app/src/utils/dashboardRouting.js" ]; then
    test_passed "dashboardRouting.js utility exists"
    
    # Check if it exports getDashboardRoute
    if grep -q "export.*getDashboardRoute" my-react-app/src/utils/dashboardRouting.js; then
        test_passed "getDashboardRoute function is exported"
    else
        test_failed "getDashboardRoute function not found in exports"
    fi
    
    # Check if it handles Pro users
    if grep -q "pro.*dashboard" my-react-app/src/utils/dashboardRouting.js; then
        test_passed "Routing utility includes Pro dashboard logic"
    else
        test_failed "Routing utility missing Pro dashboard logic"
    fi
else
    test_failed "dashboardRouting.js utility not found"
fi

# Check if Auth.jsx uses getDashboardRoute
if [ -f "my-react-app/src/pages/Auth.jsx" ]; then
    if grep -q "getDashboardRoute" my-react-app/src/pages/Auth.jsx; then
        test_passed "Auth.jsx imports getDashboardRoute utility"
    else
        test_failed "Auth.jsx does not use getDashboardRoute utility"
    fi
else
    test_warning "Auth.jsx not found"
fi

# Check if ProPlanRouter exists
if [ -f "my-react-app/src/pages/ProPlanRouter.jsx" ]; then
    test_passed "ProPlanRouter.jsx component exists"
    
    # Check if it handles business types
    if grep -q "businessType" my-react-app/src/pages/ProPlanRouter.jsx; then
        test_passed "ProPlanRouter handles businessType"
    else
        test_failed "ProPlanRouter missing businessType logic"
    fi
else
    test_failed "ProPlanRouter.jsx not found"
fi

echo ""

# ================================================================
# TEST 6: Backend Business Routes
# ================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 6: Backend Business Routes"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

test_info "Testing GET /api/business/types endpoint..."
TYPES_RESPONSE=$(curl -s -X GET "$BASE_URL/api/business/types" \
  -H "Authorization: Bearer $TOKEN")

if echo "$TYPES_RESPONSE" | jq -e '.businessTypes' >/dev/null 2>&1; then
    test_passed "GET /api/business/types returns businessTypes"
    
    # Count business types
    TYPES_COUNT=$(echo "$TYPES_RESPONSE" | jq '.businessTypes | length')
    if [ "$TYPES_COUNT" -gt 0 ]; then
        test_passed "Found $TYPES_COUNT business types configured"
    else
        test_failed "No business types found"
    fi
else
    test_failed "GET /api/business/types endpoint failed"
fi

echo ""

# ================================================================
# FINAL SUMMARY
# ================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 TEST SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

TOTAL_TESTS=$((TESTS_PASSED + TESTS_FAILED))
SUCCESS_RATE=0
if [ "$TOTAL_TESTS" -gt 0 ]; then
    SUCCESS_RATE=$((TESTS_PASSED * 100 / TOTAL_TESTS))
fi

echo -e "${GREEN}✅ Passed: $TESTS_PASSED${NC}"
echo -e "${RED}❌ Failed: $TESTS_FAILED${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Success Rate: $SUCCESS_RATE%"
echo ""

if [ "$TESTS_FAILED" -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL TESTS PASSED!${NC}"
    echo "Pro plan dashboard routing is working correctly."
    exit 0
else
    echo -e "${RED}⚠️  SOME TESTS FAILED${NC}"
    echo "Please review the failures above and fix the issues."
    exit 1
fi
