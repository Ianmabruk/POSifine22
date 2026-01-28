# type: ignore
# pyright: reportUndefinedVariable=false
# pylance: disable
"""
================================================================================
INTEGRATION GUIDE FOR POS SYSTEM REBUILD INTO app.py
================================================================================

This file shows EXACTLY where to modify app.py to use the new architecture.
This is a DOCUMENTATION FILE with code examples, not executable code.

KEY CHANGES:
1. Replace /api/sales POST endpoint with SaleService
2. Add /api/stats endpoint with AnalyticsService
3. Add /api/products/low-stock-warnings endpoint with LowStockService
4. Update frontend Complete Sale button to use immediate response
5. Update AdminDashboard to poll /api/stats every 5 seconds

================================================================================
"""

# ============================================================================
# STEP 1: ADD THESE IMPORTS TO TOP OF app.py
# ============================================================================

# from pos_system_rebuild import (
#     SaleService, AnalyticsService, LowStockService, 
#     AtomicTransactionManager
# )

# # Initialize services on app startup
# sale_service = SaleService(DATA_DIR)
# analytics_service = AnalyticsService(DATA_DIR)
# low_stock_service = LowStockService(DATA_DIR, threshold=1.0)


# ============================================================================
# STEP 2: REPLACE /api/sales POST endpoint (around line 2285)
# ============================================================================

"""
OLD CODE (REMOVE):
    @app.route('/api/sales', methods=['GET', 'POST', 'OPTIONS'])
    @token_required
    def handle_sales():
        # ...complex logic with async stock deduction...

NEW CODE (REPLACE WITH):
"""

