#!/bin/bash

# Stock Update WebSocket Test
# Tests real-time stock updates between admin and cashier

echo "================================"
echo "STOCK UPDATE WEBSOCKET TEST"
echo "================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if backend is running
echo "1. Checking backend status..."
BACKEND_STATUS=$(curl -s http://localhost:5000/ | grep -o '"status":"running"')

if [ -n "$BACKEND_STATUS" ]; then
    echo -e "${GREEN}✓${NC} Backend is running"
else
    echo -e "${RED}✗${NC} Backend is not running. Start it with: cd backend && python app.py"
    exit 1
fi

# Check if frontend is running
echo ""
echo "2. Checking frontend status..."
FRONTEND_STATUS=$(curl -s http://localhost:3000 2>/dev/null)

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Frontend is accessible"
else
    echo -e "${YELLOW}⚠${NC} Frontend might not be running. Start it with: cd my-react-app && npm start"
fi

# Test WebSocket endpoint
echo ""
echo "3. Testing WebSocket endpoint..."
echo "   Opening WebSocket connection to ws://localhost:5000/ws"

# Create a simple WebSocket test using wscat if available
if command -v wscat &> /dev/null; then
    echo ""
    echo "   Testing with wscat..."
    echo "   You should see connection messages and can send ping/pong"
    echo ""
    echo "   Press Ctrl+C to exit"
    echo ""
    wscat -c ws://localhost:5000/ws
else
    echo -e "${YELLOW}⚠${NC} wscat not installed. To test WebSocket manually:"
    echo "   npm install -g wscat"
    echo "   wscat -c ws://localhost:5000/ws"
fi

echo ""
echo "================================"
echo "MANUAL TEST STEPS"
echo "================================"
echo ""
echo "To test stock updates manually:"
echo ""
echo "1. Open Admin Dashboard: http://localhost:3000/auth/login"
echo "   Login as admin/owner"
echo ""
echo "2. Open Cashier POS in another window: http://localhost:3000/auth/login"
echo "   Login as cashier"
echo ""
echo "3. In Admin Dashboard:"
echo "   - Go to Inventory"
echo "   - Click 'Add Stock' on any product"
echo "   - Add stock (e.g., +10 units)"
echo ""
echo "4. Watch Cashier POS:"
echo "   - Stock should update in real-time WITHOUT refresh"
echo "   - You should see the new quantity immediately"
echo ""
echo "5. Check Browser Console (F12):"
echo "   Admin should show: 'Broadcasting stock update'"
echo "   Cashier should show: '📦 Stock update received'"
echo ""

echo "================================"
echo "DEBUGGING TIPS"
echo "================================"
echo ""
echo "If stock updates don't work:"
echo ""
echo "1. Check WebSocket connection in browser DevTools:"
echo "   - F12 → Network → WS"
echo "   - Should see active WebSocket connection"
echo ""
echo "2. Check browser console for errors:"
echo "   - Look for 'WebSocket connected' message"
echo "   - Look for 'Stock update received' messages"
echo ""
echo "3. Check backend logs:"
echo "   - Should see 'Connection registered' when clients connect"
echo "   - Should see 'Broadcasting stock update' when stock changes"
echo ""
echo "4. Verify token is present:"
echo "   Open console and run: localStorage.getItem('token')"
echo "   Should return a JWT token"
echo ""
echo "5. Check sync_manager connections:"
echo "   In Python console: print(sync_manager.connections)"
echo "   Should show active connections per account"
echo ""
echo "================================"
echo "See STOCK_UPDATE_GUIDE.md for complete documentation"
echo "================================"
