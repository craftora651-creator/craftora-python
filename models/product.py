# app/models/product.py
from datetime import datetime, timezone
from typing import Optional, List
from decimal import Decimal
from sqlalchemy import (
    String, Boolean, DateTime, Text,
    BigInteger, Numeric, ARRAY, ForeignKey, Integer, Computed
)
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base
import enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
from sqlalchemy import text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship


# ==================== ENUM SINIFLARI ====================

class DigitalDeliveryMethod(str, enum.Enum):
    """Digital delivery method enum."""
    INSTANT = "instant"
    MANUAL = "manual"
    DRIP = "drip"
    
    def __str__(self):
        return self.value


class FileType(str, enum.Enum):
    """File type enum - PostgreSQL ile uyumlu."""
    PDF = "pdf"
    VIDEO = "video"
    AUDIO = "audio"
    ARCHIVE = "archive"
    IMAGE = "image"
    DOCUMENT = "document"
    SOFTWARE = "software"
    OTHER = "other"
    
    def __str__(self):
        return self.value


class FulfillmentType(str, enum.Enum):
    """Fulfillment type enum - PostgreSQL ile uyumlu."""
    AUTO = "auto"
    MANUAL = "manual"
    DRIP = "drip"

    def __str__(self):
        return self.value


class ProductStatus(str, enum.Enum):
    """Product status."""
    DRAFT = "draft"
    PENDING = "pending"
    PUBLISHED = "published"
    SOLD_OUT = "sold_out"
    ARCHIVED = "archived"
    DELETED = "deleted"
    
    def __str__(self):
        return self.value


class ProductType(str, enum.Enum):
    """Product type."""
    DIGITAL = "digital"
    PHYSICAL = "physical"
    SERVICE = "service"
    
    def __str__(self):
        return self.value


class Currency(str, enum.Enum):
    """Currency."""
    USD = "USD"
    TRY = "TRY"
    EUR = "EUR"
    GBP = "GBP"
    
    def __str__(self):
        return self.value


# ==================== PRODUCT MODEL ====================

def pg_enum(enum_cls, name: str):
        return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda obj: [e.value for e in obj]
    )

