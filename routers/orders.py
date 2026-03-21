from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator, EmailStr
from decimal import Decimal
from enum import Enum

from routers.base import BaseSchema, TimestampSchema, PaginationParams


# ==================== ENUMS ====================

class OrderStatus(str, Enum):
    """Order status."""
    PENDING = "pending"
    PROCESSING = "processing"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    FAILED = "failed"


class OrderType(str, Enum):
    """Order type."""
    DIGITAL = "digital"
    PHYSICAL = "physical"
    MIXED = "mixed"
    SUBSCRIPTION = "subscription"


class PaymentMethod(str, Enum):
    """Payment method."""
    CREDIT_CARD = "credit_card"
    BANK_TRANSFER = "bank_transfer"
    PAYPAL = "paypal"
    STRIPE = "stripe"
    APPLE_PAY = "apple_pay"
    GOOGLE_PAY = "google_pay"
    CASH_ON_DELIVERY = "cash_on_delivery"


class FulfillmentStatus(str, Enum):
    """Fulfillment status."""
    UNFULFILLED = "unfulfilled"
    PARTIALLY_FULFILLED = "partially_fulfilled"
    FULFILLED = "fulfilled"
    DELIVERED = "delivered"
    RETURNED = "returned"


# ==================== ORDER SCHEMAS ====================


class OrderBase(BaseSchema):
    """Base order schema."""
    customer_email: EmailStr = Field(..., description="Customer email")
    customer_name: Optional[str] = Field(None, min_length=2, max_length=100, description="Customer name")
    customer_phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$", description="Customer phone")
    customer_notes: Optional[str] = Field(None, max_length=1000, description="Customer notes")
    
    # Billing address
    billing_address: Dict[str, Any] = Field(..., description="Billing address")
    
    # Shipping
    shipping_same_as_billing: bool = Field(True, description="Shipping same as billing")
    shipping_address: Optional[Dict[str, Any]] = Field(None, description="Shipping address")
    
    # Payment
    payment_method: PaymentMethod = Field(..., description="Payment method")
    
    @validator('shipping_address')
    def validate_shipping_address(cls, v, values):
        """Validate shipping address."""
        if not values.get('shipping_same_as_billing') and not v:
            raise ValueError("Shipping address is required when different from billing")
        return v
    
    @validator('billing_address')
    def validate_billing_address(cls, v):
        """Validate billing address."""
        required_fields = ['full_name', 'address_line1', 'city', 'country', 'postal_code']
        for field in required_fields:
            if field not in v or not v[field]:
                raise ValueError(f"Billing address missing required field: {field}")
        return v


class OrderCreate(OrderBase):
    """Create order schema (from cart)."""
    cart_id: str = Field(..., description="Cart ID to convert to order")
    save_billing_address: bool = Field(False, description="Save billing address to profile")
    save_shipping_address: bool = Field(False, description="Save shipping address to profile")
    accept_terms: bool = Field(True, description="Accept terms and conditions")
    marketing_consent: bool = Field(False, description="Marketing consent")


class OrderUpdate(BaseSchema):
    """Update order schema (seller/admin only)."""
    status: Optional[OrderStatus] = None
    fulfillment_status: Optional[FulfillmentStatus] = None
    shipping_method: Optional[str] = Field(None, max_length=50, description="Shipping method")
    tracking_number: Optional[str] = Field(None, max_length=100, description="Tracking number")
    estimated_delivery_date: Optional[datetime] = Field(None, description="Estimated delivery date")
    fulfillment_notes: Optional[str] = Field(None, max_length=1000, description="Fulfillment notes")
    digital_delivered: Optional[bool] = Field(None, description="Digital products delivered")


