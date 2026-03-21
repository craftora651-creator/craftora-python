"""
Craftora - FastAPI Dependencies Module
Centralized dependency injection for authorization, pagination, filtering, and more.
"""

from typing import Optional, Dict, Any, List, Union
from fastapi import Depends, HTTPException, status, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt

from database.database import get_db
from config.config import settings
from helpers.security import get_current_user_clean, get_current_active_user, get_current_verified_user
from nix.exceptions import (
    UnauthorizedException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
    RateLimitException
)
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ==================== AUTH DEPENDENCIES ====================

class RoleChecker:
    """Dependency to check user roles."""
    
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles
    
    def __call__(self, current_user: Dict[str, Any] = Depends(get_current_active_user)):
        if current_user.get("role") not in self.allowed_roles:
            raise ForbiddenException(
                detail=f"Access denied. Required roles: {', '.join(self.allowed_roles)}"
            )
        return current_user


class PermissionChecker:
    """Dependency to check user permissions."""
    
    def __init__(self, required_permission: str):
        self.required_permission = required_permission
    
    def __call__(self, current_user: Dict[str, Any] = Depends(get_current_active_user)):
        user_permissions = current_user.get("permissions", [])
        if self.required_permission not in user_permissions:
            raise ForbiddenException(
                detail=f"Permission '{self.required_permission}' required"
            )
        return current_user


# Role-specific dependencies
require_admin = RoleChecker(["admin"])
require_seller = RoleChecker(["seller", "admin"])
require_verified_seller = RoleChecker(["seller", "admin"])  # TODO: Add verification check

# Permission-based dependencies
can_create_shop = PermissionChecker("shop:create")
can_manage_products = PermissionChecker("products:manage")
can_view_analytics = PermissionChecker("analytics:view")


# ==================== RESOURCE OWNERSHIP ====================

async def require_shop_ownership(
    shop_id: str,
    current_user: Dict[str, Any] = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Verify user owns the shop or is admin."""
    from models.shop import Shop
    
    # Admin can access any shop
    if current_user.get("role") == "admin":
        return current_user
    
    try:
        from sqlalchemy import select
        result = await db.execute(
            select(Shop).where(
                Shop.id == shop_id,
                Shop.owner_id == current_user.get("sub"),
                Shop.is_active == True
            )
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            raise ForbiddenException(detail="You don't have access to this shop")
        
        return current_user
        
    except Exception as e:
        logger.error(f"Shop ownership check failed: {e}")
        raise ForbiddenException(detail="Shop access verification failed")


async def require_product_ownership(
    product_id: str,
    current_user: Dict[str, Any] = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Verify user owns the product or is admin."""
    from models.product import Product
    from models.shop import Shop
    
    # Admin can access any product
    if current_user.get("role") == "admin":
        return current_user
    
    try:
        from sqlalchemy import select, join
        result = await db.execute(
            select(Product).join(Shop).where(
                Product.id == product_id,
                Shop.owner_id == current_user.get("sub"),
                Product.is_active == True
            )
        )
        product = result.scalar_one_or_none()
        
        if not product:
            raise ForbiddenException(detail="You don't have access to this product")
        
        return current_user
        
    except Exception as e:
        logger.error(f"Product ownership check failed: {e}")
        raise ForbiddenException(detail="Product access verification failed")


# ==================== PAGINATION & FILTERING ====================

class PaginationParams:
    """Pagination dependency."""
    
    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(20, ge=1, le=100, description="Items per page"),
        sort_by: Optional[str] = Query(None, description="Field to sort by"),
        sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order")
    ):
        self.page = page
        self.page_size = page_size
        self.sort_by = sort_by
        self.sort_order = sort_order
        self.offset = (page - 1) * page_size
        self.limit = page_size


class SearchParams:
    """Search and filter dependency."""
    
    def __init__(
        self,
        q: Optional[str] = Query(None, description="Search query"),
        category: Optional[str] = Query(None, description="Category filter"),
        min_price: Optional[float] = Query(None, ge=0, description="Minimum price"),
        max_price: Optional[float] = Query(None, ge=0, description="Maximum price"),
        status: Optional[str] = Query(None, description="Status filter"),
        tags: Optional[List[str]] = Query(None, description="Tags filter"),
        date_from: Optional[datetime] = Query(None, description="Start date"),
        date_to: Optional[datetime] = Query(None, description="End date")
    ):
        self.q = q
        self.category = category
        self.min_price = min_price
        self.max_price = max_price
        self.status = status
        self.tags = tags
        self.date_from = date_from
        self.date_to = date_to
        
        # Validate price range
        if min_price is not None and max_price is not None:
            if min_price > max_price:
                raise ValidationException(detail="min_price cannot be greater than max_price")


