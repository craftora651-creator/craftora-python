from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from enum import Enum

# ==================== BASE ====================
class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

# ==================== ENUMS ====================
class AuthProvider(str, Enum):
    GOOGLE = "google"
    APPLE = "apple"
    EMAIL = "email"

# ==================== TOKEN SCHEMAS ====================
class TokenResponse(BaseSchema):
    """SADECE token bilgileri - güvenli versiyon"""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: Optional[str] = Field(None, description="Refresh token (opsiyonel)")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(3600, description="Token expiry in seconds")

class AuthResponse(BaseSchema):
    """Auth sonrası TAM response - user schemas ile UYUMLU"""
    tokens: TokenResponse
    user: Dict[str, Any] = Field(..., description="User information")
    is_new_user: bool = Field(False, description="Whether this is a new user")

# ==================== AUTH REQUEST SCHEMAS ====================
class RefreshTokenRequest(BaseSchema):
    refresh_token: str

class GoogleAuthRequest(BaseSchema):
    """User schemas ile UYUMLU - id_token kullan"""
    id_token: str = Field(..., description="Google JWT ID token")  # ✅ user.py ile aynı
    access_token: Optional[str] = Field(None, description="Google OAuth access token")  # ✅ user.py ile aynı

class AppleAuthRequest(BaseSchema):
    """User schemas ile UYUMLU"""
    identity_token: str = Field(..., description="Apple JWT identity token")
    authorization_code: str = Field(..., description="Apple authorization code")
    user: Optional[Dict[str, Any]] = Field(None, description="Apple user info")
    email: Optional[str] = Field(None, description="User email (if available)")  # ✅ EKLENDİ

# ==================== EMAIL/PASSWORD AUTH ====================
class LoginRequest(BaseSchema):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)

class RegisterRequest(BaseSchema):
    """SQL model ile UYUMLU olmalı"""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    locale: str = Field("tr_TR", pattern=r"^[a-z]{2}_[A-Z]{2}$")  # ✅ SQL DEFAULT ile uyumlu
    auth_provider: str = Field("email", pattern="^(google|apple|email)$")  # ✅ EKLENDİ
    accept_terms: bool = Field(..., description="Must accept terms")

# ==================== PASSWORD RESET ====================
class ForgotPasswordRequest(BaseSchema):
    email: EmailStr

class ResetPasswordRequest(BaseSchema):
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)

class VerifyEmailRequest(BaseSchema):
    token: str

# ==================== SESSION & LOGOUT ====================
class LogoutRequest(BaseSchema):
    refresh_token: Optional[str] = None
    logout_all_sessions: bool = False

class SessionInfo(BaseSchema):
    session_id: str
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    is_current: bool = False

# ==================== RESPONSE SCHEMAS ====================
class AuthUserResponse(BaseSchema):
    """User schemas'daki UserResponse ile UYUMLU olmalı"""
    # ===== PRIMARY =====
    id: str
    email: str
    
    # ===== PROFILE =====
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    phone_number: Optional[str] = None
    business_name: Optional[str] = None
    
    # ===== AUTHENTICATION =====
    auth_provider: str
    role: str
    is_active: bool
    is_verified: bool
    
    # ===== PLATFORM =====
    locale: str = "tr_TR"
    plan: str = "free"
    seller_verified: bool = False
    shop_count: int = 0
    
    # ===== METADATA =====
    preferences: Dict[str, Any] = Field(default_factory=dict)
    user_metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # ===== TIMESTAMPS =====
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None
    
    # ===== COMPUTED PROPERTIES =====
    @property
    def is_seller(self) -> bool:
        return self.role == "seller"
    
    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
