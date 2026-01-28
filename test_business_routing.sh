#!/bin/bash

# Quick Test for Business Type Routing Fix
echo "======================================"
echo "Business Type Routing - Quick Test"
echo "======================================"
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Testing the fix...${NC}"
echo ""

# Check if changes are applied
echo "1. Checking Auth.jsx for businessType fix..."
if grep -q "business_type: businessType" my-react-app/src/pages/Auth.jsx; then
    echo -e "${GREEN}✓${NC} Auth.jsx updated correctly"
else
    echo "⚠ Auth.jsx may need review"
fi

echo ""
echo "2. Checking auth_controller.py for signup update..."
if grep -q "business_type: Optional\[str\]" backend/auth_controller.py; then
    echo -e "${GREEN}✓${NC} auth_controller.py updated correctly"
else
    echo "⚠ auth_controller.py may need review"
fi

echo ""
echo "3. Checking ProPlanRouter.jsx for enhanced detection..."
if grep -q "user.business_type" my-react-app/src/pages/ProPlanRouter.jsx; then
    echo -e "${GREEN}✓${NC} ProPlanRouter.jsx updated correctly"
else
    echo "⚠ ProPlanRouter.jsx may need review"
fi

echo ""
echo "======================================"
echo "Manual Testing Steps"
echo "======================================"
echo ""
echo "To test the fix:"
echo ""
echo "1. Start backend: cd backend && python app.py"
echo "2. Start frontend: cd my-react-app && npm start"
echo ""
echo "3. Test Pro Plan - Clinic:"
echo "   a. Go to http://localhost:3000/choose-subscription"
echo "   b. Select 'Pro' plan"
echo "   c. Click 'Get Started'"
echo "   d. Select 'Clinic' business type"
echo "   e. Complete signup"
echo "   f. Should redirect to clinic dashboard ✅"
echo "   g. Logout and login again"
echo "   h. Should still go to clinic dashboard ✅"
echo ""
echo "4. Test Pro Plan - Bar:"
echo "   a. Repeat steps with 'Bar/Restaurant' selection"
echo "   b. Should redirect to bar dashboard ✅"
echo ""
echo "5. Test Pro Plan - Hotel:"
echo "   a. Repeat steps with 'Hotel' selection"
echo "   b. Should redirect to hotel dashboard ✅"
echo ""
echo "6. Test Basic/Ultra (unchanged):"
echo "   a. Select Basic or Ultra plan"
echo "   b. Should go to standard admin dashboard ✅"
echo ""
echo "Check browser console for logs like:"
echo "  [SIGNUP] Plan: pro, BusinessType: clinic"
echo "  [PRO PLAN ROUTER] Business Type: clinic, Role: admin"
echo ""
