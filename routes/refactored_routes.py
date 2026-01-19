"""
NEW UNIFIED API ROUTES
======================

Refactored endpoints using centralized services:
- /api/sales (cashier checkout)
- /api/admin-complete-sale (admin dashboard sale)
- /api/shifts/clock-in (unified shift system)
- /api/shifts/clock-out
- /api/shifts/status

This replaces fragmented endpoints with clean, consistent service calls.
"""

from flask import jsonify, request
from functools import wraps
from datetime import datetime


def create_sales_routes(app, sales_service, shift_service, notification_service, token_required):
    """
    Register all sales endpoints.
    
    Args:
        app: Flask app instance
        sales_service: SalesService instance
        shift_service: ShiftService instance  
        notification_service: NotificationService instance
        token_required: JWT auth decorator
    """
    
    @app.route('/api/sales', methods=['GET', 'POST', 'OPTIONS'])
    @token_required
    def handle_sales():
        """
        GET: Fetch sales for account
        POST: Create new sale (cashier checkout) with immediate stock deduction
        """
        if request.method == 'OPTIONS':
            return '', 200
        
        if request.method == 'GET':
            # Get all sales for this account
            try:
                sales = sales_service.data_store.load('sales')
                account_id = request.user.get('accountId')
                
                filtered = [s for s in (sales or []) if s.get('accountId') == account_id]
                return jsonify(filtered)
            except Exception as e:
                print(f"Error fetching sales: {e}")
                return jsonify({'error': str(e)}), 500
        
        # POST - Create sale
        try:
            data = request.get_json()
            
            # Call centralized sales service
            success, error_msg, response = sales_service.complete_sale(
                user_id=request.user['id'],
                user_name=request.user.get('name', 'Unknown'),
                account_id=request.user['accountId'],
                items=data.get('items', []),
                total=float(data.get('total', 0)),
                payment_method=data.get('paymentMethod', 'cash'),
                discount=float(data.get('discount', 0)),
                tax=float(data.get('tax', 0)),
                tax_type=data.get('taxType', 'exclusive'),
                completed_by='cashier'
            )
            
            if not success:
                return jsonify({'error': error_msg}), 400
            
            return jsonify({
                'success': True,
                **response
            })
        
        except Exception as e:
            print(f"❌ Sale creation error: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': 'Failed to create sale', 'message': str(e)}), 500
    
    
    @app.route('/api/admin-complete-sale', methods=['POST', 'OPTIONS'])
    @token_required
    def admin_complete_sale():
        """
        Admin dashboard - Complete sale with immediate sharp stock deduction.
        Uses same centralized sales service as /api/sales.
        """
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            data = request.get_json()
            
            # Call same service as cashier, but mark as 'admin'
            success, error_msg, response = sales_service.complete_sale(
                user_id=request.user['id'],
                user_name=request.user.get('name', 'Unknown'),
                account_id=request.user['accountId'],
                items=data.get('items', []),
                total=float(data.get('total', 0)),
                payment_method=data.get('paymentMethod', 'cash'),
                discount=float(data.get('discount', 0)),
                tax=float(data.get('tax', 0)),
                tax_type=data.get('taxType', 'exclusive'),
                completed_by='admin'  # ← Audit trail
            )
            
            if not success:
                return jsonify({'error': error_msg}), 400
            
            return jsonify({
                'success': True,
                **response
            })
        
        except Exception as e:
            print(f"❌ Admin sale error: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': 'Failed to complete sale', 'message': str(e)}), 500


def create_shift_routes(app, shift_service, notification_service, token_required):
    """
    Register all shift/clock endpoints.
    
    Args:
        app: Flask app instance
        shift_service: ShiftService instance
        notification_service: NotificationService instance
        token_required: JWT auth decorator
    """
    
    @app.route('/api/shifts/clock-in', methods=['POST', 'OPTIONS'])
    @token_required
    def clock_in():
        """Clock in - create new shift"""
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            user_id = request.user['id']
            user_name = request.user.get('name', 'Unknown')
            account_id = request.user['accountId']
            
            # Use unified shift service
            success, error_msg, shift = shift_service.clock_in(user_id, user_name, account_id)
            
            if not success:
                return jsonify({'error': error_msg}), 400
            
            # Broadcast to dashboards
            notification_service.broadcast_shift_event(account_id, shift, 'shift_opened')
            
            return jsonify({
                'success': True,
                'shift': shift,
                'message': f'Clocked in at {shift["clockInTime"]}'
            }), 201
        
        except Exception as e:
            print(f"❌ Clock-in error: {str(e)}")
            return jsonify({'error': 'Clock-in failed', 'message': str(e)}), 500
    
    
    @app.route('/api/shifts/clock-out', methods=['POST', 'OPTIONS'])
    @token_required
    def clock_out():
        """Clock out - close current shift"""
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            user_id = request.user['id']
            account_id = request.user['accountId']
            
            # Use unified shift service
            success, error_msg, shift = shift_service.clock_out(user_id, account_id)
            
            if not success:
                return jsonify({'error': error_msg}), 400
            
            # Broadcast to dashboards
            notification_service.broadcast_shift_event(account_id, shift, 'shift_closed')
            
            return jsonify({
                'success': True,
                'shift': shift,
                'displayDuration': shift.get('durationDisplay'),
                'message': f"Clocked out. Total time: {shift['durationDisplay']}"
            })
        
        except Exception as e:
            print(f"❌ Clock-out error: {str(e)}")
            return jsonify({'error': 'Clock-out failed', 'message': str(e)}), 500
    
    
    @app.route('/api/shifts/status', methods=['GET', 'OPTIONS'])
    @token_required
    def get_shift_status():
        """Get current shift status for user"""
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            user_id = request.user['id']
            account_id = request.user['accountId']
            
            shift = shift_service.get_active_shift(user_id, account_id)
            
            if shift:
                return jsonify({
                    'isClockedIn': True,
                    'shift': shift,
                    'clockInTime': shift['clockInTime'],
                    'elapsedDisplay': shift.get('elapsedDisplay')
                })
            else:
                return jsonify({
                    'isClockedIn': False,
                    'message': 'Not currently clocked in'
                })
        
        except Exception as e:
            print(f"❌ Clock status error: {str(e)}")
            return jsonify({'error': 'Failed to get clock status', 'message': str(e)}), 500
    
    
    @app.route('/api/shifts', methods=['GET', 'OPTIONS'])
    @token_required
    def get_shifts():
        """Get all shifts for current user"""
        if request.method == 'OPTIONS':
            return '', 200
        
        try:
            user_id = request.user['id']
            account_id = request.user['accountId']
            limit = request.args.get('limit', 50, type=int)
            
            shifts = shift_service.get_user_shifts(user_id, account_id, limit)
            
            return jsonify(shifts)
        
        except Exception as e:
            print(f"❌ Error fetching shifts: {str(e)}")
            return jsonify({'error': 'Failed to fetch shifts', 'message': str(e)}), 500


# Integration function to set up all routes
def setup_routes(app, services_dict, token_required):
    """
    Set up all refactored routes.
    
    Args:
        app: Flask app
        services_dict: {
            'sales': SalesService,
            'shift': ShiftService,
            'notification': NotificationService
        }
        token_required: JWT decorator
    """
    sales_service = services_dict.get('sales')
    shift_service = services_dict.get('shift')
    notification_service = services_dict.get('notification')
    
    if not all([sales_service, shift_service, notification_service]):
        print("❌ Error: Not all required services provided")
        return
    
    create_sales_routes(app, sales_service, shift_service, notification_service, token_required)
    create_shift_routes(app, shift_service, notification_service, token_required)
    
    print("✅ Refactored routes registered")
