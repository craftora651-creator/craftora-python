from datetime import datetime
from typing import Optional, List
from decimal import Decimal
from sqlalchemy import (
    String, Boolean, DateTime, Enum, Text, JSON, 
    Numeric, Integer, ForeignKey, ARRAY, BigInteger
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from models.base import Base
import enum
import uuid

class PaymentStatus(enum.Enum):
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
    
    def __str__(self):
        return self.value


class Payment(Base):
    """Payment model - maps to 'payments' table."""
    __tablename__ = "payments"
    
    # ===== IDENTIFIERS =====
    payment_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    
    # ===== RELATIONSHIPS =====
    order_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    shop_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("shops.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    buyer_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL")
    )
    
    # ===== PAYMENT METHOD =====
    payment_method_code: Mapped[str] = mapped_column(String(50), nullable=False)
    payment_provider_code: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # ===== AMOUNTS =====
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    shop_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    exchange_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    shop_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    
    # ===== FEE BREAKDOWN =====
    provider_fee_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.00)
    provider_fee_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0.00)
    platform_fee_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.00)
    platform_fee_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0.00)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0.00)
    
    net_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    
    # ===== STATUS =====
    status: Mapped[str] = mapped_column(String(20), default='requires_payment_method')
    failure_reason: Mapped[Optional[str]] = mapped_column(String(200))
    failure_code: Mapped[Optional[str]] = mapped_column(String(50))
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_level: Mapped[str] = mapped_column(String(20), default='normal')
    
    # ===== PROVIDER SPECIFIC =====
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(255))
    provider_customer_id: Mapped[Optional[str]] = mapped_column(String(255))
    provider_charge_id: Mapped[Optional[str]] = mapped_column(String(255))
    
    # ===== PAYMENT DETAILS =====
    payment_details: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {
            "card": None,
            "wallet": None,
            "bank_transfer": None,
            "redirect": None,
            "voucher": None
        }
    )
    
    # ===== CARD DETAILS =====
    card_last4: Mapped[Optional[str]] = mapped_column(String(4))
    card_brand: Mapped[Optional[str]] = mapped_column(String(20))
    card_country: Mapped[Optional[str]] = mapped_column(String(2))
    card_exp_month: Mapped[Optional[int]] = mapped_column(Integer)
    card_exp_year: Mapped[Optional[int]] = mapped_column(Integer)
    
    # ===== CUSTOMER INFO =====
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    customer_name: Mapped[Optional[str]] = mapped_column(String(100))
    customer_country: Mapped[Optional[str]] = mapped_column(String(2))
    customer_locale: Mapped[Optional[str]] = mapped_column(String(10))
    
    # ===== 3D SECURE =====
    requires_3ds: Mapped[bool] = mapped_column(Boolean, default=False)
    three_d_secure_status: Mapped[Optional[str]] = mapped_column(String(50))
    
    # ===== CAPTURE INFO =====
    capture_method: Mapped[str] = mapped_column(String(20), default='automatic')
    captured_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.00)
    uncaptured_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    
    # ===== REFUND INFO =====
    refunded_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.00)
    refund_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # ===== TIMESTAMPS =====
    authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_webhook_received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # ===== METADATA =====
    meta_data: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {
            "device": None,
            "browser": None,
            "ip_address": None,
            "user_agent": None,
            "session_id": None,
            "checkout_session_id": None,
            "utm_source": None,
            "utm_medium": None,
            "utm_campaign": None
        }
    )
    
    # ===== RELATIONSHIPS =====
    intents: Mapped[List["PaymentIntent"]] = relationship(
        "PaymentIntent",
        back_populates="payment",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    events: Mapped[List["PaymentEvent"]] = relationship(
        "PaymentEvent",
        back_populates="payment",
        cascade="all, delete-orphan",
        order_by="desc(PaymentEvent.created_at)",
        lazy="selectin"
    )
    
    # ===== HELPER PROPERTIES =====
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
    
    def to_dict(self) -> dict:
        """Payment representation."""
        return {
            "id": self.id,
            "payment_number": self.payment_number,
            "order_id": self.order_id,
            "shop_id": self.shop_id,
            "buyer_id": self.buyer_id,
            "amount": float(self.amount) if self.amount else 0.0,
            "currency": self.currency,
            "shop_currency": self.shop_currency,
            "shop_amount": float(self.shop_amount) if self.shop_amount else 0.0,
            "status": self.status,
            "payment_method_code": self.payment_method_code,
            "payment_provider_code": self.payment_provider_code,
            "provider_fee_amount": float(self.provider_fee_amount) if self.provider_fee_amount else 0.0,
            "platform_fee_amount": float(self.platform_fee_amount) if self.platform_fee_amount else 0.0,
            "net_amount": float(self.net_amount) if self.net_amount else 0.0,
            "customer_email": self.customer_email,
            "customer_name": self.customer_name,
            "is_successful": self.is_successful,
            "is_refunded": self.is_refunded,
            "is_captured": self.is_captured,
            "captured_amount": float(self.captured_amount) if self.captured_amount else 0.0,
            "refunded_amount": float(self.refunded_amount) if self.refunded_amount else 0.0,
            "can_refund": self.can_refund,
            "remaining_refund_amount": float(self.remaining_refund_amount) if self.remaining_refund_amount else 0.0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "authorized_at": self.authorized_at.isoformat() if self.authorized_at else None,
            "captured_at": self.captured_at.isoformat() if self.captured_at else None,
            "refunded_at": self.refunded_at.isoformat() if self.refunded_at else None,
            "card_brand": self.card_brand,
            "card_last4": self.card_last4,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score
        }


class PaymentIntent(Base):
    """Payment intent model - maps to 'payment_intents' table."""
    __tablename__ = "payment_intents"
    
    # ===== RELATIONSHIPS =====
    payment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("payments.id"),
        nullable=False,
        index=True
    )
    
    # ===== PROVIDER INTENT =====
    provider_intent_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    client_secret: Mapped[Optional[str]] = mapped_column(String(500))
    
    # ===== AMOUNTS =====
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_received: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.00)
    
    # ===== STATUS & FLOW =====
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    cancellation_reason: Mapped[Optional[str]] = mapped_column(String(100))
    next_action: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # ===== PAYMENT METHOD CONFIG =====
    payment_method_types: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String(50)))
    setup_future_usage: Mapped[Optional[str]] = mapped_column(String(50))
    
    # ===== CONFIRMATION =====
    confirmation_method: Mapped[str] = mapped_column(String(20), default='automatic')
    confirm_url: Mapped[Optional[str]] = mapped_column(String(500))
    
    # ===== TIMESTAMPS =====
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # ===== RELATIONSHIPS =====
    payment: Mapped["Payment"] = relationship("Payment", back_populates="intents")
    
    @property
    def is_expired(self) -> bool:
        """Check if payment intent is expired."""
        return datetime.now(self.expires_at.tzinfo) > self.expires_at
    
    @property
    def requires_action(self) -> bool:
        """Check if payment requires customer action."""
        return self.status in ['requires_action', 'requires_confirmation']
    
    def to_dict(self) -> dict:
        """Payment intent representation."""
        return {
            "id": self.id,
            "payment_id": self.payment_id,
            "provider_intent_id": self.provider_intent_id,
            "client_secret": self.client_secret,
            "amount": float(self.amount) if self.amount else 0.0,
            "currency": self.currency,
            "status": self.status,
            "next_action": self.next_action,
            "payment_method_types": self.payment_method_types,
            "requires_action": self.requires_action,
            "is_expired": self.is_expired,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "canceled_at": self.canceled_at.isoformat() if self.canceled_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class PaymentEvent(Base):
    """Payment event model - maps to 'payment_events' table."""
    __tablename__ = "payment_events"
    
    # ===== RELATIONSHIPS =====
    payment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # ===== EVENT DETAILS =====
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_event_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    provider_object_id: Mapped[Optional[str]] = mapped_column(String(255))
    
    # ===== STATUS CHANGES =====
    old_status: Mapped[Optional[str]] = mapped_column(String(50))
    new_status: Mapped[Optional[str]] = mapped_column(String(50))
    
    # ===== AMOUNTS =====
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    currency: Mapped[Optional[str]] = mapped_column(String(3))
    fee_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    
    # ===== ERROR HANDLING =====
    error_code: Mapped[Optional[str]] = mapped_column(String(50))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    decline_code: Mapped[Optional[str]] = mapped_column(String(50))
    
    # ===== RAW DATA =====
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    processed_data: Mapped[dict] = mapped_column(JSON, default=lambda: {})
    
    # ===== SOURCE =====
    source: Mapped[str] = mapped_column(String(20), default='webhook')
    
    # ===== TIMESTAMPS =====
    provider_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # ===== RELATIONSHIPS =====
    payment: Mapped["Payment"] = relationship("Payment", back_populates="events")
    
    def to_dict(self) -> dict:
        """Payment event representation."""
        return {
            "id": self.id,
            "payment_id": self.payment_id,
            "event_type": self.event_type,
            "provider_event_id": self.provider_event_id,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "amount": float(self.amount) if self.amount else None,
            "currency": self.currency,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "provider_created_at": self.provider_created_at.isoformat() if self.provider_created_at else None
        }