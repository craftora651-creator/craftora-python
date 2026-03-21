from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, validator, HttpUrl, condecimal
from decimal import Decimal
from enum import Enum

from routers.base import BaseSchema, TimestampSchema, PaginationParams
from uuid import UUID
from sqlalchemy.dialects.postgresql import JSONB
from typing import Optional
from pydantic import field_validator
from slugify import slugify

# ==================== ENUMS ====================

class ProductStatus(str, Enum):
    """Product status."""
    DRAFT = "draft"
    PENDING = "pending"
    PUBLISHED = "published"
    SOLD_OUT = "sold_out"
    ARCHIVED = "archived"
    DELETED = "deleted"

class ProductType(str, Enum):
    """Product type."""
    DIGITAL = "digital"
    PHYSICAL = "physical"
    SERVICE = "service"

class Currency(str, Enum):
    """Currency."""
    USD = "USD"
    TRY = "TRY"
    EUR = "EUR"
    GBP = "GBP"

class FileType(str, Enum):
    """File type for digital products."""
    PDF = "pdf"
    VIDEO = "video"
    AUDIO = "audio"
    ARCHIVE = "archive"
    IMAGE = "image"
    DOCUMENT = "document"
    SOFTWARE = "software"
    OTHER = "other"


class FulfillmentType(str, Enum):
    """Fulfillment type."""
    AUTO = "auto"
    MANUAL = "manual"
    DRIP = "drip"


# ==================== PRODUCT SCHEMAS ====================


class ProductBase(BaseSchema):
    """Base product schema."""
    name: str = Field(..., min_length=2, max_length=200, description="Product name")
    description: Optional[str] = Field(None, description="Full description")
    short_description: Optional[str] = Field(None, max_length=300, description="Short description")
    
    # Pricing
    base_price: Decimal = Field(..., gt=0, description="Base price in base_currency")
    compare_at_price: Optional[Decimal] = Field(
        None, 
        gt=0,  # base_price ile aynı mantık
        description="Compare at price (original price before discount)"
    )
    
    # Product type
    product_type: ProductType = ProductType.DIGITAL
    base_currency: Currency = Currency.USD

    
    # Category & Tags
    primary_category: Optional[str] = Field(None, max_length=50, description="Primary category")
    secondary_categories: Optional[List[str]] = Field(None, description="Secondary categories")
    tags: Optional[List[str]] = Field(None, description="Search tags")
    
    # SEO
    seo_title: Optional[str] = Field(None, max_length=70, description="SEO title")
    seo_description: Optional[str] = Field(None, max_length=160, description="SEO description")
    seo_keywords: Optional[str] = Field(None, max_length=200, description="SEO keywords")


