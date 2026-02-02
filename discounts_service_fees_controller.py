"""
DISCOUNTS AND SERVICE FEES CONTROLLER
=====================================
Handles discount management with product-specific rules, date ranges,
and service fee management for deliveries and extra charges.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class DiscountsController:
    """
    Discounts management controller
    """
    
    def __init__(self, datastore):
        """
        Initialize discounts controller
        
        Args:
            datastore: DataStore instance
        """
        self.ds = datastore
    
    def create_discount(
        self, 
        account_id: str, 
        name: str,
        discount_type: str,  # 'percentage' or 'fixed'
        value: float,
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
        product_ids: Optional[List[int]] = None,
        min_purchase_amount: Optional[float] = None,
        max_discount_amount: Optional[float] = None,
        usage_limit: Optional[int] = None,
        created_by: Optional[int] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Create a new discount
        
        Args:
            account_id: Account ID
            name: Discount name
            discount_type: 'percentage' or 'fixed'
            value: Discount value (percentage or fixed amount)
            valid_from: Start date (ISO format)
            valid_to: End date (ISO format)
            product_ids: List of specific product IDs (None = all products)
            min_purchase_amount: Minimum purchase amount to qualify
            max_discount_amount: Maximum discount amount (for percentage discounts)
            usage_limit: Maximum number of uses (None = unlimited)
            created_by: User ID who created the discount
        
        Returns:
            (success, error_message, discount)
        """
        try:
            if not name or not discount_type or value <= 0:
                return False, "Name, type, and positive value are required", None
            
            if discount_type not in ['percentage', 'fixed']:
                return False, "Discount type must be 'percentage' or 'fixed'", None
            
            if discount_type == 'percentage' and value > 100:
                return False, "Percentage discount cannot exceed 100%", None
            
            # Default validity period (30 days if not specified)
            if not valid_from:
                valid_from = datetime.now().isoformat()
            if not valid_to:
                valid_to = (datetime.now() + timedelta(days=30)).isoformat()
            
            discount = {
                'account_id': account_id,
                'name': name.strip(),
                'discount_type': discount_type,
                'value': float(value),
                'valid_from': valid_from,
                'valid_to': valid_to,
                'product_ids': product_ids or [],  # Empty list = all products
                'min_purchase_amount': float(min_purchase_amount) if min_purchase_amount else None,
                'max_discount_amount': float(max_discount_amount) if max_discount_amount else None,
                'usage_limit': int(usage_limit) if usage_limit else None,
                'usage_count': 0,
                'is_active': True,
                'created_by': created_by,
                'created_at': datetime.now().isoformat()
            }
            
            created_discount = self.ds.create('discounts', discount)
            
            logger.info(f"✅ Discount created: '{name}' - {value}{'%' if discount_type == 'percentage' else ' KSH'}")
            
            return True, None, created_discount
            
        except Exception as e:
            logger.error(f"❌ Failed to create discount: {e}")
            return False, f"Failed to create discount: {str(e)}", None
    
    def get_active_discounts(self, account_id: str, product_ids: Optional[List[int]] = None) -> List[Dict]:
        """
        Get active discounts, optionally filtered by products
        
        Args:
            account_id: Account ID
            product_ids: Optional list of product IDs to filter by
        
        Returns:
            List of active discounts
        """
        try:
            all_discounts = self.ds.get_all('discounts', account_id)
            now = datetime.now()
            
            active_discounts = []
            
            for discount in all_discounts:
                # Skip inactive discounts
                if not discount.get('is_active', True):
                    continue
                
                # Check date validity
                valid_from = discount.get('valid_from')
                valid_to = discount.get('valid_to')
                
                if valid_from:
                    try:
                        from_date = datetime.fromisoformat(valid_from)
                        if now < from_date:
                            continue
                    except ValueError:
                        continue
                
                if valid_to:
                    try:
                        to_date = datetime.fromisoformat(valid_to)
                        if now > to_date:
                            continue
                    except ValueError:
                        continue
                
                # Check usage limit
                usage_limit = discount.get('usage_limit')
                usage_count = discount.get('usage_count', 0)
                if usage_limit and usage_count >= usage_limit:
                    continue
                
                # Check product filter
                discount_product_ids = discount.get('product_ids', [])
                if product_ids and discount_product_ids:
                    # Discount applies to specific products, check if any match
                    if not any(pid in discount_product_ids for pid in product_ids):
                        continue
                
                active_discounts.append(discount)
            
            # Sort by value (highest first)
            active_discounts.sort(key=lambda d: d.get('value', 0), reverse=True)
            
            return active_discounts
            
        except Exception as e:
            logger.error(f"❌ Failed to get active discounts: {e}")
            return []
    
    def calculate_discount(self, discount: Dict, subtotal: float, product_ids: List[int]) -> float:
        """
        Calculate discount amount for a given subtotal and products
        
        Args:
            discount: Discount record
            subtotal: Subtotal amount
            product_ids: List of product IDs in the sale
        
        Returns:
            Discount amount
        """
        try:
            # Check minimum purchase amount
            min_amount = discount.get('min_purchase_amount')
            if min_amount and subtotal < min_amount:
                return 0.0
            
            # Check product eligibility
            discount_product_ids = discount.get('product_ids', [])
            if discount_product_ids and not any(pid in discount_product_ids for pid in product_ids):
                return 0.0
            
            # Calculate discount
            discount_type = discount.get('discount_type', 'percentage')
            value = discount.get('value', 0)
            
            if discount_type == 'percentage':
                discount_amount = subtotal * (value / 100)
            else:  # fixed
                discount_amount = value
            
            # Apply maximum discount limit
            max_amount = discount.get('max_discount_amount')
            if max_amount and discount_amount > max_amount:
                discount_amount = max_amount
            
            # Don't exceed subtotal
            if discount_amount > subtotal:
                discount_amount = subtotal
            
            return round(discount_amount, 2)
            
        except Exception as e:
            logger.error(f"❌ Failed to calculate discount: {e}")
            return 0.0
    
    def apply_discount(self, discount_id: int, account_id: str) -> bool:
        """
        Increment usage count when discount is applied
        
        Args:
            discount_id: Discount ID
            account_id: Account ID
        
        Returns:
            Success status
        """
        try:
            discount = self.ds.get_by_id('discounts', discount_id, account_id)
            if not discount:
                return False
            
            usage_count = discount.get('usage_count', 0) + 1
            
            success = self.ds.update('discounts', discount_id, {
                'usage_count': usage_count,
                'last_used_at': datetime.now().isoformat()
            }, account_id)
            
            if success:
                logger.info(f"✅ Discount {discount_id} applied - usage count: {usage_count}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Failed to apply discount {discount_id}: {e}")
            return False


