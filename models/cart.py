from datetime import datetime, timedelta  # <--- BU EKLE!
from typing import Optional, List
from decimal import Decimal
from sqlalchemy import (
    String, Boolean, DateTime, Enum, Text, JSON, 
    Numeric, Integer, ForeignKey, UUID
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from models.base import Base
from sqlalchemy.dialects.postgresql import ENUM  # PostgreSQL enum için
import enum
import uuid

class CartStatus(enum.Enum):
    """Cart status."""
    ACTIVE = "active"
    ABANDONED = "abandoned"
    CONVERTED = "converted"
    EXPIRED = "expired"

    def __str__(self):
        return self.value

class Cart(Base):
    """Cart model - maps to 'carts' table."""
    __tablename__ = "carts"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    # ===== CART OWNER =====
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
    UUID(as_uuid=True),
    ForeignKey("users.id", ondelete="CASCADE")
    )
    session_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    
    # ===== CART IDENTITY =====
    status: Mapped[CartStatus] = mapped_column(
    ENUM(CartStatus, name='cart_status', create_type=False),
    default=CartStatus.ACTIVE,
    nullable=False,
    index=True
    )

    cart_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        nullable=False,
        index=True
    )
    
    # ===== PRICING =====
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.00)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.00)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.00)
    shipping_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.00)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.00)
    
    currency: Mapped[str] = mapped_column(String(3), default='USD')
    
    # ===== DISCOUNTS =====
    coupon_code: Mapped[Optional[str]] = mapped_column(String(50))
    coupon_type: Mapped[Optional[str]] = mapped_column(String(20))
    coupon_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    
    # ===== SHIPPING =====
    shipping_method: Mapped[Optional[str]] = mapped_column(String(50))
    shipping_address: Mapped[dict] = mapped_column(JSON, default=lambda: {})
    requires_shipping: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # ===== ABANDONED CART TRACKING =====
    abandoned_email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    abandoned_email_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    recovery_token: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))  # ✅ Bu doğru
    
    # ===== METADATA =====
    meta_data: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {
            "device": None,
            "browser": None,
            "ip_address": None,
            "utm_source": None,
            "utm_medium": None,
            "utm_campaign": None,
            "referrer": None,
            "landing_page": None
        }
    )
    
    # ===== TIMESTAMPS =====
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now() + timedelta(days=30)
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now()
    )
    converted_to_order_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # ===== RELATIONSHIPS =====
    items: Mapped[List["CartItem"]] = relationship(
        "CartItem",
        back_populates="cart",
        cascade="all, delete-orphan",
        lazy="selectin"  # Eager load cart items
    )
    
    # ===== HELPER PROPERTIES =====
    @property
    def is_guest_cart(self) -> bool:
        """Check if cart belongs to guest."""
        return self.user_id is None and self.session_id is not None
    
    @property
    def is_user_cart(self) -> bool:
        """Check if cart belongs to logged-in user."""
        return self.user_id is not None
    
    @property
    def item_count(self) -> int:
        """Total number of items in cart."""
        return len(self.items) if self.items else 0
    
    @property
    def is_expired(self) -> bool:
        """Check if cart is expired."""
        return datetime.now(self.expires_at.tzinfo) > self.expires_at
    
    @property
    def is_abandoned(self) -> bool:
        """Check if cart is abandoned."""
        if self.status == CartStatus.ABANDONED.value:
            return True
        
        # Mark as abandoned if inactive for 24 hours (guest) or 7 days (user)
        threshold = timedelta(hours=24) if self.is_guest_cart else timedelta(days=7)
        return (
            self.status == CartStatus.ACTIVE.value and
            datetime.now(self.last_activity_at.tzinfo) - self.last_activity_at > threshold
        )
    
    @property
    def has_digital_items(self) -> bool:
        """Check if cart contains digital items."""
        if not self.items:
            return False
        return any(item.is_digital for item in self.items)
    
    @property
    def has_physical_items(self) -> bool:
        """Check if cart contains physical items."""
        if not self.items:
            return False
        return any(item.product_type == "physical" for item in self.items)
    
    @property
    def shop_ids(self) -> List[str]:
        """Get unique shop IDs from cart items."""
        if not self.items:
            return []
        return list(set(item.shop_id for item in self.items))
    
    def calculate_totals(self) -> dict:
        """Recalculate cart totals."""
        subtotal = sum(item.line_total for item in self.items)
        
        # Apply discount
        discount = Decimal('0.00')
        if self.coupon_code:
            if self.coupon_type == "percentage":
                discount = subtotal * (self.coupon_value / Decimal('100'))
            elif self.coupon_type == "fixed":
                discount = self.coupon_value
        
        total = subtotal - discount + self.tax_total + self.shipping_total
        
        return {
            "subtotal": subtotal,
            "discount_total": discount,
            "tax_total": self.tax_total,
            "shipping_total": self.shipping_total,
            "total": total
        }
    
    def to_dict(self) -> dict:
        """Full cart representation."""
        totals = self.calculate_totals()
        
        return {
            "id": self.id,
            "cart_token": self.cart_token,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "status": self.status,
            "is_guest_cart": self.is_guest_cart,
            "is_user_cart": self.is_user_cart,
            "item_count": self.item_count,
            "items": [item.to_dict() for item in self.items] if self.items else [],
            **totals,
            "currency": self.currency,
            "coupon_code": self.coupon_code,
            "coupon_type": self.coupon_type,
            "coupon_value": float(self.coupon_value) if self.coupon_value else None,
            "requires_shipping": self.requires_shipping,
            "shipping_method": self.shipping_method,
            "has_digital_items": self.has_digital_items,
            "has_physical_items": self.has_physical_items,
            "shop_ids": self.shop_ids,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_expired": self.is_expired,
            "is_abandoned": self.is_abandoned,
            "abandoned_email_sent": self.abandoned_email_sent,
            "recovery_token": self.recovery_token
        }