class ProductCreate(ProductBase):
    """Create product schema."""
    shop_id: str = Field(..., description="Shop ID")
    slug: Optional[str] = Field(None, description="Product slug")
    file_url: Optional[HttpUrl] = Field(None, description="File URL for digital products")
    file_name: Optional[str] = Field(None, max_length=255, description="File name")
    file_type: Optional[FileType] = Field(None, description="File type")
    file_size: Optional[int] = Field(None, ge=1, description="File size in bytes")
    download_limit: int = Field(3, ge=1, le=100, description="Max downloads per purchase")
    access_duration_days: Optional[int] = Field(None, ge=1, le=3650, description="Access duration in days")
    watermark_enabled: bool = Field(False, description="Enable watermark for digital files")
    drm_enabled: bool = Field(False, description="Enable DRM protection")
    weight: Optional[Decimal] = Field(None, ge=0, le=1000, description="Weight in kg")
    dimensions: Optional[Dict[str, Any]] = Field(None, description="Dimensions {length, width, height}")
    requires_shipping: bool = Field(False)
    shipping_class: Optional[str] = Field(None, max_length=50, description="Shipping class")
    stock_quantity: int = Field(0, ge=0, description="Stock quantity")
    low_stock_threshold: int = Field(5, ge=0, description="Low stock threshold")
    allows_backorder: bool = Field(False, description="Allow backorders")
    sku: Optional[str] = Field(None, max_length=100, description="SKU")
    barcode: Optional[str] = Field(None, max_length=100, description="Barcode")
    feature_image_url: Optional[HttpUrl] = Field(None, description="Feature image URL")
    thumbnail_url: Optional[HttpUrl] = Field(None, description="Thumbnail URL")
    video_url: Optional[HttpUrl] = Field(None, description="Video URL")
    image_gallery: Optional[List[HttpUrl]] = Field(None, description="Image gallery URLs")
    fulfillment_type: FulfillmentType = FulfillmentType.AUTO
    processing_time_days: int = Field(1, ge=0, le=30, description="Processing time in days")
    digital_delivery_method: str = Field("instant", pattern="^(instant|manual|drip)$")
    is_on_sale: bool = Field(False, description="Is on sale")
    sale_starts_at: Optional[datetime] = Field(None, description="Sale start date")
    sale_ends_at: Optional[datetime] = Field(None, description="Sale end date")
    status: Optional[ProductStatus] = Field(
        None, 
        description="Product status (draft, published, archived)"
    )
    
    @field_validator("file_url")
    @classmethod
    def validate_file_url(cls, v, info):
        product_type = info.data.get("product_type")
        if product_type == ProductType.DIGITAL and v is None:
            raise ValueError("Digital products must have file_url")
        return v

   
    @validator('weight', always=True)
    def validate_weight(cls, v, values):
        """Fiziksel ürünlerde weight zorunlu"""
        product_type = values.get('product_type')
        if product_type == ProductType.PHYSICAL and v is None:
            raise ValueError('Physical products must have weight')
        return v
    
    @validator('requires_shipping', always=True)
    def validate_shipping(cls, v, values):
        product_type = values.get('product_type')
        if product_type == ProductType.DIGITAL:
            return False
        return v
    
    
    @validator("slug", always=True)
    def generate_slug(cls, v, values):
        if not v:
            name = values.get("name")
            if not name:
                raise ValueError("Slug could not be generated, please provide a name")
            return slugify(name)
        return v
    
    @field_validator('file_size')
    def fix_file_size_for_physical(cls, v, values):
        product_type = values.data.get('product_type')
        print(f"🔍 Validator: product_type={product_type}, gelen file_size={v}")  # <-- BUNU EKLE
        if product_type == ProductType.PHYSICAL:
            print("🔧 Fiziksel ürün, file_size -> None")
            return None
        print(f"🔧 file_size aynen: {v}")
        return v


    
    @validator('sale_ends_at')
    def validate_sale_dates(cls, v, values):
        """Sale tarihleri kontrolü"""
        if v and values.get('sale_starts_at'):
            if v <= values['sale_starts_at']:
                raise ValueError('sale_ends_at must be after sale_starts_at')
        return v

class ProductUpdate(BaseSchema):
    """Update product schema."""
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = None
    short_description: Optional[str] = Field(None, max_length=300)
    slug: Optional[str] = Field(None, description="Product slug")
    
    # Pricing
    base_price: Optional[Decimal] = Field(
        None, 
        gt=0,  # le=100000 KALDIRILDI
        description="Base price in base_currency"
    )
    compare_at_price: Optional[Decimal] = Field(
        None, 
        gt=0,  # le=100000 KALDIRILDI
        description="Compare at price (original price before discount)"
    )
    cost_per_item: Optional[Decimal] = Field(
        None, 
        ge=0,  # Maliyet 0 olabilir (dijital ürünlerde)
        description="Cost per item for profit calculation"
    )
    
    # Inventory
    stock_quantity: Optional[int] = Field(None, ge=0)
    low_stock_threshold: Optional[int] = Field(None, ge=0)
    allows_backorder: Optional[bool] = None
    sku: Optional[str] = Field(None, max_length=100)
    barcode: Optional[str] = Field(None, max_length=100)
    
    # Digital product updates
    download_limit: Optional[int] = Field(None, ge=1, le=100)
    access_duration_days: Optional[int] = Field(None, ge=1, le=3650)
    
    # Physical product updates
    weight: Optional[Decimal] = Field(None, ge=0, le=1000)
    dimensions: Optional[Dict[str, Any]] = None
    requires_shipping: Optional[bool] = None
    shipping_class: Optional[str] = Field(None, max_length=50)
    
    # Media updates
    feature_image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    video_url: Optional[str] = None
    image_gallery: Optional[List[str]] = None
    
    # SEO updates
    seo_title: Optional[str] = Field(None, max_length=70)
    seo_description: Optional[str] = Field(None, max_length=160)
    seo_keywords: Optional[str] = Field(None, max_length=200)
    
    # Status updates
    status: Optional[ProductStatus] = None
    is_featured: Optional[bool] = None
    is_best_seller: Optional[bool] = None
    is_new_arrival: Optional[bool] = None
    
    # Sale updates
    is_on_sale: Optional[bool] = None
    sale_starts_at: Optional[datetime] = None
    sale_ends_at: Optional[datetime] = None
    product_type: Optional[ProductType] = None  # EKLENEBİLİR
    base_currency: Optional[Currency] = None
       # EKLENEBİLİR
    file_type: Optional[FileType] = None        # EKLENEBİLİR
    fulfillment_type: Optional[FulfillmentType] = None
    
    @validator('file_type')
    def validate_file_type(cls, v, values):
        """Digital ürünlerde file_type gerekli"""
        product_type = values.get('product_type')
        if product_type == ProductType.DIGITAL and v is None:
            raise ValueError('Digital products must have file_type')
        return v


