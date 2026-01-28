"""
Middleware Components
=====================
Request/response middleware for validation, logging, and transformation.
"""

import logging
import time
from functools import wraps
from flask import request, jsonify, g
from typing import Callable
from dto import ApiResponse, DTOValidator, ValidationError

logger = logging.getLogger(__name__)


def request_logger(f: Callable) -> Callable:
    """
    Log all incoming requests with timing
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        start_time = time.time()
        
        # Log request
        logger.info(f"➡️  {request.method} {request.path} from {request.remote_addr}")
        
        # Execute endpoint
        response = f(*args, **kwargs)
        
        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000
        
        # Log response
        status_code = response[1] if isinstance(response, tuple) else 200
        logger.info(f"⬅️  {request.method} {request.path} → {status_code} ({duration_ms:.2f}ms)")
        
        # Add performance header
        if isinstance(response, tuple):
            response_data, status, headers = response if len(response) == 3 else (*response, {})
            headers['X-Response-Time'] = f"{duration_ms:.2f}ms"
            return response_data, status, headers
        
        return response
    
    return decorated_function


def validate_json(validator_func: Callable = None):
    """
    Validate JSON request body
    
    Usage:
        @validate_json(DTOValidator.validate_product_create)
        def create_product():
            data = request.get_json()
            # data is validated
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check content type
            if not request.is_json:
                response = ApiResponse.error(
                    message="Content-Type must be application/json",
                    errors=[{'field': 'content-type', 'message': 'Invalid content type'}]
                )
                return jsonify(response.to_dict()), 400
            
            # Get JSON data
            try:
                data = request.get_json()
            except Exception as e:
                response = ApiResponse.error(
                    message="Invalid JSON in request body",
                    errors=[{'field': 'body', 'message': str(e)}]
                )
                return jsonify(response.to_dict()), 400
            
            # Validate if validator provided
            if validator_func:
                validation_errors = validator_func(data)
                if validation_errors:
                    response = ApiResponse.error(
                        message="Validation failed",
                        errors=[e.to_dict() for e in validation_errors]
                    )
                    return jsonify(response.to_dict()), 400
            
            # Store validated data in g for endpoint to use
            g.validated_data = data
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def error_handler(f: Callable) -> Callable:
    """
    Catch and format exceptions consistently
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"Validation error: {e}")
            response = ApiResponse.error(
                message=str(e),
                errors=[{'field': 'validation', 'message': str(e)}]
            )
            return jsonify(response.to_dict()), 400
        except PermissionError as e:
            logger.warning(f"Permission denied: {e}")
            response = ApiResponse.error(message="Permission denied")
            return jsonify(response.to_dict()), 403
        except Exception as e:
            logger.exception(f"Unexpected error in {f.__name__}")
            response = ApiResponse.error(
                message="An unexpected error occurred",
                errors=[{'field': 'server', 'message': 'Internal server error'}]
            )
            return jsonify(response.to_dict()), 500
    
    return decorated_function


def paginate(query_results: list, page: int = 1, per_page: int = 50) -> tuple:
    """
    Paginate query results
    
    Returns:
        (paginated_items, pagination_meta)
    """
    from dto import PaginationMeta
    
    total = len(query_results)
    total_pages = (total + per_page - 1) // per_page  # Ceiling division
    
    start = (page - 1) * per_page
    end = start + per_page
    
    items = query_results[start:end]
    
    meta = PaginationMeta(
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1
    )
    
    return items, meta


def get_pagination_params() -> tuple:
    """
    Extract pagination parameters from request
    
    Returns:
        (page, per_page)
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    # Enforce limits
    page = max(1, page)
    per_page = min(max(1, per_page), 100)  # Max 100 items per page
    
    return page, per_page


def require_fields(*fields):
    """
    Ensure required fields are present in request JSON
    
    Usage:
        @require_fields('email', 'password')
        def login():
            data = request.get_json()
            # email and password are guaranteed to exist
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            data = request.get_json()
            
            missing = []
            for field in fields:
                if field not in data or data[field] is None or data[field] == '':
                    missing.append(field)
            
            if missing:
                response = ApiResponse.error(
                    message=f"Missing required fields: {', '.join(missing)}",
                    errors=[{'field': f, 'message': 'Required field'} for f in missing]
                )
                return jsonify(response.to_dict()), 400
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def standardize_response(f: Callable) -> Callable:
    """
    Automatically wrap responses in ApiResponse format
    
    Usage:
        @standardize_response
        def get_products():
            return products, 200  # Will be wrapped in ApiResponse
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        result = f(*args, **kwargs)
        
        # If already an ApiResponse, return as-is
        if isinstance(result, tuple) and len(result) >= 2:
            data, status_code = result[0], result[1]
            if isinstance(data, dict) and 'status' in data:
                return result
        
        # Wrap in ApiResponse
        if isinstance(result, tuple):
            data, status_code = result[0], result[1]
            
            if 200 <= status_code < 300:
                response = ApiResponse.success(data=data)
            else:
                response = ApiResponse.error(
                    message=data.get('error', 'An error occurred') if isinstance(data, dict) else str(data)
                )
            
            return jsonify(response.to_dict()), status_code
        
        return result
    
    return decorated_function


class RequestContext:
    """
    Store request context data that needs to be accessed across middleware
    """
    def __init__(self):
        self.user = None
        self.account_id = None
        self.start_time = None
        self.request_id = None
    
    @classmethod
    def from_request(cls):
        """Get or create request context"""
        if not hasattr(g, 'request_context'):
            g.request_context = cls()
            g.request_context.start_time = time.time()
        return g.request_context
