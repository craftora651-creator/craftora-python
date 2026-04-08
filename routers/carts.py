from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator, HttpUrl
from decimal import Decimal
from enum import Enum
from uuid import UUID
from routers.base import BaseSchema, TimestampSchema


# ==================== ENUMS ====================


class CartStatus(str, Enum):
    """Cart status."""
    ACTIVE = "active"
    ABANDONED = "abandoned"
    CONVERTED = "converted"
    EXPIRED = "expired"


# ==================== CART SCHEMAS ====================


class CartBase(BaseSchema):
    """Base cart schema."""
    currency: str = Field("USD", pattern="^[A-Z]{3}$", description="Cart currency")
    coupon_code: Optional[str] = Field(None, max_length=50, description="Coupon code")
    shipping_method: Optional[str] = Field(None, max_length=50, description="Shipping method")
    shipping_address: Optional[Dict[str, Any]] = Field(None, description="Shipping address")


class CartCreate(CartBase):
    """Create cart schema (usually auto-created)."""
    session_id: Optional[str] = Field(None, max_length=255, description="Guest session ID")
    user_id: Optional[UUID] = Field(None, description="User ID for logged-in users")


class CartUpdate(CartBase):
    """Update cart schema."""
    coupon_code: Optional[str] = Field(None, max_length=50)
    shipping_method: Optional[str] = Field(None, max_length=50)
    shipping_address: Optional[Dict[str, Any]] = None


class CartResponse(TimestampSchema):
    """Full cart response."""
    id: UUID
    cart_token: str
    user_id: Optional[UUID] = None
    session_id: Optional[str] = None
    status: CartStatus = CartStatus.ACTIVE
    
    # Pricing
    subtotal: Decimal = Field(0.00, ge=0)
    discount_total: Decimal = Field(0.00, ge=0)
    tax_total: Decimal = Field(0.00, ge=0)
    shipping_total: Decimal = Field(0.00, ge=0)
    total: Decimal = Field(0.00, ge=0)
    currency: str = "USD"
    
    # Discounts
    coupon_code: Optional[str] = None
    coupon_type: Optional[str] = None
    coupon_value: Optional[Decimal] = None
    
    # Shipping
    shipping_method: Optional[str] = None
    shipping_address: Optional[Dict[str, Any]] = None
    requires_shipping: bool = False
    last_activity_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    # Items
    items: List["CartItemResponse"] = Field(default_factory=list)
    item_count: int = 0
    
    # Shop info
    shop_ids: List[str] = Field(default_factory=list)
    shop_count: int = 0
    
    # Product type info
    has_digital_items: bool = False
    has_physical_items: bool = False
    
    # Abandoned cart tracking
    abandoned_email_sent: bool = False
    abandoned_email_sent_at: Optional[datetime] = None
    recovery_token: Optional[str] = None
    
    # Timestamps
    last_activity_at: datetime
    expires_at: datetime
    converted_to_order_at: Optional[datetime] = None
    
    # Helper properties
    @property
    def is_guest_cart(self) -> bool:
        """Check if cart belongs to guest."""
        return self.user_id is None and self.session_id is not None
    
    @property
    def is_user_cart(self) -> bool:
        """Check if cart belongs to logged-in user."""
        return self.user_id is not None
    
    @property
    def is_expired(self) -> bool:
        """Check if cart is expired."""
        return datetime.now() > self.expires_at
    
    @property
    def is_abandoned(self) -> bool:
        """Check if cart is abandoned."""
        if self.status == CartStatus.ABANDONED:
            return True
        
        # Mark as abandoned if inactive for 24 hours (guest) or 7 days (user)
        threshold_hours = 24 if self.is_guest_cart else 168  # 7 days
        return (
            self.status == CartStatus.ACTIVE and
            (datetime.now() - self.last_activity_at).total_seconds() > threshold_hours * 3600
        )
    
    @property
    def discount_percentage(self) -> Optional[float]:
        """Calculate discount percentage."""
        if self.subtotal > 0 and self.discount_total > 0:
            return float((self.discount_total / self.subtotal) * 100)
        return None


class CartItemBase(BaseSchema):
    """Base cart item schema."""
    product_id: UUID = Field(..., description="Product ID")
    variant_id: Optional[UUID] = Field(None, description="Variant ID")
    quantity: int = Field(1, ge=1, le=100, description="Quantity")
    variant_options: Optional[Dict[str, Any]] = Field(None, description="Variant options")


class CartItemCreate(CartItemBase):
    """Create cart item schema."""
    pass


class CartItemUpdate(BaseSchema):
    """Update cart item schema."""
    quantity: int = Field(..., ge=1, le=100, description="New quantity")