class Product(Base):
    
    """Product model - maps to 'products' table."""
    __tablename__ = "products"

    # ===== PRIMARY KEY =====
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()")
    )

    # ===== ENUM ALANLARI (Artık PostgreSQL enum'ları ile uyumlu) =====
    product_type: Mapped[ProductType] = mapped_column(
    pg_enum(ProductType, "product_type"),
    nullable=False,
    default=ProductType.DIGITAL
)


    status: Mapped[ProductStatus] = mapped_column(
    pg_enum(ProductStatus, "product_status"),
    nullable=False,
    default=ProductStatus.DRAFT
)

    currency: Mapped[Currency] = mapped_column(
    pg_enum(Currency, "currency"),
    nullable=False,
    default=Currency.USD
)

    base_currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="USD",
        server_default="USD"
    )

    file_type: Mapped[Optional[FileType]] = mapped_column(
    pg_enum(FileType, "file_type")
)

    fulfillment_type: Mapped[Optional[FulfillmentType]] = mapped_column(
    pg_enum(FulfillmentType, "fulfillment_type")
)

    # ===== RELATIONSHIPS =====
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    shop = relationship("Shop", back_populates="products")

    # ===== PRODUCT IDENTITY =====
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    short_description: Mapped[Optional[str]] = mapped_column(String(300))

    # ===== PRICING =====
    base_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    prices: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb")
    )
    compare_at_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    cost_per_item: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    
    # ===== SALE =====
    is_on_sale: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sale_starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sale_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # ===== INVENTORY =====
    file_size: Mapped[int] = mapped_column(  
        BigInteger,
        nullable=True,
        default=None,
        server_default=None
    )
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    allows_backorder: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sku: Mapped[Optional[str]] = mapped_column(String(100))
    barcode: Mapped[Optional[str]] = mapped_column(String(100))
    
    # ===== DIGITAL PRODUCT SPECIFIC =====
    file_url: Mapped[Optional[str]] = mapped_column(Text)
    file_name: Mapped[Optional[str]] = mapped_column(String(255))
    download_limit: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    access_duration_days: Mapped[Optional[int]] = mapped_column(Integer)
    
    # ===== SHOP RELATED =====
    shop_is_active_public: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false"
    )
    
    # ===== VISUAL & MEDIA =====
    feature_image_url: Mapped[Optional[str]] = mapped_column(Text)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text)
    video_url: Mapped[Optional[str]] = mapped_column(Text)
    image_gallery: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text))
    
    # ===== SEO & VISIBILITY =====
    seo_title: Mapped[Optional[str]] = mapped_column(String(70))
    seo_description: Mapped[Optional[str]] = mapped_column(String(160))
    seo_keywords: Mapped[Optional[str]] = mapped_column(String(200))
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_best_seller: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_new_arrival: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_available: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default="true"
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false"
    )
    
    # ===== FIZIKSEL URUN ALANLARI =====
    watermark_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    drm_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    weight: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    dimensions: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        default=lambda: {"length": 0, "width": 0, "height": 0}
    )
    requires_shipping: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    shipping_class: Mapped[Optional[str]] = mapped_column(String(100))
    customs_info: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    processing_time_days: Mapped[Optional[int]] = mapped_column(Integer, default=1, server_default="1")
    digital_delivery_method: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="instant",
        server_default="instant"
    )
    
    # ===== DATES =====
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # ===== CATEGORY & TAGS =====
    primary_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    secondary_categories: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String(50)), nullable=True)
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    
    # ===== STATISTICS =====
    view_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    unique_view_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    purchase_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    wishlist_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cart_add_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    average_rating: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=0.00, server_default="0.00")
    review_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    refund_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0.00, server_default="0.00")
    
    # ===== PLATFORM FEES =====
    platform_fee_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), 
        default=Decimal("0.00"), 
        server_default="0.00"
    )
    platform_fee_fixed: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), 
        default=Decimal("0.00"), 
        server_default="0.00"
    )
    
    # ===== GENERATED COLUMNS =====
    price_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        Computed("base_price"),
        nullable=False
    )

    payout_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        Computed("base_price - (base_price * platform_fee_percent / 100) - platform_fee_fixed"),
        nullable=True
    )
    
    # ===== METADATA =====
    meta_data: Mapped[dict] = mapped_column(
        JSONB,
        default=lambda: {
            "source": "craftora_platform",
            "quality_score": 0,
            "ai_generated": False,
            "content_verified": False,
            "last_scanned_at": None
        },
        server_default=text("""'{
            "source": "craftora_platform",
            "quality_score": 0,
            "ai_generated": false,
            "content_verified": false,
            "last_scanned_at": null
        }'::jsonb"""),
        name="metadata"
    )
    
    # ===== TIMESTAMPS =====
    last_sold_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_restocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # ===== Base sınıfından gelen timestamps =====
    # created_at, updated_at Base'den geliyor

    # ==================== PROPERTY'LER ====================
    
    @property
    def digital_delivery_method_enum(self) -> DigitalDeliveryMethod:
        """String'den DigitalDeliveryMethod enum'una çevir."""
        return DigitalDeliveryMethod(self.digital_delivery_method)
    
    @property
    def product_type_enum(self) -> ProductType:
        """String'den ProductType enum'una çevir - ARTIK GEREK YOK ama uyumluluk için kalabilir."""
        return self.product_type  # Direkt enum döndür
    
    @property
    def status_enum(self) -> ProductStatus:
        """String'den ProductStatus enum'una çevir."""
        return self.status  # Direkt enum döndür
    
    @property
    def currency_enum(self) -> Currency:
        """String'den Currency enum'una çevir."""
        return self.currency  # Direkt enum döndür
    
    @property
    def base_currency_enum(self) -> Currency:
        """String'den Currency enum'una çevir."""
        return Currency(self.base_currency)

    @property
    def file_type_enum(self) -> Optional[FileType]:
        """String'den FileType enum'una çevir."""
        return self.file_type if self.file_type else None  # Direkt enum döndür

    @property
    def fulfillment_type_enum(self) -> Optional[FulfillmentType]:
        """String'den FulfillmentType enum'una çevir."""
        return self.fulfillment_type if self.fulfillment_type else None  # Direkt enum döndür

    @property
    def is_purchasable(self) -> bool:
        """Check if product is available for purchase."""
        return (
            self.status == ProductStatus.PUBLISHED and
            self.is_approved and
            not self.requires_approval and
            self.shop_is_active_public and
            self.is_available
        )

    @property
    def is_in_stock(self) -> bool:
        """Check if product is in stock."""
        if self.product_type == ProductType.DIGITAL:
            return True
        return self.stock_quantity > 0 or self.allows_backorder

    @property
    def is_low_stock(self) -> bool:
        """Check if product is low in stock."""
        if self.product_type == ProductType.DIGITAL:
            return False
        return 0 < self.stock_quantity <= self.low_stock_threshold

    @property
    def is_on_sale_now(self) -> bool:
        """Check if sale is currently active."""
        if not self.is_on_sale:
            return False
        
        now = datetime.now(timezone.utc)
        
        if self.sale_starts_at and now < self.sale_starts_at:
            return False
        if self.sale_ends_at and now > self.sale_ends_at:
            return False
        return True

    # ==================== METODLAR ====================

    def get_price(self, currency_code: str) -> Decimal:
        """Get price in specified currency."""
        if not currency_code:
            return self.base_price
        currency_code = currency_code.upper()
        if self.prices and currency_code in self.prices:
            return Decimal(str(self.prices[currency_code]))
        # Generated kolonlara bak
        if currency_code == "USD":
            return self.base_price
        return self.base_price

    def get_current_price(self, currency_code: str) -> Decimal:
        return self.get_price(currency_code)
    
    def get_discount_percentage(self, currency_code: str) -> Optional[int]:
        """Get discount percentage if on sale."""
        if not self.compare_at_price or not self.is_on_sale_now:
            return None
        
        current = self.get_current_price(currency_code)
        if current >= self.compare_at_price:
            return None
        
        discount = ((self.compare_at_price - current) / self.compare_at_price) * 100
        return int(discount)

    def to_public_dict(self, currency_code: str = "USD") -> dict:
        """Public representation for marketplace."""
        current_price = self.get_current_price(currency_code)
        
        return {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "short_description": self.short_description,

            "display_currency": currency_code.upper(),
            "current_price": float(current_price),
            "base_price": float(self.base_price),
            "discount_percentage": self.get_discount_percentage(currency_code),

            "is_on_sale": self.is_on_sale_now,

            "product_type": self.product_type.value,  # .value ile string'e çevir
            "is_digital": self.product_type == ProductType.DIGITAL,
            "is_physical": self.product_type == ProductType.PHYSICAL,
            "is_service": self.product_type == ProductType.SERVICE,
            
            "is_in_stock": self.is_in_stock,
            "is_low_stock": self.is_low_stock,

            "feature_image_url": self.feature_image_url,
            "image_gallery": self.image_gallery or [],
            "video_url": self.video_url,

            "average_rating": float(self.average_rating) if self.average_rating else 0.0,
            "review_count": self.review_count,
            "purchase_count": self.purchase_count,

            "is_featured": self.is_featured,
            "is_best_seller": self.is_best_seller,
            "is_new_arrival": self.is_new_arrival,

            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,

            "is_available": self.is_purchasable,
            
            # Digital product specific
            "download_limit": self.download_limit if self.product_type == ProductType.DIGITAL else None,
            "access_duration_days": self.access_duration_days if self.product_type == ProductType.DIGITAL else None,
            
            # Physical product specific
            "requires_shipping": self.requires_shipping if self.product_type == ProductType.PHYSICAL else False,
            "weight": float(self.weight) if self.weight and self.product_type == ProductType.PHYSICAL else None,
        }

    def to_seller_dict(self, currency_code: str = "USD") -> dict:
        """Seller-only representation."""
        public_data = self.to_public_dict(currency_code)
        
        # Seller-specific fields
        seller_data = {
            "status": self.status.value,  # .value ile string'e çevir
            "status_display": self.status.value,
            "sku": self.sku,
            "barcode": self.barcode,
            "cost_per_item": float(self.cost_per_item) if self.cost_per_item else None,
            "stock_quantity": self.stock_quantity,
            "low_stock_threshold": self.low_stock_threshold,
            "allows_backorder": self.allows_backorder,
            
            "platform_fee_percent": float(self.platform_fee_percent),
            "platform_fee_fixed": float(self.platform_fee_fixed),
            "payout_amount": float(self.payout_amount) if self.payout_amount else None,
            
            "requires_approval": self.requires_approval,
            "is_approved": self.is_approved,
            
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "last_sold_at": self.last_sold_at.isoformat() if self.last_sold_at else None,
            "last_restocked_at": self.last_restocked_at.isoformat() if self.last_restocked_at else None,
            
            "wishlist_count": self.wishlist_count,
            "cart_add_count": self.cart_add_count,
            "unique_view_count": self.unique_view_count,
            "refund_rate": float(self.refund_rate) if self.refund_rate else 0.0,
            
            "primary_category": self.primary_category,
            "secondary_categories": self.secondary_categories or [],
            "tags": self.tags or [],
            
            "seo_title": self.seo_title,
            "seo_description": self.seo_description,
            "seo_keywords": self.seo_keywords,
            
            "file_name": self.file_name,
            "file_type": self.file_type.value if self.file_type else None,  # .value ile
            "file_size": self.file_size,
            "file_url": self.file_url,
            
            "watermark_enabled": self.watermark_enabled,
            "drm_enabled": self.drm_enabled,
            
            "dimensions": self.dimensions,
            "shipping_class": self.shipping_class,
            "customs_info": self.customs_info,
            "processing_time_days": self.processing_time_days,
            "digital_delivery_method": self.digital_delivery_method,
            
            "metadata": self.meta_data
        }
        
        public_data.update(seller_data)
        return public_data


