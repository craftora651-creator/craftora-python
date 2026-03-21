"""
Craftora - Custom Exceptions Module
Centralized exception handling with detailed error messages and HTTP status codes.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Union
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)


# ==================== BASE EXCEPTIONS ====================

class CraftoraException(HTTPException):
    """Base exception for all Craftora exceptions."""
    
    def __init__(
        self,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail: str = "An error occurred",
        error_code: str = "INTERNAL_ERROR",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code
        self.metadata = metadata or {}
        
        # Log the exception
        logger.error(f"{error_code}: {detail}", extra=self.metadata)


# ==================== AUTHENTICATION EXCEPTIONS ====================

class UnauthorizedException(CraftoraException):
    """401 Unauthorized - Authentication required."""
    
    def __init__(
        self,
        detail: str = "Authentication required",
        error_code: str = "UNAUTHORIZED",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class InvalidCredentialsException(CraftoraException):
    """401 Invalid credentials."""
    
    def __init__(
        self,
        detail: str = "Invalid credentials",
        error_code: str = "INVALID_CREDENTIALS",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class TokenExpiredException(CraftoraException):
    """401 Token expired."""
    
    def __init__(
        self,
        detail: str = "Token has expired",
        error_code: str = "TOKEN_EXPIRED",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class TokenRevokedException(CraftoraException):
    """401 Token revoked."""
    
    def __init__(
        self,
        detail: str = "Token has been revoked",
        error_code: str = "TOKEN_REVOKED",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


# ==================== AUTHORIZATION EXCEPTIONS ====================

class ForbiddenException(CraftoraException):
    """403 Forbidden - Insufficient permissions."""
    
    def __init__(
        self,
        detail: str = "Insufficient permissions",
        error_code: str = "FORBIDDEN",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class RoleRequiredException(CraftoraException):
    """403 Specific role required."""
    
    def __init__(
        self,
        role: str,
        detail: Optional[str] = None,
        error_code: str = "ROLE_REQUIRED",
        metadata: Optional[Dict[str, Any]] = None
    ):
        detail = detail or f"{role} role required"
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class PermissionDeniedException(CraftoraException):
    """403 Permission denied."""
    
    def __init__(
        self,
        permission: str,
        detail: Optional[str] = None,
        error_code: str = "PERMISSION_DENIED",
        metadata: Optional[Dict[str, Any]] = None
    ):
        detail = detail or f"Permission '{permission}' denied"
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


# ==================== VALIDATION EXCEPTIONS ====================

class ValidationException(CraftoraException):
    """422 Validation error."""
    
    def __init__(
        self,
        detail: str = "Validation error",
        errors: Optional[List[Dict[str, Any]]] = None,
        error_code: str = "VALIDATION_ERROR",
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.errors = errors or []
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class InvalidInputException(CraftoraException):
    """400 Bad request - invalid input."""
    
    def __init__(
        self,
        detail: str = "Invalid input",
        field: Optional[str] = None,
        error_code: str = "INVALID_INPUT",
        metadata: Optional[Dict[str, Any]] = None
    ):
        if field:
            detail = f"Invalid input for field '{field}': {detail}"
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class ResourceExistsException(CraftoraException):
    """409 Conflict - resource already exists."""
    
    def __init__(
        self,
        resource_type: str,
        identifier: str,
        detail: Optional[str] = None,
        error_code: str = "RESOURCE_EXISTS",
        metadata: Optional[Dict[str, Any]] = None
    ):
        detail = detail or f"{resource_type} with identifier '{identifier}' already exists"
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


# ==================== NOT FOUND EXCEPTIONS ====================

class NotFoundException(CraftoraException):
    """404 Resource not found."""
    
    def __init__(
        self,
        resource_type: str,
        identifier: str,
        detail: Optional[str] = None,
        error_code: str = "NOT_FOUND",
        metadata: Optional[Dict[str, Any]] = None
    ):
        detail = detail or f"{resource_type} with identifier '{identifier}' not found"
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class UserNotFoundException(NotFoundException):
    """404 User not found."""
    
    def __init__(
        self,
        identifier: str,
        detail: Optional[str] = None,
        error_code: str = "USER_NOT_FOUND",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            resource_type="User",
            identifier=identifier,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class ShopNotFoundException(NotFoundException):
    """404 Shop not found."""
    
    def __init__(
        self,
        identifier: str,
        detail: Optional[str] = None,
        error_code: str = "SHOP_NOT_FOUND",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            resource_type="Shop",
            identifier=identifier,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class ProductNotFoundException(NotFoundException):
    """404 Product not found."""
    
    def __init__(
        self,
        identifier: str,
        detail: Optional[str] = None,
        error_code: str = "PRODUCT_NOT_FOUND",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            resource_type="Product",
            identifier=identifier,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class OrderNotFoundException(NotFoundException):
    """404 Order not found."""
    
    def __init__(
        self,
        identifier: str,
        detail: Optional[str] = None,
        error_code: str = "ORDER_NOT_FOUND",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            resource_type="Order",
            identifier=identifier,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


# ==================== BUSINESS LOGIC EXCEPTIONS ====================

class InsufficientStockException(CraftoraException):
    """400 Insufficient stock."""
    
    def __init__(
        self,
        product_name: str,
        requested: int,
        available: int,
        detail: Optional[str] = None,
        error_code: str = "INSUFFICIENT_STOCK",
        metadata: Optional[Dict[str, Any]] = None
    ):
        detail = detail or f"Insufficient stock for '{product_name}'. Requested: {requested}, Available: {available}"
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class PaymentRequiredException(CraftoraException):
    """402 Payment required."""
    
    def __init__(
        self,
        detail: str = "Payment required",
        error_code: str = "PAYMENT_REQUIRED",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class PaymentFailedException(CraftoraException):
    """402 Payment failed."""
    
    def __init__(
        self,
        detail: str = "Payment failed",
        error_code: str = "PAYMENT_FAILED",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class SubscriptionRequiredException(CraftoraException):
    """403 Subscription required."""
    
    def __init__(
        self,
        feature: str,
        detail: Optional[str] = None,
        error_code: str = "SUBSCRIPTION_REQUIRED",
        metadata: Optional[Dict[str, Any]] = None
    ):
        detail = detail or f"'{feature}' requires an active subscription"
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class ShopSuspendedException(CraftoraException):
    """403 Shop suspended."""
    
    def __init__(
        self,
        shop_name: str,
        reason: Optional[str] = None,
        detail: Optional[str] = None,
        error_code: str = "SHOP_SUSPENDED",
        metadata: Optional[Dict[str, Any]] = None
    ):
        detail = detail or f"Shop '{shop_name}' is suspended"
        if reason:
            detail += f". Reason: {reason}"
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class RateLimitException(CraftoraException):
    """429 Rate limit exceeded."""
    
    def __init__(
        self,
        detail: str = "Rate limit exceeded",
        retry_after: int = 60,
        error_code: str = "RATE_LIMIT_EXCEEDED",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )
        self.retry_after = retry_after


# ==================== EXTERNAL SERVICE EXCEPTIONS ====================

class ExternalServiceException(CraftoraException):
    """502 External service error."""
    
    def __init__(
        self,
        service: str,
        detail: Optional[str] = None,
        error_code: str = "EXTERNAL_SERVICE_ERROR",
        metadata: Optional[Dict[str, Any]] = None
    ):
        detail = detail or f"Error communicating with {service}"
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class StripeException(ExternalServiceException):
    """Stripe API error."""
    
    def __init__(
        self,
        detail: str = "Stripe payment error",
        stripe_error: Optional[Dict[str, Any]] = None,
        error_code: str = "STRIPE_ERROR",
        metadata: Optional[Dict[str, Any]] = None
    ):
        if stripe_error:
            detail = f"Stripe error: {stripe_error.get('message', detail)}"
        super().__init__(
            service="Stripe",
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class GoogleAuthException(ExternalServiceException):
    """Google OAuth error."""
    
    def __init__(
        self,
        detail: str = "Google authentication error",
        error_code: str = "GOOGLE_AUTH_ERROR",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            service="Google",
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class EmailServiceException(ExternalServiceException):
    """Email service error."""
    
    def __init__(
        self,
        detail: str = "Email service error",
        error_code: str = "EMAIL_SERVICE_ERROR",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            service="Email",
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class FileUploadException(ExternalServiceException):
    """File upload error."""
    
    def __init__(
        self,
        detail: str = "File upload error",
        error_code: str = "FILE_UPLOAD_ERROR",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            service="File Storage",
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


# ==================== DATABASE EXCEPTIONS ====================

class DatabaseException(CraftoraException):
    """500 Database error."""
    
    def __init__(
        self,
        detail: str = "Database error",
        error_code: str = "DATABASE_ERROR",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class ConstraintViolationException(DatabaseException):
    """Database constraint violation."""
    
    def __init__(
        self,
        constraint: str,
        detail: Optional[str] = None,
        error_code: str = "CONSTRAINT_VIOLATION",
        metadata: Optional[Dict[str, Any]] = None
    ):
        detail = detail or f"Database constraint violation: {constraint}"
        super().__init__(
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


class DeadlockException(DatabaseException):
    """Database deadlock."""
    
    def __init__(
        self,
        detail: str = "Database deadlock detected",
        error_code: str = "DEADLOCK",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


# ==================== EXCEPTION HANDLER ====================

async def craftora_exception_handler(request, exc: CraftoraException):
    """Global exception handler for Craftora exceptions."""
    
    error_response = {
        "error": {
            "code": exc.error_code,
            "message": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "path": request.url.path,
            "method": request.method,
        }
    }
    
    # Add metadata if available (non-sensitive data only)
    if exc.metadata and not exc.metadata.get("sensitive", True):
        error_response["error"]["metadata"] = {
            k: v for k, v in exc.metadata.items() 
            if k != "sensitive"
        }
    
    # Add validation errors if present
    if hasattr(exc, 'errors') and exc.errors:
        error_response["error"]["validation_errors"] = exc.errors
    
    # Add retry-after header for rate limiting
    if isinstance(exc, RateLimitException):
        headers = {"Retry-After": str(exc.retry_after)}
    else:
        headers = {}
    
    logger.error(
        f"{exc.error_code}: {exc.detail}",
        extra={
            "status_code": exc.status_code,
            "path": request.url.path,
            "method": request.method,
            **exc.metadata
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response,
        headers=headers
    )


async def generic_exception_handler(request, exc: Exception):
    """Handler for unhandled exceptions."""
    from datetime import datetime, timezone
    import traceback
    
    # Get environment safely
    def get_env():
        import os
        return os.getenv("ENVIRONMENT", "production")
    
    # Log the exception
    logger.exception(
        f"Unhandled exception: {type(exc).__name__}: {str(exc)}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "client_ip": request.client.host if request.client else None,
            "environment": get_env()
        }
    )
    
    # Create timestamp
    timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    # Build error response
    error_response = {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An internal server error occurred",
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "timestamp": timestamp,
            "path": request.url.path,
            "method": request.method,
        }
    }
    
    # Add debug info in development
    if get_env() == "development":
        error_response["error"]["debug"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exception(type(exc), exc, exc.__traceback__)
        }
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response
    )


class WebhookVerificationException(CraftoraException):
    """Webhook signature verification failed."""
    
class MaintenanceModeException(CraftoraException):
    """System is in maintenance mode."""
    
class ThirdPartyAPIException(CraftoraException):
    """Third-party API call failed."""

class AppleAuthException(ExternalServiceException):
    """Apple Sign-In error."""
    
    def __init__(
        self,
        detail: str = "Apple authentication error",
        error_code: str = "APPLE_AUTH_ERROR",
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            service="Apple",
            detail=detail,
            error_code=error_code,
            metadata=metadata
        )


# Export all exceptions
__all__ = [
    "CraftoraException",
    "UnauthorizedException",
    "InvalidCredentialsException",
    "TokenExpiredException",
    "TokenRevokedException",
    "ForbiddenException",
    "RoleRequiredException",
    "PermissionDeniedException",
    "ValidationException",
    "InvalidInputException",
    "ResourceExistsException",
    "NotFoundException",
    "UserNotFoundException",
    "ShopNotFoundException",
    "ProductNotFoundException",
    "OrderNotFoundException",
    "InsufficientStockException",
    "PaymentRequiredException",
    "PaymentFailedException",
    "SubscriptionRequiredException",
    "ShopSuspendedException",
    "RateLimitException",
    "ExternalServiceException",
    "StripeException",
    "GoogleAuthException",
    "EmailServiceException",
    "FileUploadException",
    "DatabaseException",
    "ConstraintViolationException",
    "DeadlockException",
    "craftora_exception_handler",
    "generic_exception_handler",
]