# ==================== RATE LIMITING ====================

class RateLimiter:
    """Redis-based rate limiting."""
    
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.redis_client = None
    
    async def _get_redis(self):
        if not self.redis_client:
            import redis.asyncio as redis
            self.redis_client = redis.from_url(settings.REDIS_URL)
        return self.redis_client
    
    async def __call__(self, request: Request):
        if not settings.RATE_LIMIT_ENABLED:
            return
        
        redis_client = await self._get_redis()
        client_ip = request.client.host
        path = request.url.path
        key = f"rate_limit:{client_ip}:{path}"
        
        # Use Redis INCR with expiry
        current = await redis_client.incr(key)
        if current == 1:
            await redis_client.expire(key, 60)
        
        if current > self.requests_per_minute:
            raise RateLimitException(
                detail=f"Rate limit exceeded. Maximum {self.requests_per_minute} requests per minute."
            )

# Global rate limiter instance
rate_limiter = RateLimiter(requests_per_minute=settings.RATE_LIMIT_REQUESTS)


# ==================== CACHE DEPENDENCIES ====================

class CacheControl:
    """Cache control headers dependency."""
    
    def __init__(
        self,
        max_age: int = 300,
        stale_while_revalidate: int = 60,
        public: bool = True
    ):
        self.max_age = max_age
        self.stale_while_revalidate = stale_while_revalidate
        self.public = public
    
    async def __call__(self):
        cache_header = f"{'public' if self.public else 'private'}, max-age={self.max_age}"
        if self.stale_while_revalidate:
            cache_header += f", stale-while-revalidate={self.stale_while_revalidate}"
        
        return {"Cache-Control": cache_header}


# ==================== REQUEST VALIDATION ====================

class RequestValidator:
    """Request validation dependency."""
    
    def __init__(self, required_fields: Optional[List[str]] = None):
        self.required_fields = required_fields or []
    
    async def __call__(self, request: Request):
        # Check content type
        content_type = request.headers.get("Content-Type", "")
        if request.method in ["POST", "PUT", "PATCH"]:
            if "application/json" not in content_type:
                raise ValidationException(
                    detail="Content-Type must be application/json"
                )
        
        # Check required headers
        user_agent = request.headers.get("User-Agent")
        if not user_agent:
            raise ValidationException(
                detail="User-Agent header is required"
            )
        
        return request


# ==================== SHOP SUBDOMAIN ====================