# ==================== RELATED MODELS ====================

class ProductImage(Base):
    """Product images model."""
    __tablename__ = "product_images"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()")
    )
    
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text)
    alt_text: Mapped[Optional[str]] = mapped_column(String(200))
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now,
        server_default=text("CURRENT_TIMESTAMP")
    )


class ProductVariant(Base):
    """Product variants model."""
    __tablename__ = "product_variants"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()")
    )
    
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Variant options
    option1_name: Mapped[Optional[str]] = mapped_column(String(50))
    option1_value: Mapped[Optional[str]] = mapped_column(String(50))
    option2_name: Mapped[Optional[str]] = mapped_column(String(50))
    option2_value: Mapped[Optional[str]] = mapped_column(String(50))
    option3_name: Mapped[Optional[str]] = mapped_column(String(50))
    option3_value: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Variant specifics
    sku: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
    barcode: Mapped[Optional[str]] = mapped_column(String(100))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    compare_at_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    cost_per_item: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    weight: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    image_url: Mapped[Optional[str]] = mapped_column(Text)
    
    # Statistics
    purchase_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now,
        server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now,
        onupdate=datetime.now,
        server_default=text("CURRENT_TIMESTAMP")
    )


class ProductDownload(Base):
    """Product downloads tracking model."""
    __tablename__ = "product_downloads"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()")
    )
    
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    order_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True
    )
    
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        index=True
    )
    
    download_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        index=True
    )
    
    download_url: Mapped[str] = mapped_column(Text, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))  # IPv6 ready
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    download_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now,
        server_default=text("CURRENT_TIMESTAMP")
    )
    last_download_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now,
        server_default=text("CURRENT_TIMESTAMP")
    )