class CartItemResponse(TimestampSchema):
    """Cart item response."""
    id: UUID
    cart_id: UUID
    product_id: UUID
    shop_id: UUID
    variant_id: Optional[UUID] = None
    
    # Product details (snapshot)
    product_name: str
    product_slug: str
    product_image_url: Optional[str] = None
    product_type: str  # digital, physical
    
    # Variant details
    variant_name: Optional[str] = None
    variant_options: Dict[str, Any] = Field(default_factory=dict)
    
    # Pricing (snapshot)
    unit_price: Decimal
    compare_at_price: Optional[Decimal] = None
    currency: str = "USD"
    
    # Quantity
    quantity: int = 1
    max_quantity: Optional[int] = None
    
    # Digital product info
    is_digital: bool = False
    download_available: bool = False
    
    # Inventory info
    in_stock: bool = True
    stock_quantity: Optional[int] = None
    
    # Calculated fields
    line_total: Decimal
    
    # Helper properties
    @property
    def has_variant(self) -> bool:
        """Check if item has variant."""
        return bool(self.variant_id or self.variant_name)
    
    @property
    def is_available(self) -> bool:
        """Check if item is still available."""
        if not self.in_stock:
            return False
        
        # For physical products, check stock
        if self.product_type == "physical" and self.stock_quantity is not None:
            return self.quantity <= self.stock_quantity
        
        return True
    
    @property
    def discount_amount(self) -> Optional[Decimal]:
        """Calculate discount amount if compare price exists."""
        if self.compare_at_price and self.compare_at_price > self.unit_price:
            return self.compare_at_price - self.unit_price
        return None
    
    @property
    def discount_percentage(self) -> Optional[float]:
        """Calculate discount percentage."""
        if self.discount_amount and self.compare_at_price:
            return float((self.discount_amount / self.compare_at_price) * 100)
        return None


class CartMergeRequest(BaseSchema):
    """Cart merge request (guest to user)."""
    session_cart_token: str = Field(..., description="Guest cart token")
    user_cart_token: Optional[str] = Field(None, description="User cart token (if exists)")


class CartApplyCoupon(BaseSchema):
    """Apply coupon to cart."""
    coupon_code: str = Field(..., max_length=50, description="Coupon code")


class CartShippingUpdate(BaseSchema):
    """Update cart shipping."""
    shipping_method: str = Field(..., max_length=50, description="Shipping method")
    shipping_address: Dict[str, Any] = Field(..., description="Shipping address")
    
    @validator('shipping_address')
    def validate_shipping_address(cls, v):
        """Validate shipping address."""
        required_fields = ['full_name', 'address_line1', 'city', 'country', 'postal_code']
        for field in required_fields:
            if field not in v or not v[field]:
                raise ValueError(f"Shipping address missing required field: {field}")
        return v


class CartEstimateRequest(BaseSchema):
    """Cart estimate request (for calculating totals)."""
    items: List[CartItemCreate] = Field(..., min_items=1, description="Cart items")
    coupon_code: Optional[str] = Field(None, max_length=50, description="Coupon code")
    shipping_method: Optional[str] = Field(None, max_length=50, description="Shipping method")
    shipping_address: Optional[Dict[str, Any]] = Field(None, description="Shipping address")


class CartEstimateResponse(BaseSchema):
    """Cart estimate response."""
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    shipping_total: Decimal
    total: Decimal
    currency: str = "USD"
    discount_percentage: Optional[float] = None
    tax_rate: float = 0.0
    shipping_estimate: Optional[Dict[str, Any]] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)


class CartCheckoutPreview(BaseSchema):
    """Cart checkout preview."""
    cart_id: UUID
    payment_method: str = Field(..., pattern="^(stripe|paypal|bank_transfer)$")
    save_payment_method: bool = Field(False, description="Save payment method for future")
    billing_address: Optional[Dict[str, Any]] = Field(None, description="Billing address")
    shipping_same_as_billing: bool = Field(True, description="Use billing address for shipping")
    
    @validator('billing_address')
    def validate_billing_address(cls, v, values):
        """Validate billing address."""
        if not values.get('shipping_same_as_billing') and not v:
            raise ValueError("Billing address is required when shipping address is different")
        
        if v:
            required_fields = ['full_name', 'address_line1', 'city', 'country', 'postal_code']
            for field in required_fields:
                if field not in v or not v[field]:
                    raise ValueError(f"Billing address missing required field: {field}")
        return v


class CartRecoveryRequest(BaseSchema):
    """Cart recovery request."""
    recovery_token: str = Field(..., description="Cart recovery token")
    email: Optional[str] = Field(None, description="Email for guest cart recovery")


class CartBulkUpdate(BaseSchema):
    """Bulk cart update (admin only)."""
    cart_ids: List[UUID] = Field(..., min_items=1, max_items=100, description="Cart IDs")
    action: str = Field(..., pattern="^(abandon|recover|expire|convert)$", description="Action to perform")
    reason: Optional[str] = Field(None, max_length=500, description="Reason for action")

class CartItemAdd(CartItemCreate):
    """Alias for CartItemCreate for API compatibility."""
    pass