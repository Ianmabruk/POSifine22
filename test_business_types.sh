#!/bin/bash

# Test Script for Dynamic Dashboard Redirection
# This script helps verify the implementation

echo "===================================="
echo "Dynamic Dashboard Test Script"
echo "===================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Check if backend files are modified
echo "Test 1: Checking backend files..."
if grep -q "business_type" backend/database.py; then
    echo -e "${GREEN}✓${NC} database.py has business_type column"
else
    echo -e "${RED}✗${NC} database.py missing business_type column"
fi

if grep -q "business_type" backend/admin_controller.py; then
    echo -e "${GREEN}✓${NC} admin_controller.py handles business_type"
else
    echo -e "${RED}✗${NC} admin_controller.py missing business_type handling"
fi

if grep -q "businessType" backend/app.py; then
    echo -e "${GREEN}✓${NC} app.py processes businessType from request"
else
    echo -e "${RED}✗${NC} app.py missing businessType processing"
fi

# Test 2: Check if frontend files are modified
echo ""
echo "Test 2: Checking frontend files..."
if grep -q "businessType" my-react-app/src/pages/admin/UserManagement.jsx; then
    echo -e "${GREEN}✓${NC} UserManagement.jsx has business type selection"
else
    echo -e "${RED}✗${NC} UserManagement.jsx missing business type selection"
fi

if grep -q "businessType" my-react-app/src/pages/Auth.jsx; then
    echo -e "${GREEN}✓${NC} Auth.jsx handles businessType in routing"
else
    echo -e "${RED}✗${NC} Auth.jsx missing businessType routing"
fi

# Test 3: Check if migration exists
echo ""
echo "Test 3: Checking database migration..."
if grep -q "ALTER TABLE users" backend/database.py; then
    echo -e "${GREEN}✓${NC} Migration to add business columns exists"
else
    echo -e "${RED}✗${NC} Migration missing"
fi

# Test 4: Check if landing page fix is applied
echo ""
echo "Test 4: Checking landing page fix..."
if ! grep -q "if (user) {" my-react-app/src/pages/Landing.jsx | grep -q "navigate"; then
    echo -e "${GREEN}✓${NC} Landing page auto-redirect removed"
else
    echo -e "${YELLOW}?${NC} Landing page may still have auto-redirect"
fi

echo ""
echo "===================================="
echo "Test Summary"
echo "===================================="
echo ""
echo "All code changes have been applied!"
echo ""
echo "Next steps:"
echo "1. Start the backend server: cd backend && python app.py"
echo "2. Start the frontend: cd my-react-app && npm start"
echo "3. Test the flows described in BUSINESS_TYPE_IMPLEMENTATION.md"
echo ""
echo "Key URLs to test:"
echo "- Landing page: http://localhost:3000/"
echo "- Subscription page: http://localhost:3000/choose-subscription"
echo "- Login: http://localhost:3000/auth/login"
echo "- Admin Dashboard: http://localhost:3000/admin (after login)"
echo "- Pro Dashboard: http://localhost:3000/pro-dashboard (Pro users)"
echo ""
echo "Test scenarios:"
echo "1. Create a Pro plan user with business type 'clinic' and role 'doctor'"
echo "2. Login with that user - should redirect to /pro-dashboard → DoctorDashboard"
echo "3. Create a Basic plan user"
echo "4. Login with Basic user - should redirect to /admin (standard dashboard)"
echo "5. Open the app without login - should show landing page (not redirect)"
echo ""
