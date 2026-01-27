"""
ADMIN CONTROLLER
================
Admin dashboard features:
- Dashboard statistics (sales, profit, expenses)
- Inventory management (products, stock)
- User management (cashiers, time tracking)
- Vendors management
- Reminders system
- Credit requests approval/rejection
- Service fees and discounts
"""

from flask import jsonify, request
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class AdminController:
    """Admin dashboard controller"""
    
    def __init__(self, datastore, stock_engine):
        """
        Initialize admin controller
        
        Args:
            datastore: DataStore instance
            stock_engine: StockEngine instance
        """
        self.ds = datastore
        self.stock = stock_engine
    
    # ============================================================
    # DASHBOARD STATISTICS
    # ============================================================
    
    def get_dashboard_stats(self, account_id: str, period: str = 'all') -> Dict:
        """
        Get comprehensive dashboard statistics
        
        OPTIMIZED: Single-pass data aggregation to avoid N+1 queries
        
        Args:
            account_id: Account ID
            period: 'today', 'week', 'month', 'all'
        
        Returns:
            Dashboard statistics dict
        """
        try:
            # Calculate date range
            now = datetime.now()
            if period == 'today':
                start_date = now.replace(hour=0, minute=0, second=0).isoformat()
                end_date = now.isoformat()
            elif period == 'week':
                start_date = (now - timedelta(days=7)).isoformat()
                end_date = now.isoformat()
            elif period == 'month':
                start_date = (now - timedelta(days=30)).isoformat()
                end_date = now.isoformat()
            else:  # all
                start_date = '2000-01-01'
                end_date = now.isoformat()
            
            # OPTIMIZATION: Load all data in parallel using single queries
            # This prevents N+1 query problems
            
            # Get sales with date filtering (single query)
            sales = self.ds.get_sales_by_date_range(account_id, start_date, end_date)
            
            # Calculate totals in single pass (in-memory aggregation)
            total_sales = 0.0
            total_cost = 0.0
            gross_profit = 0.0
            
            for s in sales:
                total_sales += s.get('total', 0)
                total_cost += s.get('total_cost', 0)
                gross_profit += s.get('gross_profit', 0)
            
            # Get expenses (single query)
            expenses = self.ds.get_all('expenses', account_id)
            expenses = [e for e in expenses if start_date <= e.get('created_at', '') <= end_date]
            total_expenses = sum(e.get('amount', 0) for e in expenses)
            
            # Net profit = gross profit - expenses
            net_profit = gross_profit - total_expenses
            
            # Recent sales (limit 10, already sorted by date in query)
            recent_sales = sorted(
                sales,
                key=lambda x: x.get('created_at', ''),
                reverse=True
            )[:10]
            
            # Low stock products (single query, in-memory filtering)
            low_stock = self.stock.get_low_stock_products(account_id)
            
            # Products count (single query)
            products = self.ds.get_all('products', account_id)
            total_products = len(products)
            
            return {
                'total_sales': round(total_sales, 2),
                'total_cost': round(total_cost, 2),
                'gross_profit': round(gross_profit, 2),
                'total_expenses': round(total_expenses, 2),
                'net_profit': round(net_profit, 2),
                'sales_count': len(sales),
                'recent_sales': recent_sales,
                'low_stock_count': len(low_stock),
                'low_stock_products': low_stock,
                'total_products': total_products,
                'period': period
            }
            
        except Exception as e:
            logger.error(f"Error getting dashboard stats: {e}")
            return {}
    
    def get_sales_analytics(self, account_id: str) -> Dict:
        """Get detailed sales analytics"""
        try:
            now = datetime.now()
            
            # Today's sales
            today_start = now.replace(hour=0, minute=0, second=0).isoformat()
            today_sales = self.ds.get_sales_by_date_range(account_id, today_start, now.isoformat())
            today_total = sum(s.get('total', 0) for s in today_sales)
            
            # This week's sales
            week_start = (now - timedelta(days=7)).isoformat()
            week_sales = self.ds.get_sales_by_date_range(account_id, week_start, now.isoformat())
            week_total = sum(s.get('total', 0) for s in week_sales)
            
            # This month's sales
            month_start = (now - timedelta(days=30)).isoformat()
            month_sales = self.ds.get_sales_by_date_range(account_id, month_start, now.isoformat())
            month_total = sum(s.get('total', 0) for s in month_sales)
            
            # All time
            all_sales = self.ds.get_all('sales', account_id)
            all_time_total = sum(s.get('total', 0) for s in all_sales)
            
            return {
                'today': {
                    'total': round(today_total, 2),
                    'count': len(today_sales)
                },
                'week': {
                    'total': round(week_total, 2),
                    'count': len(week_sales)
                },
                'month': {
                    'total': round(month_total, 2),
                    'count': len(month_sales)
                },
                'all_time': {
                    'total': round(all_time_total, 2),
                    'count': len(all_sales)
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting sales analytics: {e}")
            return {}
    
    # ============================================================
    # PRODUCT/INVENTORY MANAGEMENT
    # ============================================================
    
    def create_product(
        self,
        account_id: str,
        name: str,
        price: float,
        cost: float = 0.0,
        quantity: float = 0.0,
        product_type: str = 'regular',
        category: str = 'general',
        unit: str = 'pcs',
        image: Optional[str] = None,
        is_composite: bool = False,
        recipe: Optional[List[Dict]] = None,
        created_by: Optional[int] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """Create new product"""
        try:
            product_data = {
                'account_id': account_id,
                'name': name,
                'price': price,
                'cost': cost,
                'quantity': quantity,
                'product_type': product_type,
                'category': category,
                'unit': unit,
                'image': image,
                'is_composite': is_composite,
                'recipe': recipe or [],
                'reorder_level': 0.0,
                'max_stock_level': 0.0,
                'cost_per_unit': cost,
                'enable_weight_pricing': False,
                'created_at': datetime.now().isoformat(),
                'created_by': created_by
            }
            
            product = self.ds.create('products', product_data)
            return True, None, product
            
        except Exception as e:
            logger.error(f"Error creating product: {e}")
            return False, f"Failed to create product: {str(e)}", None
    
    def update_product(
        self,
        product_id: int,
        account_id: str,
        updates: Dict
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """Update product"""
        try:
            # CRITICAL: Never allow quantity to be updated via product edit
            # Stock must ONLY be updated via adjust_stock or batch_update_stock
            # This prevents accidental stock resets
            if 'quantity' in updates:
                # Get current product to preserve quantity
                current_product = self.ds.get_by_id('products', product_id, account_id)
                if current_product:
                    # Preserve existing quantity unless explicitly zero (new product scenario)
                    if current_product.get('quantity', 0) > 0:
                        logger.warning(f"Attempted to update quantity via product edit for product {product_id}. Preserving existing quantity.")
                        updates['quantity'] = current_product['quantity']
            
            updates['updated_at'] = datetime.now().isoformat()
            success = self.ds.update('products', product_id, updates, account_id)
            
            if success:
                product = self.ds.get_by_id('products', product_id, account_id)
                return True, None, product
            else:
                return False, "Product not found", None
                
        except Exception as e:
            logger.error(f"Error updating product: {e}")
            return False, f"Failed to update product: {str(e)}", None
    
    def delete_product(self, product_id: int, account_id: str) -> Tuple[bool, Optional[str]]:
        """Delete product"""
        try:
            success = self.ds.delete('products', product_id, account_id)
            if success:
                return True, None
            else:
                return False, "Product not found"
                
        except Exception as e:
            logger.error(f"Error deleting product: {e}")
            return False, f"Failed to delete product: {str(e)}"
    
    def get_products(self, account_id: str, category: Optional[str] = None) -> List[Dict]:
        """Get all products"""
        products = self.ds.get_all('products', account_id)
        
        if category:
            products = [p for p in products if p.get('category') == category]
        
        return products
    
    def adjust_stock(
        self,
        product_id: int,
        account_id: str,
        quantity: float,
        notes: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """Adjust product stock"""
        try:
            success = self.stock.adjust_stock(
                product_id, quantity, account_id, 
                'adjustment', notes, user_id
            )
            
            if success:
                return True, None
            else:
                return False, "Failed to adjust stock"
                
        except Exception as e:
            logger.error(f"Error adjusting stock: {e}")
            return False, f"Failed to adjust stock: {str(e)}"
    
    # ============================================================
    # USER MANAGEMENT
    # ============================================================
    
    def create_user(
        self,
        account_id: str,
        email: str,
        password: str,
        name: str,
        role: str = 'cashier',
        pin: Optional[str] = None,
        created_by: Optional[int] = None,
        business_type: Optional[str] = None,
        business_role: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """Create new user (cashier/admin)"""
        try:
            # Check if email already exists
            existing = self.ds.get_user_by_email(email)
            if existing:
                return False, "Email already exists", None
            
            # Hash password
            import bcrypt
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            user_data = {
                'account_id': account_id,
                'email': email,
                'password_hash': password_hash,
                'name': name,
                'role': role,
                'pin': pin,
                'cashier_pin': pin,
                'is_active': True,
                'is_locked': False,
                'screen_locked': False,
                'created_at': datetime.now().isoformat(),
                'created_by': created_by,
                'hourly_rate': 0.0,
                'business_type': business_type,
                'business_role': business_role
            }
            
            user = self.ds.create('users', user_data)
            
            # Remove password_hash from response
            user_response = {k: v for k, v in user.items() if k != 'password_hash'}
            
            return True, None, user_response
            
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return False, f"Failed to create user: {str(e)}", None
    
    def update_user(
        self,
        user_id: int,
        account_id: str,
        updates: Dict
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """Update user"""
        try:
            success = self.ds.update('users', user_id, updates, account_id)
            
            if success:
                user = self.ds.get_by_id('users', user_id, account_id)
                user_response = {k: v for k, v in user.items() if k != 'password_hash'}
                return True, None, user_response
            else:
                return False, "User not found", None
                
        except Exception as e:
            logger.error(f"Error updating user: {e}")
            return False, f"Failed to update user: {str(e)}", None
    
    def delete_user(self, user_id: int, account_id: str) -> Tuple[bool, Optional[str]]:
        """Delete user"""
        try:
            success = self.ds.delete('users', user_id, account_id)
            if success:
                return True, None
            else:
                return False, "User not found"
                
        except Exception as e:
            logger.error(f"Error deleting user: {e}")
            return False, f"Failed to delete user: {str(e)}"
    
    def get_users(self, account_id: str) -> List[Dict]:
        """Get all users for account"""
        users = self.ds.get_all('users', account_id)
        
        # Remove password hashes
        return [{k: v for k, v in u.items() if k != 'password_hash'} for u in users]
    
    def get_time_entries(
        self,
        account_id: str,
        user_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict]:
        """Get time tracking entries"""
        entries = self.ds.get_all('time_entries', account_id)
        
        if user_id:
            entries = [e for e in entries if e.get('user_id') == user_id]
        
        if start_date:
            entries = [e for e in entries if e.get('date', '') >= start_date]
        
        if end_date:
            entries = [e for e in entries if e.get('date', '') <= end_date]
        
        return entries
    
    # ============================================================
    # VENDORS
    # ============================================================
    
    def create_vendor(
        self,
        account_id: str,
        name: str,
        product_or_service: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        country: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """Create vendor"""
        try:
            vendor_data = {
                'account_id': account_id,
                'name': name,
                'product_or_service': product_or_service,
                'email': email,
                'phone': phone,
                'address': address,
                'city': city,
                'country': country,
                'created_at': datetime.now().isoformat()
            }
            
            vendor = self.ds.create('vendors', vendor_data)
            return True, None, vendor
            
        except Exception as e:
            logger.error(f"Error creating vendor: {e}")
            return False, f"Failed to create vendor: {str(e)}", None
    
    def update_vendor(
        self,
        vendor_id: int,
        account_id: str,
        updates: Dict
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """Update vendor"""
        try:
            success = self.ds.update('vendors', vendor_id, updates, account_id)
            
            if success:
                vendor = self.ds.get_by_id('vendors', vendor_id, account_id)
                return True, None, vendor
            else:
                return False, "Vendor not found", None
                
        except Exception as e:
            logger.error(f"Error updating vendor: {e}")
            return False, f"Failed to update vendor: {str(e)}", None
    
    def delete_vendor(self, vendor_id: int, account_id: str) -> Tuple[bool, Optional[str]]:
        """Delete vendor"""
        try:
            success = self.ds.delete('vendors', vendor_id, account_id)
            if success:
                return True, None
            else:
                return False, "Vendor not found"
                
        except Exception as e:
            logger.error(f"Error deleting vendor: {e}")
            return False, f"Failed to delete vendor: {str(e)}"
    
    def get_vendors(self, account_id: str) -> List[Dict]:
        """Get all vendors"""
        return self.ds.get_all('vendors', account_id)
    
    # ============================================================
    # REMINDERS
    # ============================================================
    
    def create_reminder(
        self,
        account_id: str,
        title: str,
        message: str,
        created_by: int
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """Create reminder"""
        try:
            reminder_data = {
                'account_id': account_id,
                'title': title,
                'message': message,
                'created_by': created_by,
                'created_at': datetime.now().isoformat(),
                'seen_by': []
            }
            
            reminder = self.ds.create('reminders', reminder_data)
            return True, None, reminder
            
        except Exception as e:
            logger.error(f"Error creating reminder: {e}")
            return False, f"Failed to create reminder: {str(e)}", None
    
    def mark_reminder_seen(
        self,
        reminder_id: int,
        account_id: str,
        user_id: int
    ) -> Tuple[bool, Optional[str]]:
        """Mark reminder as seen by user"""
        try:
            reminder = self.ds.get_by_id('reminders', reminder_id, account_id)
            if not reminder:
                return False, "Reminder not found"
            
            seen_by = reminder.get('seen_by', [])
            if user_id not in seen_by:
                seen_by.append(user_id)
                self.ds.update('reminders', reminder_id, {'seen_by': seen_by}, account_id)
            
            return True, None
            
        except Exception as e:
            logger.error(f"Error marking reminder seen: {e}")
            return False, f"Failed to mark reminder: {str(e)}"
    
    def get_unseen_reminders(self, account_id: str, user_id: int) -> List[Dict]:
        """Get reminders not yet seen by user"""
        reminders = self.ds.get_all('reminders', account_id)
        return [r for r in reminders if user_id not in r.get('seen_by', [])]
    
    def get_reminders(self, account_id: str) -> List[Dict]:
        """Get all reminders"""
        return self.ds.get_all('reminders', account_id)
    
    def delete_reminder(self, reminder_id: int, account_id: str) -> Tuple[bool, Optional[str]]:
        """Delete reminder"""
        try:
            success = self.ds.delete('reminders', reminder_id, account_id)
            if success:
                return True, None
            else:
                return False, "Reminder not found"
                
        except Exception as e:
            logger.error(f"Error deleting reminder: {e}")
            return False, f"Failed to delete reminder: {str(e)}"
    
    # ============================================================
    # CREDIT REQUESTS
    # ============================================================
    
    def get_credit_requests(
        self,
        account_id: str,
        status: Optional[str] = None
    ) -> List[Dict]:
        """Get credit requests"""
        requests = self.ds.get_all('credit_requests', account_id)
        
        if status:
            requests = [r for r in requests if r.get('status') == status]
        
        return sorted(requests, key=lambda x: x.get('created_at', ''), reverse=True)
    
    def approve_credit_request(
        self,
        request_id: int,
        account_id: str,
        admin_id: int,
        notes: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """Approve credit request"""
        try:
            updates = {
                'status': 'approved',
                'reviewed_by': admin_id,
                'reviewed_at': datetime.now().isoformat(),
                'admin_notes': notes
            }
            
            success = self.ds.update('credit_requests', request_id, updates, account_id)
            if success:
                return True, None
            else:
                return False, "Credit request not found"
                
        except Exception as e:
            logger.error(f"Error approving credit request: {e}")
            return False, f"Failed to approve: {str(e)}"
    
    def reject_credit_request(
        self,
        request_id: int,
        account_id: str,
        admin_id: int,
        notes: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """Reject credit request"""
        try:
            updates = {
                'status': 'rejected',
                'reviewed_by': admin_id,
                'reviewed_at': datetime.now().isoformat(),
                'admin_notes': notes
            }
            
            success = self.ds.update('credit_requests', request_id, updates, account_id)
            if success:
                return True, None
            else:
                return False, "Credit request not found"
                
        except Exception as e:
            logger.error(f"Error rejecting credit request: {e}")
            return False, f"Failed to reject: {str(e)}"
    
    # ============================================================
    # EXPENSES
    # ============================================================
    
    def get_expenses(
        self,
        account_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict]:
        """Get expenses"""
        expenses = self.ds.get_all('expenses', account_id)
        
        if start_date:
            expenses = [e for e in expenses if e.get('created_at', '') >= start_date]
        
        if end_date:
            expenses = [e for e in expenses if e.get('created_at', '') <= end_date]
        
        return sorted(expenses, key=lambda x: x.get('created_at', ''), reverse=True)
    
    def create_expense(
        self,
        account_id: str,
        name: str,
        amount: float,
        quantity: float = 1.0,
        unit: str = 'unit',
        category: str = 'general',
        description: Optional[str] = None,
        created_by: Optional[int] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """Create expense"""
        try:
            expense_data = {
                'account_id': account_id,
                'name': name,
                'amount': amount,
                'quantity': quantity,
                'unit': unit,
                'category': category,
                'description': description,
                'source': 'manual',
                'created_at': datetime.now().isoformat(),
                'created_by': created_by
            }
            
            expense = self.ds.create('expenses', expense_data)
            return True, None, expense
            
        except Exception as e:
            logger.error(f"Error creating expense: {e}")
            return False, f"Failed to create expense: {str(e)}", None
