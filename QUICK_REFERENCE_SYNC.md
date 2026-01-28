# QUICK REFERENCE - REAL-TIME SYNC

## Backend Status
```bash
# Check if backend is running
ps aux | grep "python3 app.py" | grep -v grep

# Check backend health
curl http://localhost:5000/api/health

# View logs
tail -f /home/ian-mabruk/universal/backend/logs/app.log

# Restart backend
pkill -f "python3 app.py"
cd /home/ian-mabruk/universal/backend
python3 app.py > logs/app.log 2>&1 &
```

## What Was Fixed

### 1. Clock-In Error 500 ✅
- **Problem**: Backend authentication failing with legacy data
- **Solution**: Added support for plain text passwords and field name variations
- **Test**: Click "Clock In" in cashier dashboard - should work or show "Already clocked in"

### 2. Stock Updates Not Syncing ✅
- **Problem**: Admin stock changes not appearing in cashier products
- **Solution**: Added event dispatching + 10s polling
- **Test**: 
  1. Admin: Add stock to a product
  2. Cashier: Check products tab within 10 seconds
  3. Stock should be updated

### 3. Monitor Dashboard Not Updating ✅
- **Problem**: Sales/expenses not triggering monitor updates
- **Solution**: Added event listeners for sales and expenses + 3s polling
- **Test**:
  1. Complete a sale in cashier POS
  2. Check monitor tab - updates immediately
  3. Add an expense
  4. Check monitor tab - updates immediately

## Real-Time Events

### Events Dispatched
- `sale_completed` - After sale completion
- `expense_added` - After expense creation
- `stock_updated` - After stock addition
- `productsSync` - After product list refresh
- `productUpdated` - After product modification
- `productCreated` - After product creation

### Components Listening
- **GenericCashierPOS**: Listens to all product events + 10s poll
- **MonitorDashboard**: Listens to sale/expense events + 3s poll

## Polling Intervals
- **Products**: 10 seconds
- **Monitor Stats**: 3 seconds
- **Inventory**: On-demand (no polling)

## Backend PID
Current: 31117

## Test Credentials
- Email: hub@gmail.com
- Password: 345678
- Role: admin
