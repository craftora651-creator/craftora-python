from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from enum import Enum
from pydantic import field_validator
from pydantic import BaseModel, Field, EmailStr, ConfigDict, field_validator, ValidationInfo
from typing import Any
from pydantic import BaseModel
from typing import Optional

# ==================== ENUMS ====================

class UserRole(str, Enum):
    """User roles enum."""
    USER = "user"
    SELLER = "seller"
    ADMIN = "admin"


class SellerPlan(str, Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    PREMIUM = "premium"
    BANNED = "banned"
    SUSPENDED = "suspended"


class AuthProvider(str, Enum):
    """Authentication provider enum (NEW)."""
    GOOGLE = "google"
    APPLE = "apple"


# ==================== BASE SCHEMAS ====================

class BaseSchema(BaseModel):
    """Base schema with common config."""
    model_config = ConfigDict(from_attributes=True)


class TimestampSchema(BaseSchema):
    """Schema with timestamps."""
    created_at: datetime
    updated_at: Optional[datetime] = None


class PaginationParams(BaseSchema):
    """Pagination parameters."""
    page: int = Field(1, ge=1)
    limit: int = Field(20, ge=1, le=100)
    sort_by: Optional[str] = None
    sort_order: Optional[str] = Field("desc", pattern="^(asc|desc)$")


# ==================== AUTHENTICATION SCHEMAS ====================


class RefreshTokenRequest(BaseModel):
    refresh_token: str

# ==================== SELLER SCHEMAS ====================

class BecomeSellerRequest(BaseModel):
    shop_name: Optional[str] = None
    shop_description: Optional[str] = None



class TokenResponse(BaseModel):
    """Token response for authentication endpoints."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: Optional[str] = Field(None, description="Refresh token for getting new access tokens")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(3600, description="Token expiry in seconds")


class AuthResponse(TokenResponse):
    """Authentication response with user data (NEW)."""
    user: Dict[str, Any] = Field(..., description="User information")
    is_new_user: bool = Field(False, description="Whether this is a new user")


class AppleAuthRequest(BaseModel):
    """Apple Sign-In request (NEW)."""
    identity_token: str = Field(..., description="Apple JWT identity token")
    authorization_code: str = Field(..., description="Apple authorization code")
    user: Optional[Dict[str, Any]] = Field(None, description="Apple user info (only on first login)")


class GoogleAuthRequest(BaseModel):
    """Google OAuth request (NEW)."""
    id_token: str = Field(..., description="Google JWT ID token")
    access_token: Optional[str] = Field(None, description="Google OAuth access token")

# ==================== USER SCHEMAS ====================

class UserBase(BaseSchema):
    """Base user schema with common fields."""
    email: EmailStr
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    avatar_url: Optional[str] = Field(None, max_length=500)
    phone_number: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$")  # ✅ phone -> phone_nu


# ✅ YENİ SQL UYUMLU UserCreate:
# ✅ DOĞRU PYDANTIC V2 VALIDATOR FORMATI:

class UserCreate(UserBase):
    """SQL ile TAM UYUMLU OAuth user creation."""
    # Provider ID'ler (ikisi de optional, biri olacak)
    google_id: Optional[str] = None
    apple_id: Optional[str] = None
    
    # Auth provider (SQL'de DEFAULT 'google')
    auth_provider: str = Field("google", pattern="^(google|apple)$")
    
    # Apple özel
    apple_private_email: Optional[str] = None
    is_apple_provided_email: bool = False
    
    # Locale (SQL'de DEFAULT 'tr_TR')
    locale: str = Field("tr_TR", pattern=r"^[a-z]{2}_[A-Z]{2}$")
    
    # Plan (SQL'de DEFAULT 'free')
    plan: str = Field("free", pattern="^(free|basic|pro|premium)$")
    
    # Role
    role: UserRole = Field(UserRole.USER, description="User role")
    
    # ✅ PYDANTIC V2 VALIDATOR - DOĞRU FORMAT:
    @field_validator('google_id', 'apple_id')
    def validate_provider_id(cls, v: Optional[str], info: ValidationInfo) -> Optional[str]:
        """En az bir provider ID olmalı."""
        data = info.data
        
        # Eğer google_id None ise, apple_id olmalı
        if info.field_name == 'google_id' and v is None:
            if data.get('apple_id') is None:
                raise ValueError('Either google_id or apple_id must be provided')
        
        # Eğer apple_id None ise, google_id olmalı
        elif info.field_name == 'apple_id' and v is None:
            if data.get('google_id') is None:
                raise ValueError('Either google_id or apple_id must be provided')
        
        return v
    
    @field_validator('apple_private_email')
    def validate_apple_email(cls, v: Optional[str], info: ValidationInfo) -> Optional[str]:
        """Apple private email için validation."""
        data = info.data
        
        if data.get('is_apple_provided_email') and not v:
            raise ValueError('apple_private_email required when is_apple_provided_email is True')
        
        return v



class UserUpdate(BaseSchema):
    """Update user profile schema."""
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    avatar_url: Optional[str] = None
    phone_number: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$")    
    # Preferences
    language: Optional[str] = Field(None, pattern=r"^[a-z]{2}(_[A-Z]{2})?$")
    timezone: Optional[str] = Field(None, pattern=r"^[A-Za-z_/]+$")
    currency: Optional[str] = Field(None, pattern=r"^[A-Z]{3}$")
    locale: Optional[str] = Field(None, pattern=r"^[a-z]{2}_[A-Z]{2}$")
    plan: Optional[str] = Field(None, pattern="^(free|basic|pro|premium|banned|suspended)$")
    subscription_end_date: Optional[datetime] = None
    email_notifications: Optional[bool] = None
    push_notifications: Optional[bool] = None
    marketing_emails: Optional[bool] = None
    preferences: Optional[Dict[str, Any]] = None
    business_name: Optional[str] = Field(None, max_length=255)


class UserPasswordUpdate(BaseSchema):
    """Update password schema (for future email/password auth)."""
    current_password: str = Field(..., min_length=6, max_length=100)
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str = Field(..., min_length=8, max_length=100)
    
    # ✅ PYDANTIC V2 FORMATI:
    @field_validator('confirm_password')
    def passwords_match(cls, v: str, info: ValidationInfo) -> str:
        """Check if passwords match."""
        data = info.data
        
        if 'new_password' in data and v != data['new_password']:
            raise ValueError('Passwords do not match')
        
        return v


class UserRoleUpdate(BaseSchema):
    """Update user role schema (admin only)."""
    role: UserRole
    reason: Optional[str] = Field(None, max_length=500)


class UserStatusUpdate(BaseSchema):
    """Update user status schema (admin only)."""
    is_active: bool
    reason: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = Field(None, max_length=1000)


class UserResponse(TimestampSchema):
    """Full user response - SQL UYUMLU."""
    id: str
    email: str
    avatar_url: Optional[str] = None
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    phone_number: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$")
    business_name: Optional[str] = Field(None, max_length=255)  # ✅ EKLE!
    # Authentication
    auth_provider: str
    # Platform info
    role: UserRole
    is_active: bool
    is_verified: bool
    shop_id: Optional[str] = None
    
    cj_connected: bool = False
    cj_email: Optional[str] = None
    cj_connected_at: Optional[datetime] = None
    
    # Plan ve subscription
    plan: str = "free"
    subscription_end_date: Optional[datetime] = None
    
    # Seller info - SQL'de var!
    seller_verified: bool = False
    verified_at: Optional[datetime] = None
    seller_since: Optional[datetime] = None
    shop_count: int = 0
    stripe_customer_id: Optional[str] = None
    stripe_account_id: Optional[str] = None
    
    # Preferences ve metadata - SQL'de JSONB!
    preferences: Dict[str, Any] = Field(default_factory=dict)
    user_metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Timestamps
    last_login_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None
    locale: str = "tr_TR"
    
    # Validasyon
    @property
    def is_apple_user(self) -> bool:
        return self.auth_provider == "apple"
    
    @property 
    def is_google_user(self) -> bool:
        return self.auth_provider == "google"
    
    @property
    def is_seller(self) -> bool:
        return self.role == UserRole.SELLER
    
    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN
    
    @property
    def masked_email(self) -> str:
        if self.is_apple_user:
            if 'privaterelay' in self.email or 'appleid.com' in self.email:
                return "Private Apple Email"
        return self.email

class UserPublic(BaseSchema):
    """Public user profile (visible to everyone)."""
    id: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    
    # Seller info
    is_seller: bool = False
    seller_since: Optional[datetime] = None
    shop_count: int = 0
    
    # Public statistics
    
    # Timestamps
    created_at: datetime
    last_active_at: Optional[datetime] = None
    
    @property
    def display_name(self) -> str:
        """Get display name."""
        return self.full_name or "User"


class UserAdmin(UserResponse):
    """Admin view of user with sensitive information."""
    # Security info
    login_attempts: int = 0
    locked_until: Optional[datetime] = None
    two_factor_enabled: bool = False
    
    # Provider-specific IDs
    google_id: Optional[str] = None
    apple_id: Optional[str] = None
    apple_private_email: Optional[str] = None
    is_apple_provided_email: bool = False
    
    # Metadata
    user_metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Audit info
    created_by_ip: Optional[str] = None
    last_ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    # Computed properties
    @property
    def is_locked(self) -> bool:
        """Check if account is currently locked."""
        if not self.locked_until:
            return False
        return self.locked_until > datetime.now()


class UserStats(BaseSchema):
    """User statistics."""
    total_orders: int = 0
    total_spent: float = 0.0
    average_order_value: float = 0.0
    favorite_categories: List[str] = Field(default_factory=list)
    last_order_date: Optional[datetime] = None
    order_count_30d: int = 0
    spent_30d: float = 0.0


# ==================== ADMIN & SEARCH SCHEMAS ====================

class UserSearchParams(PaginationParams):
    """User search parameters (admin only)."""
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    auth_provider: Optional[AuthProvider] = None
    is_verified: Optional[bool] = None
    is_seller: Optional[bool] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class UserExportRequest(BaseSchema):
    """User data export request."""
    format: str = Field("json", pattern="^(json|csv)$")
    include_sensitive: bool = Field(False, description="Include sensitive data")
    fields: Optional[List[str]] = Field(None, description="Specific fields to export")


class UserDeleteRequest(BaseSchema):
    """User account deletion request."""
    password: Optional[str] = Field(None, description="Current password for verification (if email auth)")
    reason: Optional[str] = Field(None, max_length=500, description="Reason for deletion")
    feedback: Optional[str] = Field(None, max_length=1000, description="User feedback")


class UserBulkAction(BaseSchema):
    """Bulk user action (admin only)."""
    user_ids: List[str] = Field(..., min_items=1, max_items=100)
    action: str = Field(..., pattern="^(activate|deactivate|verify|delete|make_seller)$")
    reason: Optional[str] = Field(None, max_length=500)
    

# ==================== CJ DROPSHIPPING SCHEMAS ====================

class CJConnectRequest(BaseModel):
    """CJ hesabı bağlama isteği"""
    cj_email: str = Field(..., description="CJ hesabı email adresi")
    cj_password: str = Field(..., description="CJ hesabı şifresi", min_length=1)
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "cj_email": "seller@example.com",
                "cj_password": "********"
            }
        }
    )


class CJConnectResponse(BaseModel):
    """CJ hesabı bağlama cevabı"""
    success: bool
    message: str
    connected_at: Optional[datetime] = None
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "CJ hesabı başarıyla bağlandı",
                "connected_at": "2026-03-15T12:00:00"
            }
        }
    )


class CJStatusResponse(BaseModel):
    """CJ bağlantı durumu"""
    connected: bool
    email: Optional[str] = None
    connected_at: Optional[datetime] = None
    last_sync: Optional[datetime] = None


class CJDisconnectResponse(BaseModel):
    """CJ bağlantı kesme cevabı"""
    success: bool
    message: str


# ==================== MINIMAL RESPONSE SCHEMAS ====================

class UserMinimal(BaseSchema):
    """Minimal user info for dropdowns/lists."""
    id: str
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: UserRole
    is_seller: bool = False
    
    @property
    def display_name(self) -> str:
        return self.full_name or self.email.split('@')[0]


class UserAuthInfo(BaseSchema):
    """User info for authentication contexts."""
    id: str
    email: str
    auth_provider: AuthProvider
    role: UserRole
    is_verified: bool
    permissions: List[str] = Field(default_factory=list)


# schemas/user.py'ye bu modelleri ekle:

class UserProfileResponse(BaseSchema):
    """Public user profile response (for /users/{id}/public endpoint)."""
    id: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    is_seller: bool = False
    seller_since: Optional[datetime] = None
    shop_count: int = 0
    total_public_reviews: int = 0
    average_rating: float = 0.0
    created_at: datetime
    last_active_at: Optional[datetime] = None
    
    @property
    def display_name(self) -> str:
        return self.full_name or "User"


# CRUD'da kullanılan model mapping'i güncelle:
class UserSearchParams(PaginationParams):
    """User search parameters (admin only)."""
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    auth_provider: Optional[AuthProvider] = None
    is_verified: Optional[bool] = None
    is_seller: Optional[bool] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None



