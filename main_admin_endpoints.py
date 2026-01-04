# Main Admin Endpoints
from flask import request, jsonify
from datetime import datetime
import jwt
from functools import wraps

def create_main_admin_routes(app, safe_load_json, safe_save_json, token_required):
    
    @app.route('/api/main-admin/auth/login', methods=['POST'])
    def main_admin_login():
        """Main admin login endpoint - Only ianmabruk3@gmail.com allowed"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'Request data is required'}), 400
            
            email = data.get('email', '').strip().lower()
            password = data.get('password', '')
            
            if not email or not password:
                return jsonify({'error': 'Email and password are required'}), 400
            
            # Only allow ianmabruk3@gmail.com with password admin123
            if email == 'ianmabruk3@gmail.com' and password == 'admin123':
                token_data = {
                    'id': 'main_admin',
                    'email': email,
                    'type': 'main_admin',
                    'role': 'main_admin'
                }
                token = jwt.encode(token_data, app.config['SECRET_KEY'], algorithm='HS256')
                
                return jsonify({
                    'token': token,
                    'user': {
                        'id': 'main_admin',
                        'email': email,
                        'name': 'Ian Mabruk',
                        'type': 'main_admin',
                        'role': 'main_admin'
                    }
                })
            
            return jsonify({'error': 'Access denied. Owner access only.'}), 401
            
        except Exception as e:
            print(f"Main admin login error: {e}")
            return jsonify({'error': f'Login failed: {str(e)}'}), 500

    @app.route('/api/main-admin/users', methods=['GET'])
    @token_required
    def main_admin_get_users():
        """Get all users for main admin"""
        try:
            if request.user.get('type') != 'main_admin':
                return jsonify({'error': 'Main admin access required'}), 403
            
            users = safe_load_json('users.json')
            # Add trial status calculation
            for user in users:
                if user.get('plan') == 'trial' or not user.get('plan'):
                    user['isFreeTrial'] = True
                    if user.get('trialExpiry'):
                        try:
                            expiry = datetime.fromisoformat(user['trialExpiry'])
                            user['trialDaysLeft'] = max(0, (expiry - datetime.now()).days)
                        except:
                            user['trialDaysLeft'] = 0
                    else:
                        user['trialDaysLeft'] = 30  # Default trial period
                else:
                    user['isFreeTrial'] = False
                    user['trialDaysLeft'] = 0
            
            return jsonify([{k: v for k, v in u.items() if k != 'password'} for u in users])
            
        except Exception as e:
            print(f"Main admin get users error: {e}")
            return jsonify({'error': f'Operation failed: {str(e)}'}), 500

    @app.route('/api/main-admin/activities', methods=['GET'])
    @token_required
    def main_admin_get_activities():
        """Get all user activities for main admin"""
        try:
            if request.user.get('type') != 'main_admin':
                return jsonify({'error': 'Main admin access required'}), 403
            
            activities = safe_load_json('activities.json')
            # Sort by timestamp (newest first)
            activities.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            return jsonify(activities)
            
        except Exception as e:
            print(f"Get activities error: {e}")
            return jsonify({'error': f'Operation failed: {str(e)}'}), 500

    @app.route('/api/main-admin/stats', methods=['GET'])
    @token_required
    def main_admin_get_stats():
        """Get global statistics for main admin"""
        try:
            if request.user.get('type') != 'main_admin':
                return jsonify({'error': 'Main admin access required'}), 403
            
            users = safe_load_json('users.json')
            sales = safe_load_json('sales.json')
            activities = safe_load_json('activities.json')
            payments = safe_load_json('payments.json')
            
            # Calculate user stats
            total_users = len(users)
            active_users = len([u for u in users if u.get('active', True) and not u.get('locked', False)])
            locked_users = len([u for u in users if u.get('locked', False)])
            trial_users = len([u for u in users if not u.get('plan') or u.get('plan') == 'trial'])
            
            # Plan distribution
            plan_counts = {'basic': 0, 'ultra': 0, 'trial': 0}
            revenue_by_plan = {'basic': 0, 'ultra': 0}
            
            for user in users:
                plan = user.get('plan', 'trial')
                if plan in plan_counts:
                    plan_counts[plan] += 1
                    if plan in revenue_by_plan:
                        revenue_by_plan[plan] += user.get('price', 0)
                elif not plan:
                    plan_counts['trial'] += 1
            
            # Activity stats
            total_signups = len([a for a in activities if a.get('type') == 'signup'])
            total_logins = len([a for a in activities if a.get('type') == 'login'])
            
            # Recent activity (last 7 days)
            week_ago = datetime.now() - datetime.timedelta(days=7)
            recent_signups = len([a for a in activities if a.get('type') == 'signup' and 
                                datetime.fromisoformat(a.get('timestamp', '')) > week_ago])
            
            # Sales stats
            total_sales = sum(sale.get('total', 0) for sale in sales)
            total_transactions = len(sales)
            
            # Payment stats
            total_revenue = sum(p.get('amount', 0) for p in payments if p.get('status') == 'approved')
            mrr = revenue_by_plan['basic'] + revenue_by_plan['ultra']  # Monthly recurring revenue
            
            return jsonify({
                'totalUsers': total_users,
                'activeUsers': active_users,
                'lockedUsers': locked_users,
                'trialUsers': trial_users,
                'planDistribution': plan_counts,
                'totalSignups': total_signups,
                'totalLogins': total_logins,
                'recentSignups': recent_signups,
                'totalSales': total_sales,
                'totalTransactions': total_transactions,
                'totalRevenue': total_revenue,
                'mrr': mrr,
                'revenueByPlan': revenue_by_plan
            })
            
        except Exception as e:
            print(f"Get main admin stats error: {e}")
            return jsonify({'error': f'Operation failed: {str(e)}'}), 500

    @app.route('/api/main-admin/users/<int:user_id>/lock', methods=['POST'])
    @token_required
    def main_admin_lock_user(user_id):
        """Lock/unlock user by main admin"""
        try:
            if request.user.get('type') != 'main_admin':
                return jsonify({'error': 'Main admin access required'}), 403
            
            data = request.get_json()
            if not data or 'locked' not in data:
                return jsonify({'error': 'Locked status is required'}), 400
            
            locked = bool(data['locked'])
            
            users = safe_load_json('users.json')
            user = next((u for u in users if u['id'] == user_id), None)
            
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            user['locked'] = locked
            user['active'] = not locked
            
            # Log the action
            activities = safe_load_json('activities.json')
            activity = {
                'id': len(activities) + 1,
                'type': 'admin_action',
                'action': 'user_locked' if locked else 'user_unlocked',
                'targetUserId': user_id,
                'targetUserEmail': user['email'],
                'adminId': 'main_admin',
                'adminEmail': 'ianmabruk3@gmail.com',
                'timestamp': datetime.now().isoformat()
            }
            activities.append(activity)
            
            if not safe_save_json('users.json', users):
                return jsonify({'error': 'Failed to update user status'}), 500
            
            safe_save_json('activities.json', activities)
            
            return jsonify({
                'message': f'User {"locked" if locked else "unlocked"} successfully',
                'user': {k: v for k, v in user.items() if k != 'password'}
            })
            
        except Exception as e:
            print(f"Main admin lock user error: {e}")
            return jsonify({'error': f'Operation failed: {str(e)}'}), 500

    @app.route('/api/main-admin/users/<int:user_id>/plan', methods=['POST'])
    @token_required
    def main_admin_change_plan(user_id):
        """Change user plan by main admin"""
        try:
            if request.user.get('type') != 'main_admin':
                return jsonify({'error': 'Main admin access required'}), 403
            
            data = request.get_json()
            if not data or 'plan' not in data:
                return jsonify({'error': 'Plan is required'}), 400
            
            new_plan = data['plan']
            if new_plan not in ['trial', 'basic', 'ultra']:
                return jsonify({'error': 'Invalid plan'}), 400
            
            users = safe_load_json('users.json')
            user = next((u for u in users if u['id'] == user_id), None)
            
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            old_plan = user.get('plan', 'trial')
            user['plan'] = new_plan
            
            # Update price based on plan
            if new_plan == 'basic':
                user['price'] = 1000
            elif new_plan == 'ultra':
                user['price'] = 2400
            else:  # trial
                user['price'] = 0
            
            # Log the action
            activities = safe_load_json('activities.json')
            activity = {
                'id': len(activities) + 1,
                'type': 'admin_action',
                'action': 'plan_changed',
                'targetUserId': user_id,
                'targetUserEmail': user['email'],
                'oldPlan': old_plan,
                'newPlan': new_plan,
                'adminId': 'main_admin',
                'adminEmail': 'ianmabruk3@gmail.com',
                'timestamp': datetime.now().isoformat()
            }
            activities.append(activity)
            
            if not safe_save_json('users.json', users):
                return jsonify({'error': 'Failed to update user plan'}), 500
            
            safe_save_json('activities.json', activities)
            
            return jsonify({
                'message': f'User plan changed from {old_plan} to {new_plan}',
                'user': {k: v for k, v in user.items() if k != 'password'}
            })
            
        except Exception as e:
            print(f"Main admin change plan error: {e}")
            return jsonify({'error': f'Operation failed: {str(e)}'}), 500

    @app.route('/api/main-admin/system/clear-data', methods=['POST'])
    @token_required
    def main_admin_clear_data():
        """Clear system data by main admin"""
        try:
            if request.user.get('type') != 'main_admin':
                return jsonify({'error': 'Main admin access required'}), 403
            
            data = request.get_json()
            clear_type = data.get('type', 'all')
            
            files_cleared = []
            
            if clear_type in ['sales', 'all']:
                if safe_save_json('sales.json', []):
                    files_cleared.append('sales')
            
            if clear_type in ['expenses', 'all']:
                if safe_save_json('expenses.json', []):
                    files_cleared.append('expenses')
            
            if clear_type in ['products', 'all']:
                if safe_save_json('products.json', []):
                    files_cleared.append('products')
                if safe_save_json('batches.json', []):
                    files_cleared.append('batches')
            
            # Log the action
            activities = safe_load_json('activities.json')
            activity = {
                'id': len(activities) + 1,
                'type': 'admin_action',
                'action': 'data_cleared',
                'clearType': clear_type,
                'filesCleared': files_cleared,
                'adminId': 'main_admin',
                'adminEmail': 'ianmabruk3@gmail.com',
                'timestamp': datetime.now().isoformat()
            }
            activities.append(activity)
            safe_save_json('activities.json', activities)
            
            return jsonify({
                'message': f'Successfully cleared {clear_type} data',
                'filesCleared': files_cleared
            })
            
        except Exception as e:
            print(f"Main admin clear data error: {e}")
            return jsonify({'error': f'Operation failed: {str(e)}'}), 500