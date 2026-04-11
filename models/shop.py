from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String, Boolean, DateTime, Text, JSON, 
    BigInteger, Numeric, ForeignKey, func
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID, CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SQLEnum
from models.base import Base
import enum
import uuid
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship 

# ===== ENUMS =====
class ShopStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"

class SubscriptionStatus(enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BANNED = "banned"
    PENDING = "pending"

class ShopVisibility(enum.Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    UNLISTED = "unlisted"

class ShopPlan(enum.Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"

# ===== SHOP MODEL =====
class Shop(Base):
    """Shop model - maps to 'shops' table."""
    __tablename__ = "shops"
    
    # ===== PRIMARY KEY =====
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # ===== RELATIONSHIPS =====
    user_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),   # UUID as string
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    products = relationship("Product", back_populates="shop", cascade="all, delete-orphan")

    
    # ===== SHOP IDENTITY =====
    shop_name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    short_description: Mapped[Optional[str]] = mapped_column(String(255))
    slogan: Mapped[Optional[str]] = mapped_column(String(200))
    
    
    # ===== VISUALS =====
    logo_url: Mapped[Optional[str]] = mapped_column(Text)
    banner_url: Mapped[Optional[str]] = mapped_column(Text)
    favicon_url: Mapped[Optional[str]] = mapped_column(Text)
    theme_color: Mapped[Optional[str]] = mapped_column(String(7), default='#3B82F6', nullable=True)
    accent_color: Mapped[Optional[str]] = mapped_column(String(7), default='#10B981', nullable=True)
    custom_css: Mapped[Optional[str]] = mapped_column(Text)
    
    # ===== SUBSCRIPTION & PAYMENT =====
    # PostgreSQL subscription_status enum'u için String kullan
    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        SQLEnum(
            SubscriptionStatus,
            name="subscription_status",
            create_type=False,  # enum zaten DB’de var
            values_callable=lambda x: [e.value for e in x]  # burada küçük harfler
        ),
        default=SubscriptionStatus.PENDING,
        server_default=SubscriptionStatus.PENDING.value,
        nullable=False,
        index=True
    )
    
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255))
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(255))
    last_payment_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_payment_due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    grace_period_end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    monthly_fee: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), default=10.00, nullable=True)
    
    # ===== VISIBILITY & STATUS =====
    # PostgreSQL shop_visibility enum'u için String kullan
    visibility: Mapped[ShopVisibility] = mapped_column(
        SQLEnum(
            ShopVisibility,
            name="shop_visibility",
            create_type=False,
            values_callable=lambda x: [e.value for e in x]
        ),
        default=ShopVisibility.PUBLIC,
        nullable=False,
        index=True,
        server_default=ShopVisibility.PUBLIC.value
    )
    
    is_verified: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    is_featured: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, nullable=True)
    verification_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # ===== CONTACT INFORMATION =====
    # CITEXT (case-insensitive text) için
    contact_email: Mapped[Optional[str]] = mapped_column(CITEXT)
    support_email: Mapped[Optional[str]] = mapped_column(CITEXT)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    website_url: Mapped[Optional[str]] = mapped_column(String(500))
    
    # ===== BUSINESS INFORMATION =====
    tax_number: Mapped[Optional[str]] = mapped_column(String(100))
    tax_office: Mapped[Optional[str]] = mapped_column(String(100))
    address: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    social_links: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # ===== PAUSE FUNCTIONALITY =====
    is_paused: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, nullable=True)
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    paused_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    pause_reason: Mapped[Optional[str]] = mapped_column(Text)
    auto_resume_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # ===== STATISTICS =====
    total_views: Mapped[Optional[int]] = mapped_column(BigInteger, default=0, nullable=True)
    total_visitors: Mapped[Optional[int]] = mapped_column(BigInteger, default=0, nullable=True)
    total_sales: Mapped[Optional[int]] = mapped_column(BigInteger, default=0, nullable=True)
    total_revenue: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), default=0.00, nullable=True)
    total_products: Mapped[Optional[int]] = mapped_column(BigInteger, default=0, nullable=True)
    total_orders: Mapped[Optional[int]] = mapped_column(BigInteger, default=0, nullable=True)
    average_rating: Mapped[Optional[float]] = mapped_column(Numeric(3, 2), default=0.00, nullable=True)
    review_count: Mapped[Optional[int]] = mapped_column(BigInteger, default=0)
    
    # ===== SEO & METADATA =====
    meta_title: Mapped[Optional[str]] = mapped_column(String(70))
    meta_description: Mapped[Optional[str]] = mapped_column(String(160))
    meta_keywords: Mapped[Optional[str]] = mapped_column(String(200))
    seo_friendly_url: Mapped[Optional[str]] = mapped_column(String(500))
    
    # ===== CATEGORY & TAGS =====
    primary_category: Mapped[Optional[str]] = mapped_column(String(50))
    secondary_categories: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String(50)))
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text))
    
    # ===== SETTINGS & ANALYTICS =====
    settings: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=True,
        default=lambda: {
            "notifications": {
                "new_order": True,
                "new_review": True,
                "low_stock": True,
                "payment_reminder": True
            },
            "checkout": {
                "require_shipping_address": False,
                "require_billing_address": False,
                "allow_guest_checkout": True,
                "auto_fulfill_digital": True
            },
            "privacy": {
                "show_sales_count": True,
                "show_revenue": False,
                "show_customer_count": False
            },
            "display": {
                "show_category_sidebar": True,
                "products_per_page": 24,
                "default_sort": "newest",
                "currency": "USD",
                "timezone": "Europe/Istanbul"
            },
            "security": {
                "require_2fa_for_payouts": False,
                "login_notifications": True,
                "api_rate_limit": 100
            }
        }
    )
    
    analytics_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # metadata kolonu (JSON tipinde)
    meta_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        name="metadata"
    )
    
    # ===== TIMESTAMPS =====
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_sale_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_restock_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # ===== COMPUTED PROPERTIES =====
    @property
    def shop_plan(self) -> ShopPlan:
        """Calculate shop plan from monthly fee."""
        if not self.monthly_fee or self.monthly_fee == 0:
            return ShopPlan.FREE
        elif self.monthly_fee <= 10:
            return ShopPlan.BASIC
        elif self.monthly_fee <= 50:
            return ShopPlan.PRO
        else:
            return ShopPlan.ENTERPRISE
    
    @property
    def status(self) -> ShopStatus:
        """Calculate shop status from various fields."""
        if self.is_paused or self.subscription_status == SubscriptionStatus.SUSPENDED.value:
            return ShopStatus.SUSPENDED
        elif (self.subscription_status == SubscriptionStatus.BANNED.value or 
              self.subscription_status == SubscriptionStatus.PENDING.value or
              self.visibility == ShopVisibility.PRIVATE.value):
            return ShopStatus.INACTIVE
        else:
            return ShopStatus.ACTIVE
    
    @property
    def is_active(self) -> bool:
        """Check if shop is active (not suspended/banned/paused)."""
        return (
            self.subscription_status == SubscriptionStatus.ACTIVE.value and
            not self.is_paused and
            self.visibility == ShopVisibility.PUBLIC.value
        )
    
    @property
    def days_until_payment(self) -> Optional[int]:
        """Days until next payment (negative if overdue)."""
        if not self.next_payment_due_date:
            return None
        delta = self.next_payment_due_date - datetime.now(self.next_payment_due_date.tzinfo)
        return delta.days
    
    @property
    def needs_payment(self) -> bool:
        """Check if shop needs to make payment."""
        if not self.next_payment_due_date:
            return False
        return self.next_payment_due_date < datetime.now(self.next_payment_due_date.tzinfo)
    
    # ===== VALIDATION METHODS =====
    def validate_subscription_status(self, value: str) -> bool:
        """Validate subscription_status against database enum."""
        valid_statuses = {"active", "suspended", "banned", "pending"}
        return value.lower() in valid_statuses  # case-insensitive
    
    def validate_visibility(self, value: str) -> bool:
        """Validate visibility against database enum."""
        valid_visibilities = {"public", "private", "unlisted"}
        return value.lower() in valid_visibilities  # case-insensitive
    
    def validate_email(self, email: str, field_name: str) -> bool:
        """Validate email format."""
        if not email:
            return True  # Optional field
        
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        if field_name == 'contact_email':
            # Contact email validation
            return bool(re.match(pattern, email))
        elif field_name == 'support_email':
            # Support email validation
            return bool(re.match(pattern, email))
        return False
    
    # ===== HELPER METHODS =====
    def normalize_emails(self):
        """Normalize emails to lowercase for consistency."""
        if self.contact_email:
            self.contact_email = self.contact_email.lower()
        if self.support_email:
            self.support_email = self.support_email.lower()
    
    def get_contact_info(self) -> Dict[str, Optional[str]]:
        """Get all contact information."""
        return {
            "contact_email": self.contact_email,
            "support_email": self.support_email,
            "phone": self.phone,
            "website_url": self.website_url
        }
    
    def get_business_info(self) -> Dict[str, Optional[str]]:
        """Get all business information."""
        return {
            "tax_number": self.tax_number,
            "tax_office": self.tax_office,
            "address": self.address
        }
    
    # ===== SERIALIZATION METHODS =====
    def to_dict(self) -> dict:
        """Full shop representation."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "shop_name": self.shop_name,
            "slug": self.slug,
            "description": self.description,
            "short_description": self.short_description,
            "slogan": self.slogan,
            "logo_url": self.logo_url,
            "banner_url": self.banner_url,
            "favicon_url": self.favicon_url,
            "theme_color": self.theme_color,
            "accent_color": self.accent_color,
            "custom_css": self.custom_css,
            "subscription_status": self.subscription_status,
            "stripe_customer_id": self.stripe_customer_id,
            "stripe_subscription_id": self.stripe_subscription_id,
            "last_payment_date": self.last_payment_date.isoformat() if self.last_payment_date else None,
            "next_payment_due_date": self.next_payment_due_date.isoformat() if self.next_payment_due_date else None,
            "grace_period_end_date": self.grace_period_end_date.isoformat() if self.grace_period_end_date else None,
            "monthly_fee": float(self.monthly_fee) if self.monthly_fee else 0.0,
            "visibility": self.visibility,
            "is_verified": self.is_verified,
            "is_featured": self.is_featured,
            "verification_requested_at": self.verification_requested_at.isoformat() if self.verification_requested_at else None,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "contact_email": self.contact_email,
            "support_email": self.support_email,
            "phone": self.phone,
            "website_url": self.website_url,
            "tax_number": self.tax_number,
            "tax_office": self.tax_office,
            "address": self.address,
            "social_links": self.social_links,
            "is_paused": self.is_paused,
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "paused_until": self.paused_until.isoformat() if self.paused_until else None,
            "pause_reason": self.pause_reason,
            "auto_resume_date": self.auto_resume_date.isoformat() if self.auto_resume_date else None,
            "total_views": self.total_views,
            "total_visitors": self.total_visitors,
            "total_sales": self.total_sales,
            "total_revenue": float(self.total_revenue) if self.total_revenue else 0.0,
            "total_products": self.total_products,
            "total_orders": self.total_orders,
            "average_rating": float(self.average_rating) if self.average_rating else 0.0,
            "review_count": self.review_count,
            "meta_title": self.meta_title,
            "meta_description": self.meta_description,
            "meta_keywords": self.meta_keywords,
            "seo_friendly_url": self.seo_friendly_url,
            "primary_category": self.primary_category,
            "secondary_categories": self.secondary_categories,
            "tags": self.tags,
            "settings": self.settings,
            "analytics_data": self.analytics_data,
            "metadata": self.meta_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "last_sale_at": self.last_sale_at.isoformat() if self.last_sale_at else None,
            "last_restock_at": self.last_restock_at.isoformat() if self.last_restock_at else None,
            # Computed fields
            "shop_plan": self.shop_plan.value,
            "shop_status": self.status.value,
            "is_active": self.is_active,
            "days_until_payment": self.days_until_payment,
            "needs_payment": self.needs_payment
        }
    
    def to_public_dict(self) -> dict:
        """Public representation for marketplace."""
        return {
            "id": self.id,
            "shop_name": self.shop_name,
            "slug": self.slug,
            "description": self.description,
            "short_description": self.short_description,
            "logo_url": self.logo_url,
            "banner_url": self.banner_url,
            "theme_color": self.theme_color,
            "accent_color": self.accent_color,
            "is_verified": self.is_verified,
            "is_featured": self.is_featured,
            "contact_email": self.contact_email,
            "website_url": self.website_url,
            "social_links": self.social_links,
            "primary_category": self.primary_category,
            "secondary_categories": self.secondary_categories,
            "tags": self.tags,
            "average_rating": float(self.average_rating) if self.average_rating else 0.0,
            "review_count": self.review_count,
            "total_sales": self.total_sales,
            "total_products": self.total_products,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_active": self.is_active
        }
    
    def to_minimal_dict(self) -> dict:
        """Minimal representation for listings."""
        return {
            "id": self.id,
            "shop_name": self.shop_name,
            "slug": self.slug,
            "logo_url": self.logo_url,
            "is_verified": self.is_verified,
            "primary_category": self.primary_category,
            "average_rating": float(self.average_rating) if self.average_rating else 0.0,
            "total_sales": self.total_sales,
            "is_active": self.is_active
        }
    
    def __repr__(self) -> str:
        return f"<Shop(id='{self.id}', name='{self.shop_name}', status='{self.status.value}')>"