class ProductResponse(TimestampSchema):
    """Full product response."""
    id: UUID
    shop_id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    short_description: Optional[str] = None
    
    # Pricing
    base_price: Decimal
    base_currency: Currency
    compare_at_price: Optional[Decimal] = None
    cost_per_item: Optional[Decimal] = None
    prices: Optional[dict] = None
    display_currency: Optional[Currency] = None
    current_price: Optional[Decimal] = None
    is_on_sale: bool = False
    sale_starts_at: Optional[datetime] = None
    sale_ends_at: Optional[datetime] = None
    sale_price: Optional[Decimal] = None
    discount_percentage: Optional[int] = None
    product_type: ProductType
    stock_quantity: int = 0
    low_stock_threshold: int = 5
    allows_backorder: bool = False
    sku: Optional[str] = None
    barcode: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_type: Optional[FileType] = None
    file_size: Optional[int] = None
    download_limit: int = 3
    access_duration_days: Optional[int] = None
    watermark_enabled: bool = False
    drm_enabled: bool = False
    weight: Optional[Decimal] = None
    dimensions: Optional[Dict[str, Any]] = None
    requires_shipping: bool = True
    shipping_class: Optional[str] = None
    primary_category: Optional[str] = None
    secondary_categories: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    feature_image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    video_url: Optional[str] = None
    image_gallery: Optional[List[str]] = None
    
    # SEO & Visibility
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    seo_keywords: Optional[str] = None
    status: ProductStatus = ProductStatus.DRAFT
    is_featured: bool = False
    is_best_seller: bool = False
    is_new_arrival: bool = False
    requires_approval: bool = False
    is_approved: bool = False
    published_at: Optional[datetime] = None
    
    # Fulfillment
    fulfillment_type: FulfillmentType = FulfillmentType.AUTO
    processing_time_days: int = 1
    digital_delivery_method: str = "instant"
    
    # Statistics
    view_count: int = 0
    unique_view_count: int = 0
    purchase_count: int = 0
    wishlist_count: int = 0
    cart_add_count: int = 0
    average_rating: Decimal = Field(0.00, ge=0, le=5)
    review_count: int = 0
    refund_rate: Decimal = Field(0.00, ge=0, le=100)
    
    # Platform fees
    platform_fee_percent: Decimal = Field(0.00, ge=0, le=100)
    platform_fee_fixed: Decimal = Field(0.00, ge=0)
    payout_amount: Optional[Decimal] = None
    
    # Metadata
    meta_data: Dict[str, Any] = Field(default_factory=dict)
    
    # Timestamps
    last_sold_at: Optional[datetime] = None
    last_restocked_at: Optional[datetime] = None
    
    # Helper properties
    @property
    def is_available(self) -> bool:
        """Check if product is available for purchase."""
        return (
            self.status == ProductStatus.PUBLISHED and
            self.is_approved and
            not self.requires_approval
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
    def is_digital(self) -> bool:
        """Check if product is digital."""
        return self.product_type == ProductType.DIGITAL
    
    @property
    def is_physical(self) -> bool:
        """Check if product is physical."""
        return self.product_type == ProductType.PHYSICAL
    
    model_config = {
        "from_attributes": True,
        "populate_by_name": True
    }


class ProductPublic(BaseSchema):
    """Public product view (for marketplace)."""
    id: str
    shop_id: str
    shop_slug: Optional[str] = None
    shop_name: Optional[str] = None
    name: str
    slug: str
    short_description: Optional[str] = None
    display_currency: Currency
    current_price: Decimal
    base_currency: Currency

    is_on_sale: bool = False
    discount_percentage: Optional[int] = None
    product_type: ProductType
    is_in_stock: bool = True
    is_low_stock: bool = False
    stock_quantity: int = 0
    feature_image_url: Optional[str] = None
    image_gallery: Optional[List[str]] = None
    average_rating: float = 0.0
    review_count: int = 0
    purchase_count: int = 0
    is_featured: bool = False
    is_best_seller: bool = False
    is_new_arrival: bool = False
    primary_category: Optional[str] = None
    tags: Optional[List[str]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_digital: bool = False
    download_limit: Optional[int] = None
    access_duration_days: Optional[int] = None
    
    
    @validator('current_price', always=True)
    def validate_current_price(cls, v):
        """Current price 0'dan büyük olmalı"""
        if v <= 0:
            raise ValueError('Current price must be greater than 0')
        return v


class ProductSeller(ProductResponse):
    """Seller view of product."""
    shop_is_active: bool = True
    shop_subscription_status: Optional[str] = None
    variants_count: int = 0
    image_count: int = 0
    category_names: Optional[List[str]] = None
    # Pricin
    
    # Sales statistics
    daily_sales: Dict[str, int] = Field(default_factory=dict)
    monthly_revenue: Decimal = Field(0.00, ge=0)
    refund_count: int = 0
    refund_amount: Decimal = Field(0.00, ge=0)
    
    # Inventory alerts
    needs_restock: bool = False
    restock_quantity: Optional[int] = None


class ProductVariant(BaseSchema):
    """Product variant schema."""
    id: str
    product_id: str
    option1_name: Optional[str] = None
    option1_value: Optional[str] = None
    option2_name: Optional[str] = None
    option2_value: Optional[str] = None
    option3_name: Optional[str] = None
    option3_value: Optional[str] = None
    sku: Optional[str] = None
    price: Decimal
    compare_at_price: Optional[Decimal] = None
    cost_per_item: Optional[Decimal] = None
    stock_quantity: int = 0
    weight: Optional[Decimal] = None
    image_url: Optional[str] = None
    purchase_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None


class ProductSearchParams(PaginationParams):
    """Product search parameters."""
    search: Optional[str] = None
    shop_id: Optional[str] = None
    shop_slug: Optional[str] = None
    category: Optional[str] = None
    min_price: Optional[Decimal] = Field(None, ge=0)
    max_price: Optional[Decimal] = Field(None, ge=0)
    min_rating: Optional[float] = Field(None, ge=0, le=5)
    product_type: Optional[ProductType] = None
    is_digital: Optional[bool] = None
    in_stock_only: Optional[bool] = False
    is_featured: Optional[bool] = None
    is_best_seller: Optional[bool] = None
    is_new_arrival: Optional[bool] = None
    tags: Optional[List[str]] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    sort_by: Optional[str] = Field(
        None, 
        pattern="^(relevance|price_asc|price_desc|newest|popular|rating|sales|name_asc|name_desc)$"
    )


class ProductBulkUpdate(BaseSchema):
    """Bulk product update."""
    product_ids: List[str] = Field(..., min_items=1, max_items=100)
    action: str = Field(
        ...,
        pattern="^(publish|unpublish|feature|unfeature|archive|delete|update_price|update_stock|update_status|approve|reject)$"
    )
    data: Optional[Dict[str, Any]] = Field(None, description="Update data")
    reason: Optional[str] = Field(None, max_length=500)


class ProductImportRequest(BaseSchema):
    """Product import request."""
    file_url: HttpUrl
    file_type: str = Field("csv", pattern="^(csv|json|excel)$")
    import_mode: str = Field("create", pattern="^(create|update|upsert)$")
    mappings: Optional[Dict[str, str]] = Field(None, description="Field mappings")
    options: Optional[Dict[str, Any]] = Field(None, description="Import options")


class ProductExportRequest(BaseSchema):
    """Product export request."""
    format: str = Field("csv", pattern="^(csv|json|excel)$")
    fields: Optional[List[str]] = Field(None, description="Fields to export")
    filters: Optional[Dict[str, Any]] = Field(None, description="Export filters")
    include_variants: bool = Field(False, description="Include variants")
    include_images: bool = Field(False, description="Include image URLs")


class ProductDetailResponse(ProductResponse):
    """Product detail response with additional fields."""
    shop_name: Optional[str] = None
    shop_slug: Optional[str] = None
    shop_is_verified: bool = False
    shop_rating: float = 0.0
    shop_total_sales: int = 0
    similar_products: List[Dict[str, Any]] = Field(default_factory=list)
    variants: Optional[List[Dict[str, Any]]] = None
    downloadable_files: Optional[List[Dict[str, Any]]] = None
    related_accessories: List[Dict[str, Any]] = Field(default_factory=list)
    warranty_info: Optional[Dict[str, Any]] = None
    user_reviews: Optional[List[Dict[str, Any]]] = None
    questions_answers: Optional[List[Dict[str, Any]]] = None


class ProductAdminResponse(ProductResponse):
    """Admin view of product."""
    shop_is_active: bool = True
    shop_subscription_status: Optional[str] = None
    variants_count: int = 0
    image_count: int = 0
    category_names: Optional[List[str]] = None
    daily_sales: Dict[str, int] = Field(default_factory=dict)
    monthly_revenue: Decimal = Field(0.00, ge=0)
    refund_count: int = 0
    refund_amount: Decimal = Field(0.00, ge=0)
    needs_restock: bool = False
    restock_quantity: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="meta_data")
    ai_generated_score: Optional[float] = None
    content_moderation_status: str = "pending"
    moderation_notes: Optional[str] = None
    moderated_by: Optional[str] = None
    moderated_at: Optional[datetime] = None
    