"""
Auth Package
============
Clean, modular authentication system for the POS backend.
"""

from .manager import AuthManager
from .service import AuthService
from .routes import create_auth_blueprint, create_main_admin_auth_blueprint
from .decorators import require_auth, require_admin, require_main_admin, require_business_admin

__all__ = [
    "AuthManager",
    "AuthService",
    "create_auth_blueprint",
    "create_main_admin_auth_blueprint",
    "require_auth",
    "require_admin",
    "require_main_admin",
    "require_business_admin",
]
