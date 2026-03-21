from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator, HttpUrl
from decimal import Decimal
from enum import Enum

from routers.base import BaseSchema, TimestampSchema


# ==================== ENUMS ====================


class PaymentStatus(str, Enum):
    """Payment status."""
    REQUIRES_PAYMENT_METHOD = "requires_payment_method"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    REQUIRES_ACTION = "requires_action"
    PROCESSING = "processing"
    REQUIRES_CAPTURE = "requires_capture"
    CANCELLED = "canceled"
    SUCCEEDED = "succeeded"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"
    FAILED = "failed"
    EXPIRED = "expired"


class PaymentMethodCategory(str, Enum):
    """Payment method category."""
    CARD = "card"
    WALLET = "wallet"
    BANK_TRANSFER = "bank_transfer"
    BANK_REDIRECT = "bank_redirect"
    VOUCHER = "voucher"
    CASH = "cash"
    BUY_NOW_PAY_LATER = "buy_now_pay_later"
    MOBILE_MONEY = "mobile_money"
    CRYPTO = "crypto"


class PayoutStatus(str, Enum):
    """Payout status."""
    PENDING = "pending"
    IN_TRANSIT = "in_transit"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "canceled"
    REVERSED = "reversed"


# ==================== PAYMENT SCHEMAS ====================


class PaymentBase(BaseSchema):
    """Base payment schema."""
    order_id: str = Field(..., description="Order ID")
    payment_method_code: str = Field(..., description="Payment method code")
    amount: Decimal = Field(..., gt=0, le=1000000, description="Payment amount")
    currency: str = Field("USD", pattern="^[A-Z]{3}$", description="Currency")
    customer_email: str = Field(..., description="Customer email")
    customer_name: Optional[str] = Field(None, description="Customer name")
    customer_country: Optional[str] = Field(None, pattern="^[A-Z]{2}$", description="Customer country code")
    
    # Billing address
    billing_address: Optional[Dict[str, Any]] = Field(None, description="Billing address")
    
    # Save payment method for future use
    save_payment_method: bool = Field(False, description="Save payment method for future use")
    setup_future_usage: Optional[str] = Field(None, pattern="^(on_session|off_session)$", description="Future usage setup")


class PaymentCreate(PaymentBase):
    """Create payment schema."""
    return_url: Optional[HttpUrl] = Field(None, description="Return URL after payment")
    cancel_url: Optional[HttpUrl] = Field(None, description="Cancel URL")
    
    # 3D Secure
    requires_3ds: Optional[bool] = Field(None, description="Require 3D Secure")
    
    # Metadata
    metadata: Optional[Dict[str, Any]] = Field(None, description="Payment metadata")


class PaymentResponse(TimestampSchema):
    """Payment response."""
    id: str
    payment_number: str
    order_id: str
    shop_id: str
    buyer_id: Optional[str] = None
    
    # Payment method
    payment_method_code: str
    payment_provider_code: str
    
    # Amounts
    amount: Decimal
    currency: str
    shop_currency: str
    exchange_rate: Optional[Decimal] = None
    shop_amount: Optional[Decimal] = None
    
    # Fee breakdown
    provider_fee_amount: Decimal = Field(0.00, ge=0)
    provider_fee_percent: Decimal = Field(0.00, ge=0, le=100)
    platform_fee_amount: Decimal = Field(0.00, ge=0)
    platform_fee_percent: Decimal = Field(0.00, ge=0, le=100)
    tax_amount: Decimal = Field(0.00, ge=0)
    net_amount: Optional[Decimal] = None
    
    # Status
    status: str = "requires_payment_method"
    failure_reason: Optional[str] = None
    failure_code: Optional[str] = None
    risk_score: int = Field(0, ge=0, le=100)
    risk_level: str = "normal"
    
    # Provider specific
    provider_payment_id: Optional[str] = None
    provider_customer_id: Optional[str] = None
    provider_charge_id: Optional[str] = None
    
    # Payment details
    payment_details: Dict[str, Any] = Field(default_factory=dict)
    
    # Card details (if applicable)
    card_last4: Optional[str] = None
    card_brand: Optional[str] = None
    card_country: Optional[str] = None
    card_exp_month: Optional[int] = None
    card_exp_year: Optional[int] = None
    card_funding: Optional[str] = None
    
    # Customer info
    customer_email: str
    customer_name: Optional[str] = None
    customer_country: Optional[str] = None
    customer_locale: Optional[str] = None
    
    # Billing & Shipping
    billing_address: Optional[Dict[str, Any]] = None
    shipping_address: Optional[Dict[str, Any]] = None
    
    # 3D Secure
    requires_3ds: bool = False
    three_d_secure_status: Optional[str] = None
    authentication_flow: Optional[str] = None
    
    # Capture info
    capture_method: str = "automatic"
    captured_amount: Decimal = Field(0.00, ge=0)
    uncaptured_amount: Optional[Decimal] = None
    
    # Refund info
    refunded_amount: Decimal = Field(0.00, ge=0)
    refund_count: int = 0
    
    # Timestamps
    authorized_at: Optional[datetime] = None
    captured_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    last_webhook_received_at: Optional[datetime] = None
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Payment intents
    intents: List["PaymentIntentResponse"] = Field(default_factory=list)
    
    # Helper properties
    @property
    def is_successful(self) -> bool:
        """Check if payment was successful."""
        return self.status == 'succeeded'
    
    @property
    def is_refunded(self) -> bool:
        """Check if payment is refunded."""
        return self.status in ['refunded', 'partially_refunded']
    
    @property
    def is_captured(self) -> bool:
        """Check if payment is captured."""
        return self.captured_amount >= self.amount
    
    @property
    def can_refund(self) -> bool:
        """Check if payment can be refunded."""
        return (
            self.is_successful and
            self.is_captured and
            self.refunded_amount < self.captured_amount
        )
    
    @property
    def remaining_refund_amount(self) -> Decimal:
        """Amount that can still be refunded."""
        if not self.can_refund:
            return Decimal('0.00')
        return self.captured_amount - self.refunded_amount
    
    @property
    def total_fees(self) -> Decimal:
        """Total fees (provider + platform)."""
        return self.provider_fee_amount + self.platform_fee_amount


class PaymentIntentCreate(BaseSchema):
    """Create payment intent schema."""
    payment_id: str = Field(..., description="Payment ID")
    payment_method_types: Optional[List[str]] = Field(None, description="Allowed payment method types")
    confirmation_method: str = Field("automatic", pattern="^(automatic|manual)$", description="Confirmation method")
    capture_method: str = Field("automatic", pattern="^(automatic|manual)$", description="Capture method")
    setup_future_usage: Optional[str] = Field(None, pattern="^(on_session|off_session)$", description="Future usage")


class PaymentIntentResponse(TimestampSchema):
    """Payment intent response."""
    id: str
    payment_id: str
    provider_intent_id: str
    client_secret: Optional[str] = None
    
    # Amounts
    amount: Decimal
    currency: str
    amount_received: Decimal = Field(0.00, ge=0)
    
    # Status & Flow
    status: str
    cancellation_reason: Optional[str] = None
    next_action: Optional[Dict[str, Any]] = None
    
    # Payment method config
    payment_method_types: Optional[List[str]] = None
    setup_future_usage: Optional[str] = None
    
    # Confirmation
    confirmation_method: str = "automatic"
    confirm_url: Optional[str] = None
    
    # Customer & Order
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    order_details: Dict[str, Any] = Field(default_factory=dict)
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    provider_metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Timestamps
    confirmed_at: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    expires_at: datetime
    
    # Helper properties
    @property
    def is_expired(self) -> bool:
        """Check if payment intent is expired."""
        return datetime.now() > self.expires_at
    
    @property
    def requires_action(self) -> bool:
        """Check if payment requires customer action."""
        return self.status in ['requires_action', 'requires_confirmation']


class PaymentCaptureRequest(BaseSchema):
    """Payment capture request."""
    amount: Optional[Decimal] = Field(None, gt=0, description="Amount to capture (partial capture)")
    capture_reason: Optional[str] = Field(None, max_length=500, description="Capture reason")


class PaymentRefundRequest(BaseSchema):
    """Payment refund request."""
    amount: Optional[Decimal] = Field(None, gt=0, description="Refund amount (partial refund)")
    refund_reason: str = Field(..., min_length=10, max_length=500, description="Refund reason")
    refund_items: Optional[List[Dict[str, Any]]] = Field(None, description="Items to refund")
    refund_shipping: bool = Field(False, description="Refund shipping cost")
    reverse_transfer: bool = Field(False, description="Reverse transfer to seller")


class PaymentMethodRequest(BaseSchema):
    """Payment method request (for saved methods)."""
    payment_method_id: str = Field(..., description="Payment method ID from provider")
    setup_intent_id: Optional[str] = Field(None, description="Setup intent ID")
    customer_id: Optional[str] = Field(None, description="Customer ID from provider")


class PaymentMethodResponse(BaseSchema):
    """Payment method response."""
    id: str
    provider_payment_method_id: str
    type: str
    card_last4: Optional[str] = None
    card_brand: Optional[str] = None
    card_exp_month: Optional[int] = None
    card_exp_year: Optional[int] = None
    card_country: Optional[str] = None
    wallet_type: Optional[str] = None
    bank_name: Optional[str] = None
    bank_last4: Optional[str] = None
    created_at: datetime
    is_default: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WebhookEvent(BaseSchema):
    """Webhook event schema."""
    id: str
    provider_code: str
    event_type: str
    provider_event_id: str
    raw_payload: Dict[str, Any]
    signature: Optional[str] = None
    ip_address: Optional[str] = None
    status: str = "pending"
    processing_attempts: int = 0
    error_message: Optional[str] = None
    received_at: datetime
    processed_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None


class PayoutRequest(BaseSchema):
    """Payout request (seller to get paid)."""
    amount: Decimal = Field(..., gt=0, description="Payout amount")
    payout_method_code: str = Field(..., description="Payout method code")
    currency: str = Field("USD", pattern="^[A-Z]{3}$", description="Payout currency")
    notes: Optional[str] = Field(None, max_length=500, description="Payout notes")


class PayoutResponse(TimestampSchema):
    """Payout response."""
    id: str
    payout_number: str
    shop_id: str
    payout_account_id: str
    
    # Amounts
    amount: Decimal
    currency: str
    exchange_rate: Optional[Decimal] = None
    payout_currency: Optional[str] = None
    payout_amount: Optional[Decimal] = None
    
    # Fees
    provider_fee_amount: Decimal = Field(0.00, ge=0)
    platform_fee_amount: Decimal = Field(0.00, ge=0)
    forex_fee_amount: Decimal = Field(0.00, ge=0)
    net_amount: Optional[Decimal] = None
    
    # Status
    status: PayoutStatus = PayoutStatus.PENDING
    failure_reason: Optional[str] = None
    failure_code: Optional[str] = None
    
    # Provider details
    provider_payout_id: Optional[str] = None
    provider_transfer_id: Optional[str] = None
    provider_batch_id: Optional[str] = None
    
    # Timing
    estimated_arrival_date: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    
    # Source
    source_payments: Optional[List[str]] = Field(None, description="Source payment IDs")
    source_balance_snapshot: Optional[Dict[str, Any]] = None
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    provider_response: Dict[str, Any] = Field(default_factory=dict)