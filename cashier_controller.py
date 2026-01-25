"""
CASHIER CONTROLLER
==================
Cashier dashboard features:
- POS sales (Complete Sell)
- Clock in/out time tracking
- Credit requests
- Product viewing
- Sales monitoring
"""

from flask import jsonify, request
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class CashierController:
    """Cashier POS controller"""
    
    def __init__(self, datastore, stock_engine):
        """
        Initialize cashier controller
        
        Args:
            datastore: DataStore instance
            stock_engine: StockEngine instance
        """
        self.ds = datastore
        self.stock = stock_engine
    
    # ============================================================
    # POS SALES
    # ============================================================
    
    def complete_sale(
        self,
        account_id: str,
        cashier_id: int,
        cashier_name: str,
        items: List[Dict],
        payment_method: str = 'cash',
        amount_paid: float = 0.0,
        tax_rate: float = 0.0,
        discount_amount: float = 0.0,
        service_fee: float = 0.0
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Complete sale transaction (OPTIMIZED)
        
        This is the critical Complete Sell button operation
        Target: <50ms execution time
        
        Args:
            account_id: Account ID
            cashier_id: Cashier user ID
            cashier_name: Cashier name
            items: List of sale items
            payment_method: Payment method
            amount_paid: Amount paid by customer
            tax_rate: Tax rate
            discount_amount: Discount applied
            service_fee: Service fee
        
        Returns:
            (success, error_message, sale_record)
        """
        try:
            # Execute sale with stock deduction
            success, error, sale = self.stock.execute_sale(
                items=items,
                account_id=account_id,
                cashier_id=cashier_id,
                cashier_name=cashier_name,
                payment_method=payment_method,
                amount_paid=amount_paid,
                tax_rate=tax_rate,
                discount_amount=discount_amount,
                service_fee=service_fee
            )
            
            if success:
                return True, None, sale
            else:
                return False, error, None
                
        except Exception as e:
            logger.error(f"Error completing sale: {e}")
            return False, f"Sale failed: {str(e)}", None
    
    def get_sales(
        self,
        account_id: str,
        cashier_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict]:
        """Get sales records"""
        if start_date and end_date:
            sales = self.ds.get_sales_by_date_range(account_id, start_date, end_date)
        else:
            sales = self.ds.get_all('sales', account_id)
        
        if cashier_id:
            sales = [s for s in sales if s.get('cashier_id') == cashier_id]
        
        return sorted(sales, key=lambda x: x.get('created_at', ''), reverse=True)
    
    def get_cashier_stats(self, account_id: str, cashier_id: int) -> Dict:
        """Get statistics for specific cashier"""
        try:
            # Get cashier's sales
            sales = [s for s in self.ds.get_all('sales', account_id) if s.get('cashier_id') == cashier_id]
            
            # Today's sales
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0).isoformat()
            today_sales = [s for s in sales if s.get('created_at', '') >= today_start]
            
            # Calculate totals
            total_sales = sum(s.get('total', 0) for s in today_sales)
            total_profit = sum(s.get('gross_profit', 0) for s in today_sales)
            
            return {
                'digital_sales': round(total_sales, 2),
                'digital_profit': round(total_profit, 2),
                'sales_count': len(today_sales),
                'all_time_sales': len(sales),
                'all_time_total': round(sum(s.get('total', 0) for s in sales), 2)
            }
            
        except Exception as e:
            logger.error(f"Error getting cashier stats: {e}")
            return {}
    
    # ============================================================
    # PRODUCT VIEWING
    # ============================================================
    
    def get_products(self, account_id: str, category: Optional[str] = None) -> List[Dict]:
        """Get products for POS"""
        products = self.ds.get_all('products', account_id)
        
        # Filter out products with zero or negative stock
        products = [p for p in products if p.get('quantity', 0) > 0]
        
        if category:
            products = [p for p in products if p.get('category') == category]
        
        return products
    
    def get_product(self, product_id: int, account_id: str) -> Optional[Dict]:
        """Get single product"""
        return self.ds.get_by_id('products', product_id, account_id)
    
    # ============================================================
    # TIME TRACKING (Clock In/Out)
    # ============================================================
    
    def clock_in(
        self,
        account_id: str,
        user_id: int,
        user_name: str
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Clock in - start time tracking
        
        Args:
            account_id: Account ID
            user_id: User ID
            user_name: User name
        
        Returns:
            (success, error_message, time_entry)
        """
        try:
            # Check if already clocked in
            active_entry = self.ds.get_active_time_entry(user_id, account_id)
            if active_entry:
                return False, "Already clocked in", None
            
            # Create time entry
            entry_data = {
                'account_id': account_id,
                'user_id': user_id,
                'user_name': user_name,
                'clock_in_time': datetime.now().isoformat(),
                'clock_out_time': None,
                'duration_minutes': 0,
                'date': datetime.now().date().isoformat(),
                'notes': None
            }
            
            entry = self.ds.create('time_entries', entry_data)
            return True, None, entry
            
        except Exception as e:
            logger.error(f"Error clocking in: {e}")
            return False, f"Clock in failed: {str(e)}", None
    
    def clock_out(
        self,
        account_id: str,
        user_id: int
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Clock out - end time tracking
        
        Args:
            account_id: Account ID
            user_id: User ID
        
        Returns:
            (success, error_message, time_entry)
        """
        try:
            # Get active entry
            active_entry = self.ds.get_active_time_entry(user_id, account_id)
            if not active_entry:
                return False, "Not clocked in", None
            
            # Calculate duration
            clock_in = datetime.fromisoformat(active_entry['clock_in_time'])
            clock_out = datetime.now()
            duration_minutes = int((clock_out - clock_in).total_seconds() / 60)
            
            # Update entry
            updates = {
                'clock_out_time': clock_out.isoformat(),
                'duration_minutes': duration_minutes
            }
            
            self.ds.update('time_entries', active_entry['id'], updates, account_id)
            
            # Get updated entry
            entry = self.ds.get_by_id('time_entries', active_entry['id'], account_id)
            return True, None, entry
            
        except Exception as e:
            logger.error(f"Error clocking out: {e}")
            return False, f"Clock out failed: {str(e)}", None
    
    def get_clock_status(
        self,
        account_id: str,
        user_id: int
    ) -> Dict:
        """Get current clock in/out status"""
        try:
            active_entry = self.ds.get_active_time_entry(user_id, account_id)
            
            if active_entry:
                # Calculate current duration
                clock_in = datetime.fromisoformat(active_entry['clock_in_time'])
                duration_minutes = int((datetime.now() - clock_in).total_seconds() / 60)
                
                return {
                    'clocked_in': True,
                    'clock_in_time': active_entry['clock_in_time'],
                    'duration_minutes': duration_minutes,
                    'entry_id': active_entry['id']
                }
            else:
                return {
                    'clocked_in': False
                }
                
        except Exception as e:
            logger.error(f"Error getting clock status: {e}")
            return {'clocked_in': False}
    
    def get_time_entries(
        self,
        account_id: str,
        user_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict]:
        """Get time tracking entries for user"""
        entries = self.ds.get_all('time_entries', account_id)
        entries = [e for e in entries if e.get('user_id') == user_id]
        
        if start_date:
            entries = [e for e in entries if e.get('date', '') >= start_date]
        
        if end_date:
            entries = [e for e in entries if e.get('date', '') <= end_date]
        
        return sorted(entries, key=lambda x: x.get('date', ''), reverse=True)
    
    # ============================================================
    # CREDIT REQUESTS
    # ============================================================
    
    def request_credit(
        self,
        account_id: str,
        cashier_id: int,
        cashier_name: str,
        amount: float,
        reason: str
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Submit credit request to admin
        
        Args:
            account_id: Account ID
            cashier_id: Cashier user ID
            cashier_name: Cashier name
            amount: Requested amount
            reason: Reason for request
        
        Returns:
            (success, error_message, credit_request)
        """
        try:
            request_data = {
                'account_id': account_id,
                'cashier_id': cashier_id,
                'cashier_name': cashier_name,
                'amount': amount,
                'reason': reason,
                'status': 'pending',
                'created_at': datetime.now().isoformat()
            }
            
            credit_request = self.ds.create('credit_requests', request_data)
            return True, None, credit_request
            
        except Exception as e:
            logger.error(f"Error requesting credit: {e}")
            return False, f"Credit request failed: {str(e)}", None
    
    def get_my_credit_requests(
        self,
        account_id: str,
        cashier_id: int
    ) -> List[Dict]:
        """Get credit requests for specific cashier"""
        requests = self.ds.get_all('credit_requests', account_id)
        return [r for r in requests if r.get('cashier_id') == cashier_id]
    
    # ============================================================
    # DISCOUNTS
    # ============================================================
    
    def get_product_discount(
        self,
        account_id: str,
        product_id: int
    ) -> Optional[Dict]:
        """Get active discount for product"""
        discounts = self.ds.get_all('discounts', account_id)
        for discount in discounts:
            if discount.get('product_id') == product_id and discount.get('is_active'):
                return discount
        return None
    
    def apply_discount(
        self,
        product_id: int,
        account_id: str,
        original_price: float
    ) -> Tuple[float, Optional[Dict]]:
        """
        Apply discount to product price
        
        Returns:
            (discounted_price, discount_info)
        """
        discount = self.get_product_discount(account_id, product_id)
        
        if not discount:
            return original_price, None
        
        discount_type = discount.get('discount_type', 'percentage')
        discount_value = discount.get('discount_value', 0)
        
        if discount_type == 'percentage':
            discounted_price = original_price * (1 - discount_value / 100)
        else:  # fixed
            discounted_price = max(0, original_price - discount_value)
        
        return discounted_price, discount
    
    # ============================================================
    # SERVICE FEES
    # ============================================================
    
    def get_service_fees(self, account_id: str) -> List[Dict]:
        """Get active service fees"""
        fees = self.ds.get_all('service_fees', account_id)
        return [f for f in fees if f.get('is_active')]
    
    def calculate_service_fee(
        self,
        account_id: str,
        subtotal: float,
        selected_services: Optional[List[int]] = None
    ) -> Tuple[float, List[Dict]]:
        """
        Calculate total service fee
        
        Args:
            account_id: Account ID
            subtotal: Sale subtotal
            selected_services: List of service fee IDs to apply
        
        Returns:
            (total_fee, applied_fees)
        """
        if not selected_services:
            return 0.0, []
        
        fees = self.ds.get_all('service_fees', account_id)
        applied_fees = []
        total_fee = 0.0
        
        for fee in fees:
            if fee.get('id') in selected_services and fee.get('is_active'):
                fee_type = fee.get('fee_type', 'fixed')
                fee_amount = fee.get('amount', 0)
                
                if fee_type == 'percentage':
                    calculated_fee = subtotal * (fee_amount / 100)
                else:  # fixed
                    calculated_fee = fee_amount
                
                total_fee += calculated_fee
                applied_fees.append({
                    'id': fee['id'],
                    'name': fee['name'],
                    'amount': calculated_fee
                })
        
        return total_fee, applied_fees
    
    # ============================================================
    # STOCK DEDUCTION LOG
    # ============================================================
    
    def get_stock_deduction_log(
        self,
        account_id: str,
        cashier_id: Optional[int] = None
    ) -> List[Dict]:
        """Get stock deduction audit log"""
        movements = self.stock.get_stock_deduction_log(account_id)
        
        # Filter by cashier if specified
        if cashier_id:
            # Get sales by cashier
            sales = [s for s in self.ds.get_all('sales', account_id) if s.get('cashier_id') == cashier_id]
            sale_ids = [s['id'] for s in sales]
            
            # Filter movements linked to those sales
            movements = [m for m in movements if m.get('reference_id') in sale_ids]
        
        return movements
