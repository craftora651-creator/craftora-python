from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator, HttpUrl
from decimal import Decimal
from enum import Enum 
from routers.base import BaseSchema, TimestampSchema, PaginationParams
from uuid import UUID
import uuid
# ==================== ENUMS ====================

class SubscriptionStatus(str, Enum):
    """Shop subscription status."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BANNED = "banned"
    PENDING = "pending"

class ShopVisibility(str, Enum):
    """Shop visibility."""
    PUBLIC = "public"
    PRIVATE = "private"
    UNLISTED = "unlisted"

class ShopVerificationStatus(str, Enum):
    """Shop verification status."""
    UNVERIFIED = "unverified"
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    
# ==================== SHOP SCHEMAS ====================

class ShopBase(BaseSchema):
    """Base shop schema."""
    shop_name: str = Field(..., min_length=2, max_length=100, description="Shop name")
    description: Optional[str] = Field(None, max_length=2000, description="Shop description")
    short_description: Optional[str] = Field(None, max_length=255, description="Short description")
    slogan: Optional[str] = Field(None, max_length=200, description="Shop slogan")
    primary_category: str = Field(..., min_length=2, max_length=50, description="Main category")
    secondary_categories: Optional[List[str]] = Field(None, description="Additional categories")
    tags: Optional[List[str]] = Field(None, description="Search tags")
    contact_email: Optional[str] = Field(None, description="Contact email")
    support_email: Optional[str] = Field(None, description="Support email")
    phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$")
    website_url: Optional[HttpUrl] = Field(None, description="Website URL")
    tax_number: Optional[str] = Field(None, max_length=100, description="Tax/VAT number")
    tax_office: Optional[str] = Field(None, max_length=100, description="Tax office")


class ShopCreate(ShopBase):
    """Create shop schema."""
    slug: Optional[str] = None
    address: Optional[Dict[str, Any]] = Field(None, description="Shop address information")
    social_links: Optional[Dict[str, Any]] = Field(None, description="Social media links")
    @validator('shop_name')
    def validate_shop_name(cls, v):
        """Validate shop name."""
        # Check for profanity, reserved names etc.
        reserved_names = ['admin', 'craftora', 'support', 'help']
        if v.lower() in reserved_names:
            raise ValueError(f"Shop name '{v}' is reserved")
        return v
    @validator('slug', pre=True, always=True)
    def generate_slug(cls, v, values):
        """Generate slug from shop name if not provided."""
        if v is not None:
            return v
        if 'shop_name' in values:
            # Convert to slug: "My Shop Name" -> "my-shop-name"
            slug = values['shop_name'].lower()
            slug = ''.join(c if c.isalnum() or c == ' ' else ' ' for c in slug)
            slug = '-'.join(slug.split())
            return slug
        raise ValueError('Shop name is required to generate slug')

class ShopUpdate(BaseSchema):
    """Update shop schema."""
    description: Optional[str] = Field(None, max_length=2000)
    short_description: Optional[str] = Field(None, max_length=255)
    slogan: Optional[str] = Field(None, max_length=200)
    logo_url: Optional[HttpUrl] = None
    banner_url: Optional[HttpUrl] = None
    favicon_url: Optional[HttpUrl] = None
    theme_color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    accent_color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    contact_email: Optional[str] = None
    support_email: Optional[str] = None
    phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$")
    website_url: Optional[HttpUrl] = None
    tax_number: Optional[str] = Field(None, max_length=100)
    tax_office: Optional[str] = Field(None, max_length=100)
    meta_title: Optional[str] = Field(None, max_length=70)
    meta_description: Optional[str] = Field(None, max_length=160)
    meta_keywords: Optional[str] = Field(None, max_length=200)
    settings: Optional[Dict[str, Any]] = None

class ShopResponse(TimestampSchema):
    """Full shop response."""
    id: UUID
    user_id: UUID
    shop_name: str
    slug: str
    description: Optional[str] = None
    short_description: Optional[str] = None
    slogan: Optional[str] = None
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None
    favicon_url: Optional[str] = None
    theme_color: str = "#3B82F6"
    accent_color: str = "#10B981"
    subscription_status: SubscriptionStatus
    monthly_fee: Decimal = Field(10.00, ge=0)
    last_payment_date: Optional[datetime] = None
    next_payment_due_date: Optional[datetime] = None
    grace_period_end_date: Optional[datetime] = None
    visibility: ShopVisibility = ShopVisibility.PUBLIC
    is_verified: bool = False
    is_featured: bool = False
    verification_status: ShopVerificationStatus = ShopVerificationStatus.UNVERIFIED
    verification_requested_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    is_paused: bool = False
    paused_at: Optional[datetime] = None
    paused_until: Optional[datetime] = None
    pause_reason: Optional[str] = None
    auto_resume_date: Optional[datetime] = None
    contact_email: Optional[str] = None
    support_email: Optional[str] = None
    phone: Optional[str] = None
    website_url: Optional[str] = None
    tax_number: Optional[str] = None
    tax_office: Optional[str] = None
    address: Optional[Dict[str, Any]] = None
    social_links: Dict[str, Any] = Field(default_factory=dict)
    total_views: int = 0
    total_visitors: int = 0
    total_sales: int = 0
    total_revenue: Decimal = Field(0.00, ge=0)
    total_products: int = 0
    total_orders: int = 0
    average_rating: Decimal = Field(0.00, ge=0, le=5)
    review_count: int = 0
    primary_category: Optional[str] = None
    secondary_categories: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    seo_friendly_url: Optional[str] = None
    settings: Dict[str, Any] = Field(default_factory=dict)
    analytics_data: Dict[str, Any] = Field(default_factory=dict)
    published_at: Optional[datetime] = None
    last_sale_at: Optional[datetime] = None
    last_restock_at: Optional[datetime] = None
    
    # Helper properties
    @property
    def is_active(self) -> bool:
        """Check if shop is active."""
        return (
            self.subscription_status == SubscriptionStatus.ACTIVE and
            not self.is_paused and
            self.visibility == ShopVisibility.PUBLIC
        )
    
    @property
    def days_until_payment(self) -> Optional[int]:
        """Days until next payment."""
        if not self.next_payment_due_date:
            return None
        return (self.next_payment_due_date - datetime.now()).days
    
    @property
    def needs_payment(self) -> bool:
        """Check if shop needs payment."""
        if not self.next_payment_due_date:
            return False
        return self.next_payment_due_date < datetime.now()
    class Config:
        from_attributes = True
        json_encoders = {
            uuid.UUID: str
        }


class ShopPublic(BaseSchema):
    """Public shop view (for marketplace)."""
    id: str
    shop_name: str
    slug: str
    description: Optional[str] = None
    short_description: Optional[str] = None
    slogan: Optional[str] = None
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None
    theme_color: str
    accent_color: str
    is_verified: bool
    is_featured: bool
    contact_email: Optional[str] = None
    website_url: Optional[str] = None
    social_links: Dict[str, Any]
    total_sales: int
    total_products: int
    average_rating: float
    review_count: int
    primary_category: Optional[str]
    secondary_categories: Optional[List[str]]
    tags: Optional[List[str]]
    created_at: datetime
    published_at: Optional[datetime] = None
    is_active: bool


class ShopSeller(ShopResponse):
    """Seller view of shop (includes financial info)."""
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    stripe_account_id: Optional[str] = None
    
    # Financial stats
    pending_balance: Decimal = Field(0.00, ge=0)
    available_balance: Decimal = Field(0.00, ge=0)
    total_payouts: Decimal = Field(0.00, ge=0)
    last_payout_at: Optional[datetime] = None
    last_payout_amount: Optional[Decimal] = None
    
    # Payout settings
    payout_method: Optional[str] = None
    payout_threshold: Decimal = Field(50.00, ge=10)
    auto_payout: bool = True
    payout_frequency: str = "weekly"  # daily, weekly, monthly, manual
    
    # Verification data
    verification_data: Optional[Dict[str, Any]] = None
    verification_failure_reason: Optional[str] = None


class ShopAdmin(ShopSeller):
    """Admin view of shop."""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_platform_shop: bool = False
    fraud_score: int = Field(0, ge=0, le=100)
    manual_review_required: bool = False
    review_notes: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None


class ShopStats(BaseSchema):
    """Shop statistics."""
    daily_views: Dict[str, int] = Field(default_factory=dict)
    daily_sales: Dict[str, int] = Field(default_factory=dict)
    daily_revenue: Dict[str, Decimal] = Field(default_factory=dict)
    top_products: List[Dict[str, Any]] = Field(default_factory=list)
    conversion_rate: float = 0.0
    average_order_value: Decimal = Field(0.00, ge=0)
    customer_count: int = 0
    repeat_customer_rate: float = 0.0


class ShopSearchParams(PaginationParams):
    """Shop search parameters."""
    search: Optional[str] = None
    category: Optional[str] = None
    min_rating: Optional[float] = Field(None, ge=0, le=5)
    min_sales: Optional[int] = Field(None, ge=0)
    is_verified: Optional[bool] = None
    is_featured: Optional[bool] = None
    subscription_status: Optional[SubscriptionStatus] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class ShopVerificationRequest(BaseSchema):
    """Shop verification request."""
    documents: List[Dict[str, Any]] = Field(..., min_items=1, description="Verification documents")
    additional_info: Optional[str] = Field(None, max_length=1000)


class ShopPauseRequest(BaseSchema):
    """Pause shop request."""
    pause_days: int = Field(30, ge=1, le=365, description="Days to pause")
    reason: str = Field(..., min_length=10, max_length=500, description="Pause reason")
    auto_resume: bool = Field(True, description="Auto resume after pause period")


class ShopSubscriptionUpdate(BaseSchema):
    """Update shop subscription (admin only)."""
    subscription_status: SubscriptionStatus
    monthly_fee: Optional[Decimal] = Field(None, ge=0)
    next_payment_due_date: Optional[datetime] = None
    grace_period_end_date: Optional[datetime] = None
    reason: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = Field(None, max_length=1000)

class ShopDetailResponse(ShopResponse):
    """Shop detail response with additional fields."""
    owner_name: Optional[str] = None
    owner_email: Optional[str] = None
    total_followers: int = 0
    is_following: bool = False
    rating_distribution: Dict[str, int] = Field(default_factory=dict)
    product_categories: List[str] = Field(default_factory=list)
    top_products: List[Dict[str, Any]] = Field(default_factory=list)
    shipping_policies: Optional[Dict[str, Any]] = None
    return_policy: Optional[Dict[str, Any]] = None
    support_policy: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True
        json_encoders = {  # Burada da olmalı!
            uuid.UUID: str
        }



class ShopAdminResponse(ShopResponse):
    """Admin view of shop."""
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    stripe_account_id: Optional[str] = None
    pending_balance: Decimal = Field(0.00, ge=0)
    available_balance: Decimal = Field(0.00, ge=0)
    total_payouts: Decimal = Field(0.00, ge=0)
    last_payout_at: Optional[datetime] = None
    last_payout_amount: Optional[Decimal] = None
    payout_method: Optional[str] = None
    payout_threshold: Decimal = Field(50.00, ge=10)
    auto_payout: bool = True
    payout_frequency: str = "weekly"
    verification_data: Optional[Dict[str, Any]] = None
    verification_failure_reason: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_platform_shop: bool = False
    fraud_score: int = Field(0, ge=0, le=100)
    manual_review_required: bool = False
    review_notes: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
        json_encoders = {  # Burada da!
            uuid.UUID: str
        }