class OrderResponse(TimestampSchema):
    """Full order response."""
    id: str
    order_number: str
    shop_id: str
    buyer_id: Optional[str] = None
    cart_id: Optional[str] = None
    
    # Status
    status: OrderStatus = OrderStatus.PENDING
    order_type: OrderType
    fulfillment_status: FulfillmentStatus = FulfillmentStatus.UNFULFILLED
    
    # Customer info
    customer_email: str
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_notes: Optional[str] = None
    
    # Addresses
    billing_address: Dict[str, Any]
    shipping_address: Dict[str, Any]
    shipping_same_as_billing: bool = True
    
    # Pricing
    items_subtotal: Decimal = Field(0.00, ge=0)
    discount_total: Decimal = Field(0.00, ge=0)
    tax_total: Decimal = Field(0.00, ge=0)
    shipping_total: Decimal = Field(0.00, ge=0)
    platform_fee: Decimal = Field(0.00, ge=0)
    seller_payout: Decimal = Field(0.00, ge=0)
    order_total: Decimal = Field(0.00, ge=0)
    currency: str = "USD"
    
    # Discount
    coupon_code: Optional[str] = None
    coupon_type: Optional[str] = None
    coupon_value: Optional[Decimal] = None
    
    # Payment
    payment_method: Optional[PaymentMethod] = None
    payment_status: str = "pending"
    stripe_payment_intent_id: Optional[str] = None
    stripe_charge_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    paid_at: Optional[datetime] = None
    payment_due_date: Optional[datetime] = None
    
    # Shipping
    requires_shipping: bool = False
    shipping_method: Optional[str] = None
    shipping_provider: Optional[str] = None
    tracking_number: Optional[str] = None
    estimated_delivery_date: Optional[datetime] = None
    
    # Fulfillment
    fulfillment_notes: Optional[str] = None
    digital_delivered: bool = False
    digital_delivered_at: Optional[datetime] = None
    
    # Refund
    refund_reason: Optional[str] = None
    refund_amount: Decimal = Field(0.00, ge=0)
    refunded_at: Optional[datetime] = None
    
    # Risk & Fraud
    fraud_score: int = Field(0, ge=0, le=100)
    fraud_checked: bool = False
    fraud_checked_at: Optional[datetime] = None
    high_risk: bool = False
    manual_review_required: bool = False
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Email status
    email_confirmation_sent: bool = False
    email_confirmation_sent_at: Optional[datetime] = None
    email_shipping_sent: bool = False
    email_shipping_sent_at: Optional[datetime] = None
    email_delivered_sent: bool = False
    email_delivered_sent_at: Optional[datetime] = None
    
    # Timestamps
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    
    # Items (from cart)
    items: List[Dict[str, Any]] = Field(default_factory=list)
    item_count: int = 0
    
    # Status logs
    status_logs: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Helper properties
    @property
    def is_paid(self) -> bool:
        """Check if order is paid."""
        return self.payment_status == 'paid' and self.paid_at is not None
    
    @property
    def is_completed(self) -> bool:
        """Check if order is completed."""
        return self.status == OrderStatus.COMPLETED
    
    @property
    def is_cancelled(self) -> bool:
        """Check if order is cancelled."""
        return self.status == OrderStatus.CANCELLED
    
    @property
    def is_refunded(self) -> bool:
        """Check if order is refunded."""
        return self.status == OrderStatus.REFUNDED
    
    @property
    def is_refundable(self) -> bool:
        """Check if order can be refunded."""
        return (
            self.status == OrderStatus.COMPLETED and
            self.is_paid and
            self.refund_amount < self.order_total
        )
    
    @property
    def days_since_creation(self) -> int:
        """Days since order was created."""
        return (datetime.now() - self.created_at).days
    
    @property
    def payment_overdue(self) -> bool:
        """Check if payment is overdue."""
        if not self.payment_due_date or self.is_paid:
            return False
        return datetime.now() > self.payment_due_date
    
    @property
    def risk_level(self) -> str:
        """Get risk level based on fraud score."""
        if self.fraud_score >= 80:
            return "high"
        elif self.fraud_score >= 50:
            return "medium"
        else:
            return "low"
    
    @property
    def net_amount(self) -> Decimal:
        """Calculate net amount after platform fees."""
        return self.order_total - self.platform_fee


class OrderCustomer(OrderResponse):
    """Customer view of order."""
    shop_name: Optional[str] = None
    shop_slug: Optional[str] = None
    shop_logo_url: Optional[str] = None
    shop_is_verified: bool = False
    
    # Customer-specific info
    can_cancel: bool = False
    cancel_deadline: Optional[datetime] = None
    can_request_refund: bool = False
    refund_deadline: Optional[datetime] = None
    can_download_digital: bool = False
    download_urls: Optional[List[Dict[str, Any]]] = None
    can_review: bool = False
    review_deadline: Optional[datetime] = None
    has_reviewed: bool = False