class CartItem(Base):
    """Cart item model - maps to 'cart_items' table."""
    __tablename__ = "cart_items"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    # ===== RELATIONSHIPS =====
    cart_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("carts.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    shop_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    variant_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    
    # ===== PRODUCT DETAILS (Snapshot) =====
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_slug: Mapped[str] = mapped_column(String(220), nullable=False)
    product_image_url: Mapped[Optional[str]] = mapped_column(Text)
    product_type: Mapped[str] = mapped_column(String(20), nullable=False)  # digital, physical
    
    # ===== VARIANT DETAILS =====
    variant_name: Mapped[Optional[str]] = mapped_column(String(100))
    variant_options: Mapped[dict] = mapped_column(JSON, default=lambda: {})
    
    # ===== PRICING (Snapshot) =====
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    compare_at_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default='USD')
    
    # ===== QUANTITY =====
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    max_quantity: Mapped[Optional[int]] = mapped_column(Integer)
    
    # ===== DIGITAL PRODUCT =====
    is_digital: Mapped[bool] = mapped_column(Boolean, default=False)
    download_available: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # ===== INVENTORY =====
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    stock_quantity: Mapped[Optional[int]] = mapped_column(Integer)
    
    # ===== RELATIONSHIPS =====
    cart: Mapped["Cart"] = relationship("Cart", back_populates="items")
    
    # ===== HELPER PROPERTIES =====
    @property
    def line_total(self) -> Decimal:
        """Calculate line total (unit_price * quantity)."""
        return self.unit_price * Decimal(str(self.quantity))
    
    @property
    def is_available(self) -> bool:
        """Check if item is still available for purchase."""
        if not self.in_stock:
            return False
        
        # For physical products, check stock
        if self.product_type == "physical" and self.stock_quantity is not None:
            return self.quantity <= self.stock_quantity
        
        return True
    
    @property
    def has_variant(self) -> bool:
        """Check if item has variant."""
        return bool(self.variant_id or self.variant_name)
    
    def to_dict(self) -> dict:
        """Cart item representation."""
        return {
            "id": self.id,
            "cart_id": self.cart_id,
            "product_id": self.product_id,
            "shop_id": self.shop_id,
            "product_name": self.product_name,
            "product_slug": self.product_slug,
            "product_image_url": self.product_image_url,
            "product_type": self.product_type,
            "variant_id": self.variant_id,
            "variant_name": self.variant_name,
            "variant_options": self.variant_options,
            "unit_price": float(self.unit_price) if self.unit_price else 0.0,
            "compare_at_price": float(self.compare_at_price) if self.compare_at_price else None,
            "currency": self.currency,
            "quantity": self.quantity,
            "line_total": float(self.line_total) if self.line_total else 0.0,
            "is_digital": self.is_digital,
            "download_available": self.download_available,
            "in_stock": self.in_stock,
            "stock_quantity": self.stock_quantity,
            "is_available": self.is_available,
            "has_variant": self.has_variant,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }