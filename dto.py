"""
Data Transfer Objects (DTOs)
=============================
Standardized data structures for API communication.
Provides validation, serialization, and type safety.
"""

from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ResponseStatus(Enum):
    """Standard response status codes"""
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ApiResponse:
    """
    Standardized API response format
    
    All API endpoints should return this format for consistency
    """
    status: str  # success | error | warning | info
    message: Optional[str] = None
    data: Optional[Any] = None
    errors: Optional[List[Dict[str, str]]] = None
    meta: Optional[Dict[str, Any]] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        result = {
            'status': self.status,
            'timestamp': self.timestamp
        }
        if self.message:
            result['message'] = self.message
        if self.data is not None:
            result['data'] = self.data
        if self.errors:
            result['errors'] = self.errors
        if self.meta:
            result['meta'] = self.meta
        return result
    
    @classmethod
    def success(cls, data: Any = None, message: str = None, meta: Dict = None):
        """Create success response"""
        return cls(
            status=ResponseStatus.SUCCESS.value,
            message=message,
            data=data,
            meta=meta
        )
    
    @classmethod
    def error(cls, message: str, errors: List[Dict] = None, data: Any = None):
        """Create error response"""
        return cls(
            status=ResponseStatus.ERROR.value,
            message=message,
            errors=errors,
            data=data
        )
    
    @classmethod
    def warning(cls, message: str, data: Any = None):
        """Create warning response"""
        return cls(
            status=ResponseStatus.WARNING.value,
            message=message,
            data=data
        )


@dataclass
class PaginationMeta:
    """Pagination metadata"""
    page: int
    per_page: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class UserDTO:
    """User data transfer object"""
    id: int
    email: str
    name: str
    role: str
    account_id: str
    is_active: bool = True
    business_type: Optional[str] = None
    business_role: Optional[str] = None
    pin: Optional[str] = None
    created_at: Optional[str] = None
    last_login: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary, excluding sensitive data"""
        data = asdict(self)
        # Never send password_hash in DTO
        data.pop('password_hash', None)
        return data
    
    @classmethod
    def from_db(cls, db_user: Dict):
        """Create DTO from database record"""
        return cls(
            id=db_user.get('id'),
            email=db_user.get('email'),
            name=db_user.get('name'),
            role=db_user.get('role'),
            account_id=db_user.get('account_id'),
            is_active=db_user.get('is_active', True),
            business_type=db_user.get('business_type'),
            business_role=db_user.get('business_role'),
            pin=db_user.get('pin'),
            created_at=db_user.get('created_at'),
            last_login=db_user.get('last_login')
        )


@dataclass
class ProductDTO:
    """Product data transfer object"""
    id: int
    name: str
    price: float
    cost: float
    quantity: float
    category: str
    account_id: str
    unit: str = "pcs"
    is_composite: bool = False
    recipe: Optional[List[Dict]] = None
    reorder_level: float = 0.0
    barcode: Optional[str] = None
    image: Optional[str] = None
    created_at: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_db(cls, db_product: Dict):
        """Create DTO from database record"""
        return cls(
            id=db_product.get('id'),
            name=db_product.get('name'),
            price=float(db_product.get('price', 0)),
            cost=float(db_product.get('cost', 0)),
            quantity=float(db_product.get('quantity', 0)),
            category=db_product.get('category', 'general'),
            account_id=db_product.get('account_id'),
            unit=db_product.get('unit', 'pcs'),
            is_composite=db_product.get('is_composite', False),
            recipe=db_product.get('recipe'),
            reorder_level=float(db_product.get('reorder_level', 0)),
            barcode=db_product.get('barcode'),
            image=db_product.get('image'),
            created_at=db_product.get('created_at')
        )


@dataclass
class SaleDTO:
    """Sale data transfer object"""
    id: int
    items: List[Dict]
    total: float
    total_cost: float
    gross_profit: float
    payment_method: str
    cashier_id: int
    cashier_name: str
    account_id: str
    amount_paid: float = 0.0
    change: float = 0.0
    created_at: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_db(cls, db_sale: Dict):
        """Create DTO from database record"""
        return cls(
            id=db_sale.get('id'),
            items=db_sale.get('items', []),
            total=float(db_sale.get('total', 0)),
            total_cost=float(db_sale.get('total_cost', 0)),
            gross_profit=float(db_sale.get('gross_profit', 0)),
            payment_method=db_sale.get('payment_method', 'cash'),
            cashier_id=db_sale.get('cashier_id'),
            cashier_name=db_sale.get('cashier_name', ''),
            account_id=db_sale.get('account_id'),
            amount_paid=float(db_sale.get('amount_paid', 0)),
            change=float(db_sale.get('change', 0)),
            created_at=db_sale.get('created_at')
        )


@dataclass
class WebSocketMessage:
    """Standardized WebSocket message format"""
    type: str  # Message type: update, notification, error, ping, pong
    action: Optional[str] = None  # Action: product_updated, sale_completed, etc.
    data: Optional[Any] = None
    account_id: Optional[str] = None
    user_id: Optional[int] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def update(cls, action: str, data: Any, account_id: str, user_id: int = None):
        """Create update message"""
        return cls(
            type='update',
            action=action,
            data=data,
            account_id=account_id,
            user_id=user_id
        )
    
    @classmethod
    def notification(cls, message: str, data: Any = None, account_id: str = None):
        """Create notification message"""
        return cls(
            type='notification',
            action='notify',
            data={'message': message, 'details': data},
            account_id=account_id
        )
    
    @classmethod
    def error(cls, message: str, details: Any = None):
        """Create error message"""
        return cls(
            type='error',
            action='error',
            data={'message': message, 'details': details}
        )


@dataclass
class ValidationError:
    """Validation error detail"""
    field: str
    message: str
    code: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


class DTOValidator:
    """Validates DTOs and request data"""
    
    @staticmethod
    def validate_user_create(data: Dict) -> List[ValidationError]:
        """Validate user creation data"""
        errors = []
        
        if not data.get('email'):
            errors.append(ValidationError('email', 'Email is required', 'required'))
        elif '@' not in data.get('email', ''):
            errors.append(ValidationError('email', 'Invalid email format', 'invalid'))
        
        if not data.get('password'):
            errors.append(ValidationError('password', 'Password is required', 'required'))
        elif len(data.get('password', '')) < 6:
            errors.append(ValidationError('password', 'Password must be at least 6 characters', 'min_length'))
        
        if not data.get('name'):
            errors.append(ValidationError('name', 'Name is required', 'required'))
        
        return errors
    
    @staticmethod
    def validate_product_create(data: Dict) -> List[ValidationError]:
        """Validate product creation data"""
        errors = []
        
        if not data.get('name'):
            errors.append(ValidationError('name', 'Product name is required', 'required'))
        
        if not data.get('price') or float(data.get('price', 0)) < 0:
            errors.append(ValidationError('price', 'Valid price is required', 'invalid'))
        
        if 'quantity' in data and float(data.get('quantity', 0)) < 0:
            errors.append(ValidationError('quantity', 'Quantity cannot be negative', 'invalid'))
        
        return errors
    
    @staticmethod
    def validate_sale_create(data: Dict) -> List[ValidationError]:
        """Validate sale creation data"""
        errors = []
        
        if not data.get('items') or not isinstance(data.get('items'), list):
            errors.append(ValidationError('items', 'Items array is required', 'required'))
        elif len(data.get('items', [])) == 0:
            errors.append(ValidationError('items', 'At least one item is required', 'required'))
        
        if not data.get('payment_method'):
            errors.append(ValidationError('payment_method', 'Payment method is required', 'required'))
        
        return errors
