#!/bin/bash

# ================================================================
# Pro Plan Routing Fix - Deployment Verification
# ================================================================
# Run this script to verify all changes are in place before
# deploying to production
# ================================================================

echo "================================================================"
echo "🔍 PRO PLAN ROUTING FIX - DEPLOYMENT VERIFICATION"
echo "================================================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNING=0

check_pass() {
    echo -e "${GREEN}✅ PASS:${NC} $1"
    ((CHECKS_PASSED++))
}

check_fail() {
    echo -e "${RED}❌ FAIL:${NC} $1"
    ((CHECKS_FAILED++))
}

check_warn() {
    echo -e "${YELLOW}⚠️  WARN:${NC} $1"
    ((CHECKS_WARNING++))
}

check_info() {
    echo -e "${BLUE}ℹ️  INFO:${NC} $1"
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣  BACKEND FILES"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check backend/auth_controller.py exists
if [ -f "backend/auth_controller.py" ]; then
    check_pass "backend/auth_controller.py exists"
    
    # Check if login method gets account
    if grep -q "account.*=.*get.*accounts" backend/auth_controller.py; then
        check_pass "Login method gets account object"
    else
        check_fail "Login method does NOT get account object"
    fi
    
    # Check if login returns subscription
    if grep -q "subscription" backend/auth_controller.py; then
        check_pass "Login returns 'subscription' field"
    else
        check_fail "Login does NOT return 'subscription' field"
    fi
    
    # Check if login checks business_profiles
    if grep -q "business_profile" backend/auth_controller.py; then
        check_pass "Login checks business_profiles"
    else
        check_fail "Login does NOT check business_profiles"
    fi
    
    # Check if login returns businessType
    if grep -q "businessType" backend/auth_controller.py; then
        check_pass "Login returns 'businessType' field"
    else
        check_fail "Login does NOT return 'businessType' field"
    fi
else
    check_fail "backend/auth_controller.py NOT FOUND"
fi

echo ""

# Check backend/business_types.py exists
if [ -f "backend/business_types.py" ]; then
    check_pass "backend/business_types.py exists"
else
    check_warn "backend/business_types.py not found (may not be needed)"
fi

# Check backend/business_routes.py exists
if [ -f "backend/business_routes.py" ]; then
    check_pass "backend/business_routes.py exists"
else
    check_warn "backend/business_routes.py not found (may not be needed)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣  FRONTEND FILES"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check dashboardRouting.js exists
if [ -f "my-react-app/src/utils/dashboardRouting.js" ]; then
    check_pass "dashboardRouting.js exists"
    
    # Check exports
    if grep -q "export function getDashboardRoute" my-react-app/src/utils/dashboardRouting.js; then
        check_pass "getDashboardRoute function exported"
    else
        check_fail "getDashboardRoute NOT exported"
    fi
    
    if grep -q "export function isProUser" my-react-app/src/utils/dashboardRouting.js; then
        check_pass "isProUser function exported"
    else
        check_fail "isProUser NOT exported"
    fi
    
    if grep -q "export function hasBusinessType" my-react-app/src/utils/dashboardRouting.js; then
        check_pass "hasBusinessType function exported"
    else
        check_fail "hasBusinessType NOT exported"
    fi
    
    # Check routing logic
    if grep -q "/pro-dashboard" my-react-app/src/utils/dashboardRouting.js; then
        check_pass "Routes to /pro-dashboard for Pro users"
    else
        check_fail "Missing /pro-dashboard route"
    fi
    
    if grep -q "/select-business-type" my-react-app/src/utils/dashboardRouting.js; then
        check_pass "Routes to /select-business-type for Pro admins without type"
    else
        check_fail "Missing /select-business-type route"
    fi
else
    check_fail "dashboardRouting.js NOT FOUND (CRITICAL)"
fi

echo ""

# Check Auth.jsx uses utility
if [ -f "my-react-app/src/pages/Auth.jsx" ]; then
    check_pass "Auth.jsx exists"
    
    if grep -q "import.*getDashboardRoute" my-react-app/src/pages/Auth.jsx; then
        check_pass "Auth.jsx imports getDashboardRoute"
    else
        check_fail "Auth.jsx does NOT import getDashboardRoute"
    fi
    
    if grep -q "getDashboardRoute(res.user)" my-react-app/src/pages/Auth.jsx; then
        check_pass "Auth.jsx uses getDashboardRoute()"
    else
        check_fail "Auth.jsx does NOT use getDashboardRoute()"
    fi
else
    check_fail "Auth.jsx NOT FOUND"
fi

echo ""

# Check ProPlanRouter.jsx uses utility
if [ -f "my-react-app/src/pages/ProPlanRouter.jsx" ]; then
    check_pass "ProPlanRouter.jsx exists"
    
    if grep -q "import.*isProUser" my-react-app/src/pages/ProPlanRouter.jsx; then
        check_pass "ProPlanRouter imports isProUser"
    else
        check_fail "ProPlanRouter does NOT import isProUser"
    fi
    
    if grep -q "isProUser(user)" my-react-app/src/pages/ProPlanRouter.jsx; then
        check_pass "ProPlanRouter uses isProUser()"
    else
        check_fail "ProPlanRouter does NOT use isProUser()"
    fi
else
    check_fail "ProPlanRouter.jsx NOT FOUND"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣  TESTING & DOCUMENTATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check test script
if [ -f "test_pro_routing.sh" ]; then
    check_pass "test_pro_routing.sh exists"
    
    if [ -x "test_pro_routing.sh" ]; then
        check_pass "test_pro_routing.sh is executable"
    else
        check_warn "test_pro_routing.sh NOT executable (run: chmod +x test_pro_routing.sh)"
    fi
else
    check_fail "test_pro_routing.sh NOT FOUND"
fi

# Check documentation
if [ -f "PRO_ROUTING_FIX.md" ]; then
    check_pass "PRO_ROUTING_FIX.md exists"
else
    check_warn "PRO_ROUTING_FIX.md not found (recommended)"
fi

if [ -f "QUICK_START_PRO_ROUTING.md" ]; then
    check_pass "QUICK_START_PRO_ROUTING.md exists"
else
    check_warn "QUICK_START_PRO_ROUTING.md not found (recommended)"
fi

if [ -f "CHANGES_SUMMARY.md" ]; then
    check_pass "CHANGES_SUMMARY.md exists"
else
    check_warn "CHANGES_SUMMARY.md not found (recommended)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣  CODE QUALITY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check for console.log debugging (should be present)
if grep -q "console.log.*ROUTING" my-react-app/src/utils/dashboardRouting.js 2>/dev/null; then
    check_pass "Debug logging present in routing utility"
else
    check_warn "No debug logging found (recommended for troubleshooting)"
fi

# Check for backend logging
if grep -q "logger.info.*subscription" backend/auth_controller.py 2>/dev/null; then
    check_pass "Backend logging present in auth controller"
else
    check_warn "No backend logging found (recommended for troubleshooting)"
fi

# Check for error handling
if grep -q "try.*except" backend/auth_controller.py 2>/dev/null; then
    check_pass "Error handling present in backend"
else
    check_warn "Limited error handling in backend"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣  DEPLOYMENT READINESS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check if backend is using a database
if [ -f "backend/database.py" ]; then
    check_pass "Database module exists"
    
    if grep -q "def get_account" backend/database.py 2>/dev/null; then
        check_pass "get_account() method exists in database"
    else
        check_fail "get_account() method NOT FOUND in database"
    fi
    
    if grep -q "def get_business_profile" backend/database.py 2>/dev/null; then
        check_pass "get_business_profile() method exists in database"
    else
        check_warn "get_business_profile() method not found (may need to be added)"
    fi
else
    check_fail "backend/database.py NOT FOUND"
fi

# Check if backend routes are registered
if [ -f "backend/app.py" ]; then
    check_pass "backend/app.py exists"
    
    if grep -q "business_routes" backend/app.py 2>/dev/null; then
        check_pass "Business routes registered in app.py"
    else
        check_warn "Business routes may not be registered"
    fi
else
    check_fail "backend/app.py NOT FOUND"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 VERIFICATION SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

TOTAL_CHECKS=$((CHECKS_PASSED + CHECKS_FAILED + CHECKS_WARNING))
echo -e "${GREEN}✅ Passed: $CHECKS_PASSED${NC}"
echo -e "${RED}❌ Failed: $CHECKS_FAILED${NC}"
echo -e "${YELLOW}⚠️  Warnings: $CHECKS_WARNING${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ "$CHECKS_FAILED" -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL CRITICAL CHECKS PASSED!${NC}"
    echo ""
    echo "✅ Ready to deploy! Next steps:"
    echo ""
    echo "1. Run automated tests:"
    echo "   ./test_pro_routing.sh"
    echo ""
    echo "2. Manual testing:"
    echo "   - Pro user signup → business selection → login"
    echo "   - Basic user signup → login (ensure unchanged)"
    echo ""
    echo "3. Review logs:"
    echo "   - Backend: Should show subscription + businessType"
    echo "   - Frontend: Check browser console for routing debug"
    echo ""
    echo "4. Deploy:"
    echo "   - Deploy backend changes first"
    echo "   - Deploy frontend changes"
    echo "   - Monitor production logs"
    echo ""
    exit 0
else
    echo -e "${RED}⚠️  CRITICAL CHECKS FAILED${NC}"
    echo ""
    echo "Please fix the failures above before deploying."
    echo ""
    echo "Common fixes:"
    echo "- Missing imports: Add import statements"
    echo "- Missing functions: Check file was saved correctly"
    echo "- Database methods: Update database.py to include required methods"
    echo ""
    echo "See PRO_ROUTING_FIX.md for detailed implementation guide."
    echo ""
    exit 1
fi