class ServiceFeesController:
    """
    Service fees management controller
    """
    
    def __init__(self, datastore):
        """
        Initialize service fees controller
        
        Args:
            datastore: DataStore instance
        """
        self.ds = datastore
    
    def create_service_fee(
        self, 
        account_id: str, 
        name: str,
        amount: float,
        fee_type: str = 'fixed',  # 'fixed' or 'percentage'
        description: Optional[str] = None,
        is_active: bool = True,
        created_by: Optional[int] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Create a new service fee
        
        Args:
            account_id: Account ID
            name: Service fee name (e.g., "Delivery", "Packaging")
            amount: Fee amount or percentage
            fee_type: 'fixed' or 'percentage'
            description: Optional description
            is_active: Whether the fee is active
            created_by: User ID who created the fee
        
        Returns:
            (success, error_message, service_fee)
        """
        try:
            if not name or amount < 0:
                return False, "Name is required and amount must be non-negative", None
            
            if fee_type not in ['fixed', 'percentage']:
                return False, "Fee type must be 'fixed' or 'percentage'", None
            
            service_fee = {
                'account_id': account_id,
                'name': name.strip(),
                'amount': float(amount),
                'fee_type': fee_type,
                'description': description.strip() if description else None,
                'is_active': is_active,
                'created_by': created_by,
                'created_at': datetime.now().isoformat()
            }
            
            created_fee = self.ds.create('service_fees', service_fee)
            
            logger.info(f"✅ Service fee created: '{name}' - {amount}{'%' if fee_type == 'percentage' else ' KSH'}")
            
            return True, None, created_fee
            
        except Exception as e:
            logger.error(f"❌ Failed to create service fee: {e}")
            return False, f"Failed to create service fee: {str(e)}", None
    
    def get_active_service_fees(self, account_id: str) -> List[Dict]:
        """
        Get all active service fees
        
        Args:
            account_id: Account ID
        
        Returns:
            List of active service fees
        """
        try:
            all_fees = self.ds.get_all('service_fees', account_id)
            
            active_fees = [
                fee for fee in all_fees 
                if fee.get('is_active', True)
            ]
            
            # Sort by name
            active_fees.sort(key=lambda f: f.get('name', ''))
            
            return active_fees
            
        except Exception as e:
            logger.error(f"❌ Failed to get active service fees: {e}")
            return []
    
    def calculate_service_fee(self, service_fee: Dict, subtotal: float) -> float:
        """
        Calculate service fee amount
        
        Args:
            service_fee: Service fee record
            subtotal: Subtotal amount
        
        Returns:
            Service fee amount
        """
        try:
            fee_type = service_fee.get('fee_type', 'fixed')
            amount = service_fee.get('amount', 0)
            
            if fee_type == 'percentage':
                return round(subtotal * (amount / 100), 2)
            else:  # fixed
                return round(amount, 2)
                
        except Exception as e:
            logger.error(f"❌ Failed to calculate service fee: {e}")
            return 0.0
    
    def get_all_service_fees(self, account_id: str) -> List[Dict]:
        """
        Get all service fees for admin management
        
        Args:
            account_id: Account ID
        
        Returns:
            List of all service fees
        """
        try:
            fees = self.ds.get_all('service_fees', account_id)
            
            # Sort by creation date (newest first)
            fees.sort(key=lambda f: f.get('created_at', ''), reverse=True)
            
            return fees
            
        except Exception as e:
            logger.error(f"❌ Failed to get all service fees: {e}")
            return []
    
    def update_service_fee(self, fee_id: int, account_id: str, updates: Dict) -> bool:
        """
        Update a service fee
        
        Args:
            fee_id: Service fee ID
            account_id: Account ID
            updates: Fields to update
        
        Returns:
            Success status
        """
        try:
            updates['updated_at'] = datetime.now().isoformat()
            
            success = self.ds.update('service_fees', fee_id, updates, account_id)
            
            if success:
                logger.info(f"✅ Service fee {fee_id} updated")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Failed to update service fee {fee_id}: {e}")
            return False
    
    def delete_service_fee(self, fee_id: int, account_id: str) -> bool:
        """
        Delete a service fee
        
        Args:
            fee_id: Service fee ID
            account_id: Account ID
        
        Returns:
            Success status
        """
        try:
            success = self.ds.delete('service_fees', fee_id, account_id)
            
            if success:
                logger.info(f"🗑️ Service fee {fee_id} deleted")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Failed to delete service fee {fee_id}: {e}")
            return False