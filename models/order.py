from datetime import datetime, timedelta
from typing import Optional, List
from decimal import Decimal
from sqlalchemy import (
    String, Boolean, DateTime, Enum, Text, JSON, 
    Numeric, Integer, ForeignKey, ARRAY
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from models.base import Base
import enum


class OrderStatus(enum.Enum):
    """Order status."""
    PENDING = "pending"
    PROCESSING = "processing"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    FAILED = "failed"
    
    def __str__(self):
        return self.value

class OrderType(enum.Enum):
    """Order type."""
    DIGITAL = "digital"
    PHYSICAL = "physical"
    MIXED = "mixed"
    SUBSCRIPTION = "subscription"
    
    def __str__(self):
        return self.value
    
# models/order.py dosyasına ekleyin (PaymentMethod class'ından sonra):

class FulfillmentStatus(enum.Enum):
    """Order fulfillment status."""
    UNFULFILLED = "unfulfilled"
    PARTIALLY_FULFILLED = "partially_fulfilled"
    FULFILLED = "fulfilled"
    RESTOCKED = "restocked"
    
    def __str__(self):
        return self.value

class PaymentMethod(enum.Enum):
    """Payment method."""
    CREDIT_CARD = "credit_card"
    BANK_TRANSFER = "bank_transfer"
    PAYPAL = "paypal"
    STRIPE = "stripe"
    APPLE_PAY = "apple_pay"
    GOOGLE_PAY = "google_pay"
    CASH_ON_DELIVERY = "cash_on_delivery"
    
    def __str__(self):
        return self.value


class Order(Base):
    """Order model - maps to 'orders' table."""
    __tablename__ = "orders"
    
    # ===== RELATIONSHIPS =====
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
    cart_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("carts.id", ondelete="SET NULL")
    )
    
    # ===== ORDER IDENTITY =====
    order_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    
    status: Mapped[str] = mapped_column(
    String(20),
    default=OrderStatus.PENDING.value,
    nullable=False,
    index=True
    )

    order_type: Mapped[str] = mapped_column(
    String(20),
    default=OrderType.PHYSICAL.value,
    nullable=False
    )

    
    # ===== CUSTOMER INFO =====
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    customer_name: Mapped[Optional[str]] = mapped_column(String(100))
    customer_phone: Mapped[Optional[str]] = mapped_column(String(20))
    customer_notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # ===== ADDRESSES =====
    billing_address: Mapped[dict] = mapped_column(JSON, default=lambda: {})
    shipping_address: Mapped[dict] = mapped_column(JSON, default=lambda: {})
    shipping_same_as_billing: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # ===== PRICING =====
    items_subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.00)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.00)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.00)
    shipping_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.00)
    platform_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.00)
    seller_payout: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.00)
    order_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.00)
    
    currency: Mapped[str] = mapped_column(String(3), default='USD')
    
    # ===== DISCOUNT =====
    coupon_code: Mapped[Optional[str]] = mapped_column(String(50))
    coupon_type: Mapped[Optional[str]] = mapped_column(String(20))
    coupon_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    
    # ===== PAYMENT =====
    payment_method: Mapped[Optional[str]] = mapped_column(
    String(30),
    nullable=True
    )

    payment_status: Mapped[str] = mapped_column(String(20), default='pending')
    
    stripe_payment_intent_id: Mapped[Optional[str]] = mapped_column(String(255))
    stripe_charge_id: Mapped[Optional[str]] = mapped_column(String(255))
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255))
    
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    payment_due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # ===== SHIPPING =====
    requires_shipping: Mapped[bool] = mapped_column(Boolean, default=False)
    shipping_method: Mapped[Optional[str]] = mapped_column(String(50))
    shipping_provider: Mapped[Optional[str]] = mapped_column(String(50))
    tracking_number: Mapped[Optional[str]] = mapped_column(String(100))
    estimated_delivery_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # ===== FULFILLMENT =====
    fulfillment_notes: Mapped[Optional[str]] = mapped_column(Text)
    digital_delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    digital_delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # ===== REFUND =====
    refund_reason: Mapped[Optional[str]] = mapped_column(Text)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.00)
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # ===== RISK & FRAUD =====
    fraud_score: Mapped[int] = mapped_column(Integer, default=0)
    fraud_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    fraud_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    high_risk: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # ===== METADATA =====
    meta_data: Mapped[dict] = mapped_column(JSON, default=lambda: {})
    
    # ===== EMAIL STATUS =====
    email_confirmation_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    email_confirmation_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    email_shipping_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    email_shipping_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    email_delivered_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    email_delivered_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # ===== TIMESTAMPS =====
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # ===== RELATIONSHIPS =====
    # Items will be retrieved from cart_items via cart_id
    status_logs: Mapped[List["OrderStatusLog"]] = relationship(
        "OrderStatusLog",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="desc(OrderStatusLog.created_at)",
        lazy="selectin"
    )
    
    # ===== HELPER PROPERTIES =====
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
        return (datetime.now(self.created_at.tzinfo) - self.created_at).days
    
    @property
    def payment_overdue(self) -> bool:
        """Check if payment is overdue."""
        if not self.payment_due_date or self.is_paid:
            return False
        return datetime.now(self.payment_due_date.tzinfo) > self.payment_due_date
    
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
    
    def get_status_history(self) -> List[dict]:
        """Get order status history."""
        return [
            {
                "status": log.new_status,
                "changed_at": log.created_at.isoformat() if log.created_at else None,
                "notes": log.notes,
                "changed_by": log.changed_by
            }
            for log in sorted(self.status_logs, key=lambda x: x.created_at)
        ]
    
    def to_customer_dict(self) -> dict:
        """Customer view of order."""
        return {
            "id": self.id,
            "order_number": self.order_number,
            "status": self.status,
            "order_type": self.order_type,
            "items_subtotal": float(self.items_subtotal) if self.items_subtotal else 0.0,
            "discount_total": float(self.discount_total) if self.discount_total else 0.0,
            "shipping_total": float(self.shipping_total) if self.shipping_total else 0.0,
            "tax_total": float(self.tax_total) if self.tax_total else 0.0,
            "order_total": float(self.order_total) if self.order_total else 0.0,
            "currency": self.currency,
            "payment_method": self.payment_method if self.payment_method else None,
            "payment_status": self.payment_status,
            "is_paid": self.is_paid,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "requires_shipping": self.requires_shipping,
            "shipping_method": self.shipping_method,
            "tracking_number": self.tracking_number,
            "estimated_delivery_date": self.estimated_delivery_date.isoformat() if self.estimated_delivery_date else None,
            "digital_delivered": self.digital_delivered,
            "digital_delivered_at": self.digital_delivered_at.isoformat() if self.digital_delivered_at else None,
            "refund_amount": float(self.refund_amount) if self.refund_amount else 0.0,
            "customer_email": self.customer_email,
            "customer_name": self.customer_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "status_history": self.get_status_history(),
            "is_refundable": self.is_refundable,
            "payment_overdue": self.payment_overdue
        }
    
    def to_seller_dict(self) -> dict:
        """Seller view of order."""
        customer_data = self.to_customer_dict()
        customer_data.update({
            "shop_id": self.shop_id,
            "buyer_id": self.buyer_id,
            "billing_address": self.billing_address,
            "shipping_address": self.shipping_address,
            "platform_fee": float(self.platform_fee) if self.platform_fee else 0.0,
            "seller_payout": float(self.seller_payout) if self.seller_payout else 0.0,
            "net_amount": float(self.net_amount) if self.net_amount else 0.0,
            "coupon_code": self.coupon_code,
            "coupon_type": self.coupon_type,
            "customer_phone": self.customer_phone,
            "customer_notes": self.customer_notes,
            "fraud_score": self.fraud_score,
            "risk_level": self.risk_level,
            "high_risk": self.high_risk,
            "manual_review_required": self.manual_review_required,
            "fulfillment_notes": self.fulfillment_notes,
            "email_confirmation_sent": self.email_confirmation_sent,
            "email_shipping_sent": self.email_shipping_sent,
            "email_delivered_sent": self.email_delivered_sent,
            "metadata": self.meta_data
        })
        return customer_data


class OrderStatusLog(Base):
    """Order status log model - maps to 'order_status_logs' table."""
    __tablename__ = "order_status_logs"
    
    # ===== RELATIONSHIPS =====
    order_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    changed_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL")
    )
    
    # ===== STATUS CHANGE =====
    old_status: Mapped[str] = mapped_column(
    String(20),
    nullable=False
    )

    new_status: Mapped[str] = mapped_column(
    String(20),
    nullable=False
    )

    
    # ===== NOTES =====
    notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # ===== RELATIONSHIPS =====
    order: Mapped["Order"] = relationship("Order", back_populates="status_logs")
    
    def to_dict(self) -> dict:
        """Status log representation."""
        return {
            "id": self.id,
            "order_id": self.order_id,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "notes": self.notes,
            "changed_by": self.changed_by,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }