"""
API Router
==========
Centralized API routing with versioning and documentation.
"""

from flask import Blueprint, jsonify, request
from dto import ApiResponse
from middleware import request_logger, error_handler, standardize_response
import logging

logger = logging.getLogger(__name__)


def create_api_v1(datastore, auth, admin, cashier):
    """
    Create API v1 routes
    
    Standardized, versioned API with consistent response formats
    """
    api_v1 = Blueprint('api_v1', __name__, url_prefix='/api/v1')
    
    # ============================================================
    # API INFO & HEALTH
    # ============================================================
    
    @api_v1.route('/', methods=['GET'])
    def api_info():
        """API information and available endpoints"""
        return jsonify(ApiResponse.success(data={
            'version': '1.0',
            'name': 'Universal POS API',
            'description': 'Multi-tenant POS system with Pro/Custom plan support',
            'endpoints': {
                'auth': '/api/v1/auth',
                'products': '/api/v1/products',
                'sales': '/api/v1/sales',
                'users': '/api/v1/users',
                'analytics': '/api/v1/analytics'
            },
            'documentation': '/api/v1/docs'
        }).to_dict()), 200
    
    @api_v1.route('/health', methods=['GET'])
    def health_check():
        """Detailed health check"""
        try:
            # Check database
            db_healthy = True
            try:
                datastore.get_by_id('accounts', 'health-check')
            except:
                db_healthy = False
            
            health_status = {
                'database': 'healthy' if db_healthy else 'unhealthy',
                'api_version': '1.0',
                'timestamp': ApiResponse.success().timestamp
            }
            
            status_code = 200 if db_healthy else 503
            
            return jsonify(ApiResponse.success(data=health_status).to_dict()), status_code
        except Exception as e:
            logger.exception("Health check failed")
            return jsonify(ApiResponse.error(message="Health check failed").to_dict()), 503
    
    # ============================================================
    # AUTHENTICATION ROUTES
    # ============================================================
    
    @api_v1.route('/auth/signup', methods=['POST'])
    @error_handler
    @standardize_response
    def signup():
        """User signup"""
        from middleware import require_fields
        from dto import DTOValidator
        
        data = request.get_json()
        
        # Validate
        errors = DTOValidator.validate_user_create(data)
        if errors:
            response = ApiResponse.error(
                message="Validation failed",
                errors=[e.to_dict() for e in errors]
            )
            return jsonify(response.to_dict()), 400
        
        # Create user
        success, error, result = auth.signup(
            email=data['email'],
            password=data['password'],
            name=data['name'],
            plan=data.get('plan', 'free'),
            business_type=data.get('business_type')
        )
        
        if success:
            return ApiResponse.success(
                data=result,
                message="Account created successfully"
            ).to_dict(), 201
        else:
            return ApiResponse.error(message=error).to_dict(), 400
    
    @api_v1.route('/auth/login', methods=['POST'])
    @error_handler
    @standardize_response
    def login():
        """User login"""
        data = request.get_json()
        
        if not data.get('email') or not data.get('password'):
            return ApiResponse.error(message="Email and password required").to_dict(), 400
        
        success, error, result = auth.login(
            email=data['email'],
            password=data['password']
        )
        
        if success:
            return ApiResponse.success(
                data=result,
                message="Login successful"
            ).to_dict(), 200
        else:
            return ApiResponse.error(message=error).to_dict(), 401
    
    # ============================================================
    # PRODUCTS ROUTES
    # ============================================================
    
    @api_v1.route('/products', methods=['GET'])
    @auth.require_auth
    @error_handler
    @standardize_response
    def get_products():
        """Get all products with pagination"""
        from middleware import get_pagination_params, paginate
        
        payload = auth.verify_token(request.headers.get('Authorization', '').replace('Bearer ', ''))
        account_id = payload['account_id']
        
        # Get products
        products = admin.get_products(account_id)
        
        # Pagination
        page, per_page = get_pagination_params()
        items, meta = paginate(products, page, per_page)
        
        return ApiResponse.success(
            data=items,
            meta={'pagination': meta.to_dict()}
        ).to_dict(), 200
    
    @api_v1.route('/products', methods=['POST'])
    @auth.require_auth
    @error_handler
    @standardize_response
    def create_product():
        """Create new product"""
        from dto import DTOValidator
        
        payload = auth.verify_token(request.headers.get('Authorization', '').replace('Bearer ', ''))
        data = request.get_json()
        
        # Validate
        errors = DTOValidator.validate_product_create(data)
        if errors:
            return ApiResponse.error(
                message="Validation failed",
                errors=[e.to_dict() for e in errors]
            ).to_dict(), 400
        
        # Create product
        success, error, product = admin.create_product(
            account_id=payload['account_id'],
            created_by=payload['user_id'],
            **data
        )
        
        if success:
            return ApiResponse.success(
                data=product,
                message="Product created successfully"
            ).to_dict(), 201
        else:
            return ApiResponse.error(message=error).to_dict(), 400
    
    @api_v1.route('/products/<int:product_id>', methods=['GET'])
    @auth.require_auth
    @error_handler
    @standardize_response
    def get_product(product_id):
        """Get single product"""
        payload = auth.verify_token(request.headers.get('Authorization', '').replace('Bearer ', ''))
        
        product = datastore.get_by_id('products', product_id, payload['account_id'])
        
        if product:
            return ApiResponse.success(data=product).to_dict(), 200
        else:
            return ApiResponse.error(message="Product not found").to_dict(), 404
    
    # ============================================================
    # SALES ROUTES
    # ============================================================
    
    @api_v1.route('/sales', methods=['POST'])
    @auth.require_auth
    @error_handler
    @standardize_response
    def complete_sale():
        """Complete sale transaction"""
        from dto import DTOValidator
        
        payload = auth.verify_token(request.headers.get('Authorization', '').replace('Bearer ', ''))
        data = request.get_json()
        
        # Validate
        errors = DTOValidator.validate_sale_create(data)
        if errors:
            return ApiResponse.error(
                message="Validation failed",
                errors=[e.to_dict() for e in errors]
            ).to_dict(), 400
        
        # Complete sale
        success, error, sale = cashier.complete_sale(
            account_id=payload['account_id'],
            cashier_id=payload['user_id'],
            cashier_name=payload.get('name', 'Cashier'),
            items=data['items'],
            payment_method=data.get('payment_method', 'cash'),
            amount_paid=data.get('amount_paid', 0),
            tax_rate=data.get('tax_rate', 0),
            discount_amount=data.get('discount_amount', 0)
        )
        
        if success:
            return ApiResponse.success(
                data=sale,
                message="Sale completed successfully"
            ).to_dict(), 201
        else:
            return ApiResponse.error(message=error).to_dict(), 400
    
    @api_v1.route('/sales', methods=['GET'])
    @auth.require_auth
    @error_handler
    @standardize_response
    def get_sales():
        """Get sales with pagination"""
        from middleware import get_pagination_params, paginate
        
        payload = auth.verify_token(request.headers.get('Authorization', '').replace('Bearer ', ''))
        
        # Get sales
        sales = cashier.get_sales(payload['account_id'])
        
        # Pagination
        page, per_page = get_pagination_params()
        items, meta = paginate(sales, page, per_page)
        
        return ApiResponse.success(
            data=items,
            meta={'pagination': meta.to_dict()}
        ).to_dict(), 200
    
    return api_v1


def create_websocket_protocol():
    """
    Standardized WebSocket message protocol
    
    All WebSocket messages follow this format:
    {
        "type": "update" | "notification" | "error" | "ping" | "pong",
        "action": "product_updated" | "sale_completed" | etc.,
        "data": {...},
        "account_id": "...",
        "timestamp": "..."
    }
    """
    from dto import WebSocketMessage
    
    protocol = {
        'version': '1.0',
        'message_format': WebSocketMessage(
            type='example',
            action='example_action',
            data={'key': 'value'}
        ).to_dict(),
        'message_types': {
            'update': 'Data update notification',
            'notification': 'User notification',
            'error': 'Error message',
            'ping': 'Keep-alive ping',
            'pong': 'Keep-alive pong response'
        },
        'actions': {
            'product_created': 'New product added',
            'product_updated': 'Product modified',
            'product_deleted': 'Product removed',
            'sale_completed': 'Sale transaction completed',
            'stock_updated': 'Product stock changed',
            'low_stock_alert': 'Product below reorder level'
        }
    }
    
    return protocol