async def get_shop_from_subdomain(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Optional[Dict[str, Any]]:
    """Extract shop from subdomain."""
    from models.shop import Shop
    
    host = request.headers.get("host", "")
    subdomain = host.split(".")[0] if "." in host else None
    
    if subdomain and subdomain not in ["www", "api", "admin"]:
        try:
            from sqlalchemy import select
            result = await db.execute(
                select(Shop).where(
                    Shop.subdomain == subdomain,
                    Shop.is_active == True,
                    Shop.is_approved == True
                )
            )
            shop = result.scalar_one_or_none()
            
            if shop:
                return {
                    "shop_id": shop.id,
                    "shop_name": shop.name,
                    "subdomain": shop.subdomain,
                    "owner_id": shop.owner_id
                }
                
        except Exception as e:
            logger.error(f"Subdomain shop lookup failed: {e}")
    
    return None


# ==================== FILE UPLOAD VALIDATION ====================

class FileUploadValidator:
    """Validate file uploads."""
    
    def __init__(
        self,
        max_size_mb: int = 100,
        allowed_types: Optional[List[str]] = None
    ):
        self.max_size = max_size_mb * 1024 * 1024
        self.allowed_types = allowed_types or settings.ALLOWED_FILE_TYPES
    
    async def __call__(self, file):
        # Check file size
        if file.size > self.max_size:
            raise ValidationException(
                detail=f"File size exceeds maximum {self.max_size / (1024*1024)}MB"
            )
        
        # Check file type
        if file.content_type not in self.allowed_types:
            raise ValidationException(
                detail=f"File type {file.content_type} not allowed. Allowed types: {', '.join(self.allowed_types)}"
            )
        
        return file


# ==================== API KEY AUTHENTICATION ====================

class APIKeyAuth:
    """API Key authentication for external services."""
    
    def __init__(self):
        self.scheme = HTTPBearer(auto_error=False)
    
    async def __call__(
        self,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
    ):
        if not credentials:
            raise UnauthorizedException(detail="API Key required")
        
        api_key = credentials.credentials
        
        # Validate API key (in production, check against database)
        valid_keys = settings.VALID_API_KEYS if hasattr(settings, "VALID_API_KEYS") else []
        
        if api_key not in valid_keys:
            raise ForbiddenException(detail="Invalid API Key")
        
        return {"api_key": api_key, "auth_type": "api_key"}


# ==================== EXPORT DEPENDENCIES ====================

class ExportParams:
    """Export parameters dependency."""
    
    def __init__(
        self,
        format: str = Query("csv", pattern="^(csv|json|excel)$", description="Export format"),
        fields: Optional[str] = Query(None, description="Comma-separated fields to export"),
        include_metadata: bool = Query(False, description="Include metadata"),
        compress: bool = Query(False, description="Compress output")
    ):
        self.format = format
        self.fields = fields.split(",") if fields else None
        self.include_metadata = include_metadata
        self.compress = compress


# ==================== WEBHOOK VERIFICATION ====================

class WebhookVerifier:
    """Verify webhook signatures."""
    
    def __init__(self, service: str):
        self.service = service
    
    async def __call__(self, request: Request):
        signature = request.headers.get(f"X-{self.service}-Signature")
        timestamp = request.headers.get(f"X-{self.service}-Timestamp")
        
        if not signature or not timestamp:
            raise UnauthorizedException(
                detail=f"{self.service} webhook signature required"
            )
        
        # Verify timestamp (prevent replay attacks)
        current_time = datetime.now().timestamp()
        if abs(current_time - float(timestamp)) > 300:  # 5 minutes tolerance
            raise ForbiddenException(detail="Webhook timestamp expired")
        
        # Verify signature (implementation depends on service)
        body = await request.body()
        if not self._verify_signature(body, signature, timestamp):
            raise ForbiddenException(detail="Invalid webhook signature")
        
        return body
    
    def _verify_signature(self, body: bytes, signature: str, timestamp: str) -> bool:
        """Verify webhook signature (implement per service)."""
        # TODO: Implement signature verification for Stripe, PayPal, etc.
        return True


# ==================== BULK OPERATIONS ====================

class BulkOperationValidator:
    """Validate bulk operation requests."""
    
    def __init__(self, max_items: int = 100):
        self.max_items = max_items
    
    async def __call__(self, items: List[Any]):
        if len(items) > self.max_items:
            raise ValidationException(
                detail=f"Maximum {self.max_items} items allowed in bulk operation"
            )
        
        if not items:
            raise ValidationException(detail="No items provided")
        
        return items


# Ekle: İki faktörlü doğrulama dependency'si
class TwoFactorRequired:
    """Require 2FA for sensitive operations."""
    
    async def __call__(self, current_user: Dict = Depends(get_current_user_clean)):
        if current_user.get("requires_2fa") and not current_user.get("2fa_verified"):
            raise ForbiddenException(detail="Two-factor authentication required")
        return current_user

# Ekle: Geo-blocking
class GeoBlockChecker:
    """Block requests from specific countries."""
    
    BLOCKED_COUNTRIES = ["RU", "CN", "KP"]  # Örnek
    
    async def __call__(self, request: Request):
        country = await self._get_country_from_ip(request.client.host)
        if country in self.BLOCKED_COUNTRIES:
            raise ForbiddenException(detail=f"Access blocked from {country}")

async def require_verified_seller(
    current_user: Dict[str, Any] = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Require verified seller status."""
    from models.user import User
    from sqlalchemy import select
    
    if current_user.get("role") != "seller":
        raise ForbiddenException(detail="Seller account required")
    
    result = await db.execute(
        select(User).where(
            User.id == current_user.get("sub"),
            User.seller_verified == True
        )
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise ForbiddenException(detail="Seller verification required")
    
    return current_user


# Export commonly used dependencies
__all__ = [
    "get_db",
    "get_current_active_user",
    "get_current_verified_user",
    "require_admin",
    "require_seller",
    "require_shop_ownership",
    "require_product_ownership",
    "PaginationParams",
    "SearchParams",
    "rate_limiter",
    "CacheControl",
    "FileUploadValidator",
    "APIKeyAuth",
    "ExportParams",
    "WebhookVerifier",
    "BulkOperationValidator",
]