class OrderSeller(OrderResponse):
    """Seller view of order."""
    buyer_email: str  # Same as customer_email but renamed for clarity
    buyer_name: Optional[str] = None
    buyer_has_account: bool = False
    buyer_account_id: Optional[str] = None
    buyer_total_orders: int = 0
    buyer_is_verified: bool = False
    
    # Seller-specific info
    can_fulfill: bool = False
    can_ship: bool = False
    can_mark_delivered: bool = False
    can_cancel: bool = False
    can_refund: bool = False
    can_update_tracking: bool = False
    
    # Financial info
    payout_status: str = "pending"
    payout_amount: Optional[Decimal] = None
    payout_date: Optional[datetime] = None
    payout_method: Optional[str] = None
    
    # Shop info
    shop_currency: str = "USD"
    shop_timezone: str = "UTC"
    shop_notification_email: Optional[str] = None
    shop_support_email: Optional[str] = None


class OrderStatusUpdate(BaseSchema):
    """Order status update request."""
    status: OrderStatus
    notes: Optional[str] = Field(None, max_length=1000, description="Status change notes")
    notify_customer: bool = Field(True, description="Notify customer of status change")


class OrderRefundRequest(BaseSchema):
    """Order refund request."""
    refund_amount: Decimal = Field(..., gt=0, description="Refund amount")
    refund_reason: str = Field(..., min_length=10, max_length=500, description="Refund reason")
    notify_customer: bool = Field(True, description="Notify customer of refund")
    refund_shipping: bool = Field(False, description="Refund shipping cost")
    restock_items: bool = Field(True, description="Restock refunded items")


class OrderSearchParams(PaginationParams):
    """Order search parameters."""
    search: Optional[str] = None
    shop_id: Optional[str] = None
    customer_email: Optional[str] = None
    status: Optional[OrderStatus] = None
    order_type: Optional[OrderType] = None
    payment_status: Optional[str] = None
    fulfillment_status: Optional[FulfillmentStatus] = None
    payment_method: Optional[PaymentMethod] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    min_amount: Optional[Decimal] = Field(None, ge=0)
    max_amount: Optional[Decimal] = Field(None, ge=0)
    has_digital: Optional[bool] = None
    has_physical: Optional[bool] = None


class OrderExportRequest(BaseSchema):
    """Order export request."""
    format: str = Field("csv", pattern="^(csv|json|excel)$")
    fields: Optional[List[str]] = Field(None, description="Fields to export")
    filters: Optional[Dict[str, Any]] = Field(None, description="Export filters")
    include_items: bool = Field(False, description="Include order items")
    include_customer: bool = Field(False, description="Include customer details")
    include_payment: bool = Field(False, description="Include payment details")


class OrderBulkAction(BaseSchema):
    """Bulk order action (seller/admin only)."""
    order_ids: List[str] = Field(..., min_items=1, max_items=50, description="Order IDs")
    action: str = Field(
        ...,
        pattern="^(fulfill|ship|complete|cancel|refund|update_status|export_labels)$"
    )
    data: Optional[Dict[str, Any]] = Field(None, description="Action data")
    reason: Optional[str] = Field(None, max_length=500, description="Action reason")
    notify_customers: bool = Field(True, description="Notify customers")


class OrderFulfillmentRequest(BaseSchema):
    """Order fulfillment request."""
    items: List[Dict[str, Any]] = Field(..., min_items=1, description="Items to fulfill")
    tracking_number: Optional[str] = Field(None, max_length=100, description="Tracking number")
    shipping_provider: Optional[str] = Field(None, max_length=50, description="Shipping provider")
    estimated_delivery_date: Optional[datetime] = None
    notes: Optional[str] = Field(None, max_length=1000, description="Fulfillment notes")
    notify_customer: bool = Field(True, description="Notify customer")


class OrderDeliveryConfirmation(BaseSchema):
    """Order delivery confirmation."""
    delivered_at: datetime = Field(default_factory=datetime.now, description="Delivery timestamp")
    delivery_notes: Optional[str] = Field(None, max_length=1000, description="Delivery notes")
    customer_signature: Optional[str] = Field(None, max_length=500, description="Customer signature (if required)")
    delivery_proof: Optional[List[Dict[str, Any]]] = Field(None, description="Delivery proof (photos, etc.)")