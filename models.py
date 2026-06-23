"""
REWRITTEN POS SYSTEM MODELS
============================
Comprehensive database models for multi-tenant POS system with:
- Account/Business isolation
- User management with roles (owner, admin, cashier)
- Product management (raw, composite, expense items)
- Sales tracking with detailed analytics
- Inventory management with real-time stock tracking
- Time tracking (clock in/out)
- Reminders, vendors, credit requests
- Subscription management
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from enum import Enum
import json


class UserRole(Enum):
    """User role types"""
    OWNER = "owner"
    ADMIN = "admin"
    CASHIER = "cashier"


class ProductType(Enum):
    """Product types"""
    RAW = "raw"  # Raw materials/ingredients
    COMPOSITE = "composite"  # Built from recipe (BOM)
    EXPENSE = "expense"  # Expense-only items
    REGULAR = "regular"  # Regular sellable products


class PaymentMethod(Enum):
    """Payment methods"""
    CASH = "cash"
    MPESA = "mpesa"
    CARD = "card"
    CREDIT = "credit"


class SubscriptionPlan(Enum):
    """Subscription plans"""
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ULTRA = "ultra"


# ============================================================
# ACCOUNT/BUSINESS MODEL
# ============================================================

@dataclass
class Account:
    """
    Business Account - Multi-tenant isolation
    Each business has separate data, users, products, sales
    """
    id: str
    owner_email: str
    business_name: str
    plan: str = SubscriptionPlan.FREE.value
    is_active: bool = True
    is_locked: bool = False
    trial_ends_at: Optional[str] = None
    subscription_ends_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Business settings
    business_logo: Optional[str] = None
    currency: str = "KES"
    tax_rate: float = 0.0
    screen_lock_password: str = "2005"
    
    # Subscription tracking
    days_used: int = 0
    last_activity_date: Optional[str] = None
    requested_trial: bool = False
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def is_subscription_active(self) -> bool:
        """Check if subscription is active"""
        if not self.is_active or self.is_locked:
            return False
        
        if self.plan == SubscriptionPlan.FREE.value:
            return True
        
        if self.plan == "trial":
            if self.trial_ends_at:
                ends_at = datetime.fromisoformat(self.trial_ends_at)
                return datetime.now() < ends_at
            return True
        
        if self.subscription_ends_at:
            ends_at = datetime.fromisoformat(self.subscription_ends_at)
            return datetime.now() < ends_at
        
        return False


# ============================================================
# USER MODEL
# ============================================================

@dataclass
class User:
    """
    User model - supports owner, admin, cashier roles
    """
    id: int
    account_id: str
    email: str
    password_hash: str
    name: str
    role: str = UserRole.CASHIER.value
    
    # Authentication
    pin: Optional[str] = None
    cashier_pin: Optional[str] = None
    
    # Status
    is_active: bool = True
    is_locked: bool = False
    screen_locked: bool = False
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    created_by: Optional[int] = None
    last_login: Optional[str] = None
    
    # Cashier-specific
    hourly_rate: float = 0.0
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        # Don't expose password hash
        data.pop('password_hash', None)
        return data
    
    def is_owner(self) -> bool:
        return self.role == UserRole.OWNER.value
    
    def is_admin(self) -> bool:
        return self.role in [UserRole.OWNER.value, UserRole.ADMIN.value]
    
    def is_cashier(self) -> bool:
        return self.role == UserRole.CASHIER.value


# ============================================================
# PRODUCT MODELS
# ============================================================

@dataclass
class Recipe:
    """Recipe ingredient for composite products"""
    product_id: int
    quantity: float
    unit: str
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Product:
    """
    Product model - supports raw, composite, and expense items
    """
    id: int
    account_id: str
    name: str
    price: float
    cost: float = 0.0
    quantity: float = 0.0
    
    # Product type and classification
    product_type: str = ProductType.REGULAR.value
    category: str = "general"
    unit: str = "pcs"
    
    # Images and display
    image: Optional[str] = None
    barcode: Optional[str] = None
    sku: Optional[str] = None
    
    # Composite product recipe (BOM)
    is_composite: bool = False
    recipe: List[Dict] = field(default_factory=list)  # List of Recipe dicts
    
    # Inventory tracking
    reorder_level: float = 0.0
    max_stock_level: float = 0.0
    
    # Pricing
    cost_per_unit: float = 0.0  # For expense items
    enable_weight_pricing: bool = False
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    created_by: Optional[int] = None
    updated_at: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def is_low_stock(self) -> bool:
        """Check if product is low on stock"""
        return self.reorder_level > 0 and self.quantity <= self.reorder_level
    
    def is_out_of_stock(self) -> bool:
        """Check if product is out of stock"""
        return self.quantity <= 0
    
    def has_sufficient_stock(self, required_qty: float) -> bool:
        """Check if product has sufficient stock for sale"""
        return self.quantity >= required_qty


# ============================================================
# SALE MODELS
# ============================================================

@dataclass
class SaleItem:
    """Individual item in a sale"""
    product_id: int
    product_name: str
    quantity: float
    unit_price: float
    subtotal: float
    cost: float = 0.0
    unit: str = "pcs"
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Sale:
    """
    Sale transaction record
    """
    id: int
    account_id: str
    
    # Sale details
    items: List[Dict]  # List of SaleItem dicts
    total: float
    
    # Costs and profit
    total_cost: float = 0.0
    gross_profit: float = 0.0
    
    # Payment
    payment_method: str = PaymentMethod.CASH.value
    amount_paid: float = 0.0
    change: float = 0.0
    
    # Tax and discounts
    tax_amount: float = 0.0
    discount_amount: float = 0.0
    service_fee: float = 0.0
    
    # Cashier info
    cashier_id: Optional[int] = None
    cashier_name: Optional[str] = None
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    receipt_number: Optional[str] = None
    notes: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def calculate_totals(self):
        """Calculate total cost and profit"""
        self.total_cost = sum(item.get('cost', 0) * item.get('quantity', 0) for item in self.items)
        self.gross_profit = self.total - self.total_cost


# ============================================================
# INVENTORY TRACKING
# ============================================================

@dataclass
class StockMovement:
    """Track stock movements (in/out) for audit trail"""
    id: int
    account_id: str
    product_id: int
    quantity: float
    movement_type: str  # 'in', 'out', 'adjustment', 'sale', 'production'
    reference_id: Optional[int] = None  # Sale ID, production ID, etc.
    notes: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    created_by: Optional[int] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


# ============================================================
# TIME TRACKING
# ============================================================

@dataclass
class TimeEntry:
    """
    Clock in/out time tracking for cashiers
    """
    id: int
    account_id: str
    user_id: int
    user_name: str
    
    # Time tracking
    clock_in_time: str
    clock_out_time: Optional[str] = None
    duration_minutes: int = 0
    
    # Metadata
    date: str = field(default_factory=lambda: datetime.now().date().isoformat())
    notes: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def calculate_duration(self):
        """Calculate duration if clocked out"""
        if self.clock_out_time:
            clock_in = datetime.fromisoformat(self.clock_in_time)
            clock_out = datetime.fromisoformat(self.clock_out_time)
            delta = clock_out - clock_in
            self.duration_minutes = int(delta.total_seconds() / 60)


# ============================================================
# REMINDERS
# ============================================================

@dataclass
class Reminder:
    """
    User reminders - show once per account on login
    """
    id: int
    account_id: str
    title: str
    message: str
    created_by: int
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Tracking who has seen the reminder
    seen_by: List[int] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def mark_seen_by(self, user_id: int):
        """Mark reminder as seen by user"""
        if user_id not in self.seen_by:
            self.seen_by.append(user_id)


# ============================================================
# VENDORS
# ============================================================

@dataclass
class Vendor:
    """
    Vendor/Supplier management
    """
    id: int
    account_id: str
    name: str
    product_or_service: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return asdict(self)


# ============================================================
# CREDIT REQUESTS
# ============================================================

@dataclass
class CreditRequest:
    """
    Credit requests from cashier to admin
    """
    id: int
    account_id: str
    cashier_id: int
    cashier_name: str
    amount: float
    reason: str
    status: str = "pending"  # pending, approved, rejected
    
    # Response
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[str] = None
    admin_notes: Optional[str] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def approve(self, admin_id: int, notes: Optional[str] = None):
        """Approve credit request"""
        self.status = "approved"
        self.reviewed_by = admin_id
        self.reviewed_at = datetime.now().isoformat()
        self.admin_notes = notes
    
    def reject(self, admin_id: int, notes: Optional[str] = None):
        """Reject credit request"""
        self.status = "rejected"
        self.reviewed_by = admin_id
        self.reviewed_at = datetime.now().isoformat()
        self.admin_notes = notes


# ============================================================
# EXPENSES
# ============================================================

@dataclass
class Expense:
    """
    Expense tracking
    """
    id: int
    account_id: str
    name: str
    amount: float
    quantity: float = 1.0
    unit: str = "unit"
    category: str = "general"
    description: Optional[str] = None
    
    # Expense source
    source: str = "manual"  # manual, auto-deduction
    linked_product_id: Optional[int] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    created_by: Optional[int] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


# ============================================================
# DISCOUNTS
# ============================================================

@dataclass
class Discount:
    """
    Product-specific discounts
    """
    id: int
    account_id: str
    product_id: int
    discount_type: str = "percentage"  # percentage, fixed
    discount_value: float = 0.0
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def calculate_discounted_price(self, original_price: float) -> float:
        """Calculate discounted price"""
        if not self.is_active:
            return original_price
        
        if self.discount_type == "percentage":
            return original_price * (1 - self.discount_value / 100)
        else:  # fixed
            return max(0, original_price - self.discount_value)


# ============================================================
# SERVICE FEES
# ============================================================

@dataclass
class ServiceFee:
    """
    Service fees (delivery, packaging, etc.)
    """
    id: int
    account_id: str
    name: str
    amount: float
    fee_type: str = "fixed"  # fixed, percentage
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return asdict(self)
