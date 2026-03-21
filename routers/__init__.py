"""
Pydantic schemas for Craftora API.
Placed in 'routers' folder but contains only schemas, not endpoints.
Endpoints will be in 'api/v1/' folder.
"""

from routers.base import (
    BaseSchema, TimestampSchema, IDSchema,
    PaginationParams, PaginatedResponse,
    SuccessResponse, ErrorResponse, ValidationError
)

from routers.auth import (
    GoogleAuthRequest,
    TokenResponse, RefreshTokenRequest,
    LoginRequest, RegisterRequest,
    ForgotPasswordRequest, ResetPasswordRequest,
    VerifyEmailRequest, AuthUserResponse
)

from routers.users import (
    UserCreate, UserUpdate, 
    UserResponse, UserPublic, UserAdmin
)

from routers.shops import (
    ShopCreate, ShopUpdate,
    ShopResponse, ShopPublic, ShopSeller, ShopAdmin
)

from routers.products import (
    ProductCreate, ProductUpdate,
    ProductResponse, ProductPublic, ProductSeller
)

from routers.carts import (
    CartCreate, CartUpdate, CartResponse,
    CartItemCreate, CartItemUpdate, CartItemResponse
)

from routers.orders import (
    OrderCreate, OrderUpdate, OrderResponse,
    OrderCustomer, OrderSeller, OrderStatusUpdate
)

from routers.payments import (
    PaymentCreate, PaymentResponse,
    PaymentIntentCreate, PaymentIntentResponse,
    WebhookEvent
)

__all__ = [
    # Base schemas
    "BaseSchema", "TimestampSchema", "IDSchema",
    "PaginationParams", "PaginatedResponse",
    "SuccessResponse", "ErrorResponse", "ValidationError",
    
    # Auth schemas
    "GoogleAuthRequest",
    "TokenResponse", "RefreshTokenRequest",
    "LoginRequest", "RegisterRequest",
    "ForgotPasswordRequest", "ResetPasswordRequest",
    "VerifyEmailRequest", "AuthUserResponse",
    
    # User schemas
    "UserCreate", "UserUpdate", 
    "UserResponse", "UserPublic", "UserAdmin",
    
    # Shop schemas
    "ShopCreate", "ShopUpdate",
    "ShopResponse", "ShopPublic", "ShopSeller", "ShopAdmin",
    
    # Product schemas
    "ProductCreate", "ProductUpdate",
    "ProductResponse", "ProductPublic", "ProductSeller",
    
    # Cart schemas
    "CartCreate", "CartUpdate", "CartResponse",
    "CartItemCreate", "CartItemUpdate", "CartItemResponse",
    
    # Order schemas
    "OrderCreate", "OrderUpdate", "OrderResponse",
    "OrderCustomer", "OrderSeller", "OrderStatusUpdate",
    
    # Payment schemas
    "PaymentCreate", "PaymentResponse",
    "PaymentIntentCreate", "PaymentIntentResponse",
    "WebhookEvent"
]