@app.route('/api/sales', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def handle_sales():
    """
    ULTRA-FAST COMPLETE SALE ENDPOINT
    - Returns immediately (<50ms typical)
    - Stock deducted atomically
    - No hanging states
    """
    if request.method == 'OPTIONS':
        return '', 200
    
    if request.method == 'GET':
        # GET: Return sales list
        sales = load_data_cached(SALES_FILE, use_cache=True)
        account_id = request.user.get('accountId')
        filtered_sales = [s for s in sales if s.get('accountId') == account_id]
        return jsonify(filtered_sales), 200
    
    # POST: Create new sale with ATOMIC stock deduction
    try:
        start_time = time.time()
        data = request.get_json()
        
        if not data or not data.get('items') or len(data['items']) == 0:
            return jsonify({
                'success': False,
                'error': 'Cart cannot be empty',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # USE UNIFIED SALE SERVICE - atomic operation
        success, error_msg, result = sale_service.complete_sale(
            items=data['items'],
            total=float(data['total']),
            account_id=request.user['accountId'],
            cashier_id=request.user['id'],
            cashier_name=request.user.get('name', 'Cashier'),
            discount=float(data.get('discount', 0)),
            tax=float(data.get('tax', 0)),
            taxType=data.get('taxType', 'exclusive'),
            paymentMethod=data.get('paymentMethod', 'cash')
        )
        
        if not success:
            return jsonify({
                'success': False,
                'error': error_msg,
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # INSTANT SUCCESS RESPONSE
        elapsed_ms = (time.time() - start_time) * 1000
        
        # Check for low stock warnings
        warnings = low_stock_service.check_low_stock(request.user['accountId'])
        
        # Broadcast updates to all connected clients
        broadcast_update('sale_completed', {
            'saleId': result['saleId'],
            'deductions': result['stockDeductions'],
            'timestamp': datetime.now().isoformat(),
            'lowStockWarnings': warnings['warnings']
        }, account_id=request.user['accountId'])
        
        return jsonify({
            'success': True,
            'saleId': result['saleId'],
            'total': result['sale']['total'],
            'stockDeductions': result['stockDeductions'],
            'processingTime': result['processingTime'],
            'lowStockWarnings': warnings['warnings'],
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        import traceback
        print(f"❌ Sale error: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


# ============================================================================
# STEP 3: REPLACE /api/admin-complete-sale endpoint (around line 2419)
# ============================================================================

"""
OLD CODE: /api/admin-complete-sale with complex async logic

NEW CODE: Just call the same SaleService for consistency
"""

@app.route('/api/admin-complete-sale', methods=['POST', 'OPTIONS'])
@token_required
def admin_complete_sale_v2():
    """
    Admin Complete Sale - uses same SaleService
    Returns instantly with updated stock
    """
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        start_time = time.time()
        data = request.get_json()
        
        if not data or not data.get('items'):
            return jsonify({
                'success': False,
                'error': 'Items required',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # SAME atomic service
        success, error_msg, result = sale_service.complete_sale(
            items=data['items'],
            total=float(data['total']),
            account_id=request.user['accountId'],
            cashier_id=request.user['id'],
            cashier_name=request.user.get('name', 'Admin'),
            **data  # Include all optional parameters
        )
        
        if not success:
            return jsonify({
                'success': False,
                'error': error_msg,
                'timestamp': datetime.now().isoformat()
            }), 400
        
        elapsed_ms = (time.time() - start_time) * 1000
        warnings = low_stock_service.check_low_stock(request.user['accountId'])
        
        broadcast_update('admin_sale_completed', {
            'saleId': result['saleId'],
            'deductions': result['stockDeductions'],
            'warnings': warnings['warnings']
        }, account_id=request.user['accountId'])
        
        return jsonify({
            'success': True,
            'saleId': result['saleId'],
            'stockDeductions': result['stockDeductions'],
            'processingTime': f"{elapsed_ms:.2f}ms",
            'lowStockWarnings': warnings['warnings'],
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


# ============================================================================
# STEP 4: REPLACE /api/stats endpoint (around line 2947)
# ============================================================================

"""
OLD CODE:
    @app.route('/api/stats', methods=['GET', 'OPTIONS'])
    @token_required
    def stats():
        # ...complex calculations...

NEW CODE: Use AnalyticsService for instant totals
"""

@app.route('/api/stats', methods=['GET', 'OPTIONS'])
@token_required
def stats_v2():
    """
    GET LIVE TOTALS INSTANTLY
    Returns: {totalSales, totalExpenses, netProfit, ...}
    
    Frontend should call this every 5 seconds for live dashboard
    """
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        account_id = request.user.get('accountId')
        totals = analytics_service.get_totals(account_id)
        
        return jsonify({
            'success': True,
            'data': totals,
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


# ============================================================================
# STEP 5: ADD NEW /api/products/low-stock-warnings endpoint
# ============================================================================

@app.route('/api/products/low-stock-warnings', methods=['GET', 'OPTIONS'])
@token_required
def get_low_stock_warnings_v2():
    """
    GET ALL LOW STOCK WARNINGS
    Cashier and Admin can use this to show alerts
    """
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        account_id = request.user.get('accountId')
        threshold = request.args.get('threshold', 1.0, type=float)
        
        warnings = low_stock_service.check_low_stock(account_id)
        
        return jsonify({
            'success': True,
            'data': warnings,
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


# ============================================================================
# STEP 6: UPDATE FRONTEND - CashierPOS.jsx handleCheckout function
# ============================================================================

"""
NEW REACT CODE (Replace handleCheckout in CashierPOS.jsx):

const handleCheckout = async () => {
  if (cart.length === 0 || checkoutLoading) return;
  
  setCheckoutLoading(true);
  
  try {
    const response = await fetch(`${BASE_API_URL}/sales`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        items: cart.map(item => ({
          productId: item.id,
          quantity: item.quantity
        })),
        total: finalTotal,
        discount: discountValue,
        tax: tax,
        taxType: taxType,
        paymentMethod: paymentMethod
      })
    });
    
    const data = await response.json();
    
    if (!data.success) {
      alert(`❌ Sale failed: ${data.error}`);
      return;
    }
    
    // INSTANT SUCCESS - show message immediately
    alert(`✅ SALE COMPLETE!\nSale ID: #${data.saleId}\nAmount: KES ${data.total}\nProcessing Time: ${data.processingTime}`);
    
    // Show low stock warnings if any
    if (data.lowStockWarnings && data.lowStockWarnings.length > 0) {
      const warnings_str = data.lowStockWarnings
        .map(w => `⚠️ ${w.productName}: ${w.currentStock}${w.unit}`)
        .join('\n');
      alert(`Low Stock:\n${warnings_str}`);
    }
    
    // Clear cart
    setCart([]);
    setSelectedDiscount(null);
    setTaxType('exclusive');
    
    // Refresh products in background
    refreshProducts();
  } catch (error) {
    alert(`❌ Sale failed: ${error.message}`);
  } finally {
    setCheckoutLoading(false);
  }
};
"""


# ============================================================================
# STEP 7: UPDATE FRONTEND - AdminDashboard.jsx stats polling
# ============================================================================

"""
NEW REACT CODE (Add to AdminDashboard.jsx):

useEffect(() => {
  // Poll /api/stats every 5 seconds for live totals
  const statsInterval = setInterval(async () => {
    try {
      const response = await fetch(`${BASE_API_URL}/stats`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      const result = await response.json();
      
      if (result.success) {
        setData(prev => ({
          ...prev,
          stats: result.data
        }));
      }
    } catch (error) {
      console.warn('Stats update failed:', error);
    }
  }, 5000);  // Every 5 seconds
  
  return () => clearInterval(statsInterval);
}, []);
"""


# ============================================================================
# STEP 8: ADD LOW-STOCK ALERT COMPONENT
# ============================================================================

"""
NEW REACT COMPONENT (Create LowStockAlert.jsx):

import { AlertTriangle } from 'lucide-react';

export default function LowStockAlert({ warnings, dismissible = true }) {
  const [dismissed, setDismissed] = useState(false);
  
  if (!warnings || warnings.length === 0 || dismissed) return null;
  
  return (
    <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-4 rounded">
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-red-600 mt-0.5 flex-shrink-0" />
        <div className="flex-1">
          <h3 className="font-bold text-red-800">⚠️ Low Stock Alert</h3>
          <div className="mt-2 text-sm text-red-700">
            {warnings.map(w => (
              <div key={w.productId}>
                {w.productName}: {w.currentStock}{w.unit} left
                (Threshold: {w.threshold}{w.unit})
              </div>
            ))}
          </div>
        </div>
        {dismissible && (
          <button
            onClick={() => setDismissed(true)}
            className="text-red-600 hover:text-red-800"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
}

// USE IN CashierPOS.jsx:
<LowStockAlert warnings={lowStockWarnings} />
"""


print("""
================================================================================
INTEGRATION CHECKLIST
================================================================================

✅ BACKEND CHANGES:
  [ ] 1. Import SaleService, AnalyticsService, LowStockService at top of app.py
  [ ] 2. Initialize services on startup
  [ ] 3. Replace /api/sales POST endpoint with SaleService
  [ ] 4. Replace /api/admin-complete-sale with same SaleService
  [ ] 5. Replace /api/stats with AnalyticsService
  [ ] 6. Add /api/products/low-stock-warnings endpoint
  [ ] 7. Test endpoints return responses in <100ms

✅ FRONTEND CHANGES:
  [ ] 8. Update CashierPOS.jsx handleCheckout() to handle instant responses
  [ ] 9. Update AdminDashboard.jsx to poll /api/stats every 5 seconds
  [ ] 10. Create LowStockAlert component and show warnings
  [ ] 11. Test Complete Sale button - should NEVER hang
  [ ] 12. Test dashboard totals update live without page refresh

✅ TESTING:
  [ ] 13. Test 1: Create sale and verify stock deducts immediately
  [ ] 14. Test 2: Create multiple sales and verify no race conditions
  [ ] 15. Test 3: Check low stock warnings appear correctly
  [ ] 16. Test 4: Verify admin dashboard totals update live
  [ ] 17. Test 5: Measure all endpoint response times (<100ms)

✅ DEPLOYMENT:
  [ ] 18. Deploy changes to production
  [ ] 19. Monitor for any issues
  [ ] 20. Rate system on 1-100 scale (target: 99.99)

================================================================================
""")
