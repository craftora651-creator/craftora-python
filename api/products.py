"""
Product management API endpoints
Create, update, delete products, manage inventory, pricing
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_, or_, case
from sqlalchemy.orm import joinedload, selectinload
from datetime import timedelta
import httpx
from sqlalchemy import update
from models.product import FileType, FulfillmentType 
from database.database import get_db
from helpers.security import get_current_user_clean , get_current_verified_user
from nix.dependencies import (
    PaginationParams, 
    FileUploadValidator,
    BulkOperationValidator,
    require_admin
)
from nix.exceptions import (
    NotFoundException,
    ValidationException,
    ForbiddenException,
    ResourceExistsException,
    InsufficientStockException
)
from nix.logging import logger, audit_logger, performance_logger
from config.config import settings
import uuid
from models.product import Product, ProductStatus, ProductType, Currency
from models.shop import Shop, ShopStatus
from models.user import User
from routers.products import (
    ProductCreate, 
    ProductUpdate, 
    ProductResponse, 
    ProductDetailResponse,
    ProductAdminResponse,
    ProductSearchParams,
    ProductBulkUpdate,
)
from sqlalchemy import cast, UUID
from sqlalchemy import cast
from sqlalchemy.dialects.postgresql import ENUM
from models.product import ProductType, Currency
import uuid
from decimal import Decimal
from sqlalchemy import update
from slugify import slugify

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["products"])

# ==================== PRODUCT CREATION & BASIC CRUD ====================

@router.post("/", response_model=ProductResponse)
async def create_product(
    product_data: ProductCreate,
    current_user: dict = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    print(f"📥 Gelen product_data: {product_data}")
    print(f"💰 base_price: {product_data.base_price}")
    print(f"🏷️ compare_at_price: {product_data.compare_at_price}")
    print(f"📥 Gelen product_data.compare_at_price: {product_data.compare_at_price}")
    try:
        result = await db.execute(
            select(Shop).where(
                Shop.id == product_data.shop_id,
                Shop.user_id == uuid.UUID(current_user["sub"]),
            )
        )
        shop = result.scalar_one_or_none()
        if not shop:
            raise ForbiddenException(
                detail="Shop not found, not active, or you don't have permission"
            )
        data = product_data.model_dump(mode="json", exclude_unset=True)
        product_status = data.get("status", ProductStatus.DRAFT.value)
        print(f"🎯 Gelen status: {data.get('status')}")
        print(f"🎯 Kullanılacak status: {product_status}")
        if "fulfillment_type" not in data or data["fulfillment_type"] is None:
            data["fulfillment_type"] = "manual"  # veya "auto" hangisi uygunsa
        base_slug = slugify(data.get("slug", data["name"]))
        slug = base_slug
        counter = 1
        while True:
            result = await db.execute(
                select(Product).where(
                    Product.shop_id == shop.id,
                    Product.slug == slug
                )
            )
            if not result.scalar_one_or_none():
                break
            slug = f"{base_slug}-{counter}"
            counter += 1
        data["slug"] = slug
        product = Product(
            **data,
            requires_approval=False,
            is_approved=True,
            published_at=datetime.utcnow() if data.get("status") == ProductStatus.PUBLISHED.value else None
        )
        db.add(product)
        await db.commit()
        await db.refresh(product)
        await db.execute(
            update(Shop)
            .where(Shop.id == shop.id)
            .values(total_products=Shop.total_products + 1)
        )
        await db.commit()
        try:
            if audit_logger:
                audit_logger.log_user_login(
                    user_id=current_user["sub"],
                    user_email=current_user["email"],
                    method="product_creation",
                    ip_address="127.0.0.1",
                    user_agent="api",
                    success=True,
                    failure_reason=None
                )
        except Exception as e:
            logger.warning(f"Audit logging failed: {e}")
        logger.info(f"Product created: {product.name} in shop {shop.shop_name}")
        logger.info("=" * 50)
        logger.info("🔍 PRODUCT CREATED - CHECKING RESPONSE")
        logger.info(f"📌 Product ID: {product.id}")
        logger.info(f"📌 Product name: {product.name}")
        logger.info(f"📌 Product type: {type(product)}")
        logger.info(f"📌 Product __dict__: {product.__dict__}")
        try:
            response = ProductResponse.from_orm(product)
            logger.info(f"✅ Response oluşturuldu: {type(response)}")
            logger.info(f"✅ Response ID: {response.id}")
            logger.info(f"✅ Response status: {response.status}")
            logger.info(f"✅ Response dict: {response.model_dump()}")
            logger.info("=" * 50)
            return response
        except Exception as e:
            logger.error(f"❌ Response hatası: {e}")
            logger.exception("Detaylı hata:")
            raise
    except ForbiddenException:
        raise
    except Exception as e:
        await db.rollback()
        logger.exception("Error creating product")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e) 
        )

@router.get("/my", response_model=List[ProductResponse])
async def get_my_products(
    shop_id: Optional[str] = Query(None),
    status: Optional[ProductStatus] = Query(None),
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    try:
        # Convert user ID to UUID
        user_id_uuid = uuid.UUID(current_user["sub"])
        
        # Get user's shops
        result = await db.execute(
            select(Shop).where(Shop.user_id == user_id_uuid)
        )
        user_shops = result.scalars().all()
        
        if not user_shops:
            return []
        
        shop_ids = [shop.id for shop in user_shops]
        
        # Build query
        query = select(Product).where(Product.shop_id.in_(shop_ids))
        
        # 🔴 YENİ: Silinmiş ürünleri gösterme!
        query = query.where(Product.status != ProductStatus.DELETED.value)
        
        if shop_id:
            shop_id_uuid = uuid.UUID(shop_id)
            if shop_id_uuid not in shop_ids:
                raise ForbiddenException(detail="You don't own this shop")
            query = query.where(Product.shop_id == shop_id_uuid)

        if status:
            query = query.where(Product.status == status.value)
        
        query = query.order_by(Product.created_at.desc())
        
        result = await db.execute(query)
        products = result.scalars().all()
        
        return [ProductResponse.from_orm(product) for product in products]
        
    except Exception as e:
        logger.error(f"Error getting user products: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve your products"
        )


@router.get("/shop/{shop_id}", response_model=List[ProductDetailResponse])
async def get_shop_products(
    shop_id: str,
    category: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Get products for a specific shop (public endpoint).
    Only shows published and approved products.
    """
    try:
        shop_id_uuid = uuid.UUID(shop_id)
        result = await db.execute(
            select(Shop).where(
                Shop.id == shop_id_uuid,
                Shop.status == ShopStatus.ACTIVE,
            )
        )
        shop = result.scalar_one_or_none()
        if not shop:
            raise NotFoundException(
                resource_type="Shop",
                identifier=shop_id,
                detail="Shop not found or not active"
            )
        
        query = select(Product).where(
            Product.shop_id == shop.id,
            Product.status == ProductStatus.PUBLISHED.value,  # String
            Product.is_approved.is_(True)
        )
        
        if category:
            query = query.where(Product.primary_category == category)
        if min_price is not None:
            query = query.where(Product.base_price >= Decimal(str(min_price)))
        if max_price is not None:
            query = query.where(Product.base_price <= Decimal(str(max_price)))
        
        query = query.order_by(
            Product.is_featured.desc(),
            Product.is_best_seller.desc(),
            Product.created_at.desc()
        )
        
        result = await db.execute(query)
        products = result.scalars().all()
        
        return [ProductDetailResponse.from_orm(product) for product in products]
        
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid shop ID format"
        )
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error getting shop products: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve shop products"
        )


@router.get("/{product_id}", response_model=ProductDetailResponse)
async def get_product(
    product_id: str,
    current_user: dict = Depends(get_current_user_clean),  # Artık zorunlu değil
    db: AsyncSession = Depends(get_db)
):
    """
    Get product details by ID.
    - Public: Sadece PUBLISHED ve onaylı ürünleri gösterir
    - Seller: Kendi ürünlerini (draft dahil) görebilir
    """
    try:
        product_id_uuid = uuid.UUID(product_id)
        
        # Önce ürünü bul (hiçbir filtre olmadan)
        result = await db.execute(
            select(Product).where(
                Product.id == product_id_uuid
            ).options(
                joinedload(Product.shop)
            )
        )
        product = result.scalar_one_or_none()
        
        if not product:
            raise NotFoundException(
                resource_type="Product",
                identifier=product_id
            )
        
        # Yetki kontrolü:
        # - Eğer kullanıcı giriş yapmamışsa: sadece PUBLISHED ve onaylı ürünleri görebilir
        # - Eğer kullanıcı giriş yapmışsa: kendi ürünlerini görebilir, başkasınınkini göremez
        
        is_owner = False
        if current_user and current_user.get("sub"):
            # Kullanıcının bu ürünün sahibi olup olmadığını kontrol et
            result = await db.execute(
                select(Shop).where(
                    Shop.id == product.shop_id,
                    Shop.user_id == current_user["sub"]
                )
            )
            shop = result.scalar_one_or_none()
            is_owner = shop is not None
        
        if not is_owner:
            # Sahibi değilse, sadece PUBLISHED ve onaylı ürünleri görebilir
            if product.status != ProductStatus.PUBLISHED.value or not product.is_approved:
                raise NotFoundException(
                    resource_type="Product",
                    identifier=product_id
                )
            
            # View count'u artır (sadece public görüntülemelerde)
            await db.execute(
                update(Product)
                .where(Product.id == product.id)
                .values(view_count=Product.view_count + 1)
            )
            await db.commit()
        
        return ProductDetailResponse.from_orm(product)
        
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid product ID format"
        )
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error getting product: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve product"
        )


@router.get("/slug/{slug}", response_model=ProductDetailResponse)
async def get_product_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get product by slug (public endpoint).
    """
    try:
        result = await db.execute(
            select(Product).where(
                Product.slug == slug,
                Product.status == ProductStatus.PUBLISHED.value,  # String
                Product.is_approved.is_(True)
            ).options(
                joinedload(Product.shop)
            )
        )
        product = result.scalar_one_or_none()
        
        if not product:
            raise NotFoundException(
                resource_type="Product",
                identifier=slug
            )
        
        # Increment view count
        await db.execute(
            update(Product)
            .where(Product.id == product.id)
            .values(view_count=Product.view_count + 1)
        )
        await db.commit()
        
        return ProductDetailResponse.from_orm(product)
        
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error getting product by slug: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve product"
        )


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    product_data: ProductUpdate,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Update product details (owner only).
    """
    try:
        product_id_uuid = uuid.UUID(product_id)
        
        result = await db.execute(
            select(Product).where(
                Product.id == product_id_uuid,
                Product.shop.has(user_id=current_user["sub"])
            ).options(
                joinedload(Product.shop)
            )
        )
        product = result.scalar_one_or_none()
        
        if not product:
            raise ForbiddenException(
                detail="You don't have permission to update this product"
            )
        
        if product.status == ProductStatus.DELETED.value:  # String
            raise ValidationException(
                detail="Cannot update deleted product"
            )
        
        update_data = product_data.dict(exclude_unset=True)
        
        # Restricted fields
        restricted_fields = {"shop_id", "is_approved", "published_at"}
        for field in restricted_fields:
            update_data.pop(field, None)
        
        # Slug uniqueness check
        if "slug" in update_data and update_data["slug"] != product.slug:
            result = await db.execute(
                select(Product).where(
                    Product.shop_id == product.shop_id,
                    Product.slug == update_data["slug"],
                    Product.id != product_id_uuid
                )
            )
            existing_product = result.scalar_one_or_none()
            if existing_product:
                raise ResourceExistsException(
                    resource_type="Product",
                    identifier=update_data["slug"],
                    detail="Product with this slug already exists in your shop"
                )
        
        # Apply updates
        for field, value in update_data.items():
            setattr(product, field, value)
        
        await db.commit()
        await db.refresh(product)
        
        logger.info(f"Product updated: {product.name} by {current_user['email']}")
        
        return ProductResponse.from_orm(product)
        
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid product ID format"
        )
    except (ForbiddenException, ValidationException, ResourceExistsException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating product: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    permanent: bool = Query(False, description="Permanently delete (admin only)"),
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete product (soft delete by default, permanent delete for admin).
    """
    try:
        product_id_uuid = uuid.UUID(product_id)
        
        result = await db.execute(
            select(Product).options(
                joinedload(Product.shop)
            ).where(
                Product.id == product_id_uuid
            )
        )
        product = result.scalar_one_or_none()
        
        if not product:
            raise NotFoundException(
                resource_type="Product",
                identifier=product_id
            )
        
        user_id_uuid = uuid.UUID(current_user["sub"])
        is_owner = product.shop.user_id == user_id_uuid
        is_admin = current_user.get("role") == "admin"
        
        if not (is_owner or is_admin):
            raise ForbiddenException(
                detail="You don't have permission to delete this product"
            )
        
        if product.status == ProductStatus.DELETED.value and not permanent:
            return {
                "message": "Product already deleted",
                "product_id": product_id,
                "permanent": False
            }
        
        if permanent:
            if not is_admin:
                raise ForbiddenException(
                    detail="Only admin can permanently delete products"
                )
            await db.delete(product)
            message = "Product permanently deleted"
        else:
            product.status = ProductStatus.DELETED.value  # String
            await db.execute(
                update(Shop)
                .where(Shop.id == product.shop_id)
                .where(Shop.total_products > 0)
                .values(total_products=Shop.total_products - 1)
            )
            message = "Product deleted (soft delete)"
        
        await db.commit()
        
        logger.warning(
            f"Product deleted: {product.name} by {current_user['email']}, permanent: {permanent}"
        )
        
        return {
            "message": message,
            "product_id": product_id,
            "product_name": product.name,
            "permanent": permanent and is_admin,
            "deleted_by": current_user["email"]
        }
        
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid product ID format"
        )
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting product: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete product"
        )
    

# ==================== PRODUCT STATUS MANAGEMENT ====================

@router.post("/{product_id}/publish")
async def publish_product(
    product_id: str,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Publish product (change status from DRAFT to PUBLISHED).
    """
    try:
        product_id_uuid = uuid.UUID(product_id)

        result = await db.execute(
            select(Product).where(
                Product.id == product_id_uuid,
                Product.shop.has(user_id=current_user["sub"])
            ).options(
                joinedload(Product.shop)
            )
        )
        product = result.scalar_one_or_none()

        if not product:
            raise ForbiddenException(
                detail="You don't have permission to publish this product"
            )

        # Shop must be active
        if product.shop.status != ShopStatus.ACTIVE.value:  # String
            raise ValidationException(
                detail="Cannot publish product from inactive shop"
            )

        if product.status == ProductStatus.DELETED.value:  # String
            raise ValidationException(
                detail="Cannot publish deleted product"
            )

        if product.status == ProductStatus.PUBLISHED.value:  # String
            raise ValidationException(
                detail="Product is already published"
            )

        if product.status != ProductStatus.DRAFT.value:  # String
            raise ValidationException(
                detail=f"Cannot publish product with status: {product.status}"
            )

        # Minimum validation
        if not product.name or not product.base_price or product.base_price <= 0:
            raise ValidationException(
                detail="Product must have valid name and price to publish"
            )
        
        if product.product_type == ProductType.DIGITAL.value and not product.file_url:
            raise ValidationException(
                detail="Digital products must have a file URL"
            )
        
        product.status = ProductStatus.PUBLISHED.value  # String
        product.published_at = datetime.utcnow()
        
        if not product.requires_approval:
            product.is_approved = True
        
        await db.commit()
        await db.refresh(product)
        
        logger.info(f"Product published: {product.name} by {current_user['email']}")
        
        return {
            "message": "Product published successfully",
            "product_id": product_id,
            "product_name": product.name,
            "status": product.status,
            "requires_approval": product.requires_approval,
            "is_approved": product.is_approved
        }
        
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid product ID format"
        )
    except (ForbiddenException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error publishing product: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not publish product"
        )


@router.post("/{product_id}/archive")
async def archive_product(
    product_id: str,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Archive product (hide from public view).
    """
    try:
        product_id_uuid = uuid.UUID(product_id)

        result = await db.execute(
            select(Product).where(
                Product.id == product_id_uuid,
                Product.shop.has(user_id=current_user["sub"])
            )
        )
        product = result.scalar_one_or_none()

        if not product:
            raise ForbiddenException(
                detail="You don't have permission to archive this product"
            )

        if product.status == ProductStatus.DELETED.value:  # String
            raise ValidationException(
                detail="Cannot archive deleted product"
            )

        if product.status == ProductStatus.ARCHIVED.value:  # String
            return {
                "message": "Product already archived",
                "product_id": product_id,
                "status": "archived"
            }

        if product.status != ProductStatus.PUBLISHED.value:  # String
            raise ValidationException(
                detail=f"Cannot archive product with status: {product.status}"
            )

        product.status = ProductStatus.ARCHIVED.value  # String
        await db.commit()

        logger.info(f"Product archived: {product.name} by {current_user['email']}")

        return {
            "message": "Product archived successfully",
            "product_id": product_id,
            "product_name": product.name,
            "status": product.status
        }

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid product ID format"
        )
    except (ForbiddenException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error archiving product: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not archive product"
        )


@router.post("/{product_id}/restore")
async def restore_product(
    product_id: str,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Restore archived product.
    """
    try:
        product_id_uuid = uuid.UUID(product_id)

        result = await db.execute(
            select(Product).where(
                Product.id == product_id_uuid,
                Product.shop.has(user_id=current_user["sub"])
            ).options(
                joinedload(Product.shop)
            )
        )
        product = result.scalar_one_or_none()

        if not product:
            raise ForbiddenException(
                detail="You don't have permission to restore this product"
            )

        if product.status == ProductStatus.DELETED.value:  # String
            raise ValidationException(
                detail="Cannot restore deleted product"
            )

        if product.status == ProductStatus.PUBLISHED.value:  # String
            return {
                "message": "Product already published",
                "product_id": product_id,
                "status": "published"
            }

        if product.status != ProductStatus.ARCHIVED.value:  # String
            raise ValidationException(
                detail=f"Cannot restore product with status: {product.status}"
            )

        # Shop must be active
        if product.shop.status != ShopStatus.ACTIVE.value:  # String
            raise ValidationException(
                detail="Cannot restore product from inactive shop"
            )

        # Restore logic
        product.status = ProductStatus.PUBLISHED.value  # String
        product.published_at = datetime.utcnow()

        # If approval required and not approved, don't auto-publish
        if product.requires_approval and not product.is_approved:
            product.status = ProductStatus.DRAFT.value  # String

        await db.commit()

        logger.info(f"Product restored: {product.name} by {current_user['email']}")

        return {
            "message": "Product restored successfully",
            "product_id": product_id,
            "product_name": product.name,
            "status": product.status
        }

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid product ID format"
        )
    except (ForbiddenException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error restoring product: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not restore product"
        )


# ==================== INVENTORY MANAGEMENT ====================

@router.post("/{product_id}/inventory/update")
async def update_inventory(
    product_id: str,
    quantity_change: int,
    reason: str = Form("manual_update"),
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Update product inventory (add or remove stock).
    """
    try:
        if quantity_change == 0:
            raise ValidationException(
                detail="Quantity change cannot be zero"
            )

        product_id_uuid = uuid.UUID(product_id)
        user_id_uuid = uuid.UUID(current_user["sub"])

        # Atomic stock update
        result = await db.execute(
            update(Product)
            .where(
                Product.id == product_id_uuid,
                Product.product_type == ProductType.PHYSICAL.value,  # String
                Product.shop.has(user_id=user_id_uuid),
                Product.stock_quantity + quantity_change >= 0
            )
            .values(
                stock_quantity=Product.stock_quantity + quantity_change,
                last_restocked_at=datetime.utcnow() if quantity_change > 0 else Product.last_restocked_at
            )
            .returning(Product.id, Product.stock_quantity, Product.name)
        )

        updated = result.first()

        if not updated:
            raise ValidationException(
                detail="Inventory update failed (invalid product, permission, or insufficient stock)"
            )

        await db.commit()

        product_id_db, new_quantity, product_name = updated

        logger.info(
            f"Inventory updated: {product_name}, change: {quantity_change}, reason: {reason}"
        )

        return {
            "message": "Inventory updated successfully",
            "product_id": str(product_id_db),
            "product_name": product_name,
            "new_quantity": new_quantity,
            "change": quantity_change,
            "reason": reason,
            "is_low_stock": new_quantity <= 5  # or your threshold
        }

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid product ID format"
        )
    except (ForbiddenException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating inventory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update inventory"
        )


@router.get("/{product_id}/inventory")
async def get_inventory(
    product_id: str,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Get product inventory details.
    """
    try:
        product_id_uuid = uuid.UUID(product_id)

        result = await db.execute(
            select(Product)
            .options(
                selectinload(Product.shop)
            )
            .where(
                Product.id == product_id_uuid,
                Product.shop.has(user_id=current_user["sub"])
            )
        )
        product = result.scalar_one_or_none()

        if not product:
            raise ForbiddenException(
                detail="You don't have permission to view inventory"
            )

        if product.product_type != ProductType.PHYSICAL.value:  # String
            raise ValidationException(
                detail="Inventory is only available for physical products"
            )

        return {
            "product_id": str(product.id),
            "product_name": product.name,
            "product_type": product.product_type,
            "stock_quantity": product.stock_quantity,
            "low_stock_threshold": product.low_stock_threshold,
            "is_in_stock": product.stock_quantity > 0,
            "is_low_stock": product.stock_quantity <= product.low_stock_threshold,
            "allows_backorder": product.allows_backorder,
            "last_restocked_at": product.last_restocked_at.isoformat() if product.last_restocked_at else None,
            "last_sold_at": product.last_sold_at.isoformat() if product.last_sold_at else None,
            "purchase_count": product.purchase_count,
            "cart_add_count": product.cart_add_count
        }

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid product ID format"
        )
    except (ForbiddenException, ValidationException):
        raise
    except Exception as e:
        logger.error(f"Error getting inventory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve inventory"
        )


# ==================== PRICING & DISCOUNTS ====================

@router.post("/{product_id}/discount")
async def set_discount(
    product_id: str,
    discount_percent: float = Form(..., gt=0, lt=100),
    starts_at: Optional[datetime] = Form(None),
    ends_at: Optional[datetime] = Form(None),
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Set discount for product.
    """
    try:
        product_id_uuid = uuid.UUID(product_id)

        if starts_at and ends_at and ends_at <= starts_at:
            raise ValidationException(
                detail="End date must be after start date"
            )

        result = await db.execute(
            select(Product).where(
                Product.id == product_id_uuid,
                Product.shop.has(user_id=current_user["sub"])
            )
        )
        product = result.scalar_one_or_none()

        if not product:
            raise ForbiddenException(
                detail="You don't have permission to set discount"
            )

        if product.status != ProductStatus.PUBLISHED.value:  # String
            raise ValidationException(
                detail="Discount can only be applied to published products"
            )

        # Calculate discounted price
        discount_decimal = Decimal(str(discount_percent)) / Decimal("100")
        discounted_price = product.base_price * (Decimal("1") - discount_decimal)

        if discounted_price <= 0:
            raise ValidationException(
                detail="Discount results in invalid price"
            )

        # Preserve original price
        if not product.compare_at_price:
            product.compare_at_price = product.base_price

        product.is_on_sale = True
        product.sale_starts_at = starts_at
        product.sale_ends_at = ends_at

        await db.commit()
        await db.refresh(product)

        logger.info(
            f"Discount set: {product.name} {discount_percent}% by {current_user['email']}"
        )

        return {
            "message": "Discount set successfully",
            "product_id": product_id,
            "product_name": product.name,
            "base_price": float(product.base_price),
            "discount_percent": discount_percent,
            "is_on_sale": product.is_on_sale,
            "sale_starts_at": product.sale_starts_at.isoformat() if product.sale_starts_at else None,
            "sale_ends_at": product.sale_ends_at.isoformat() if product.sale_ends_at else None
        }

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid product ID format"
        )
    except (ForbiddenException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error setting discount: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not set discount"
        )


@router.post("/{product_id}/discount/remove")
async def remove_discount(
    product_id: str,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Remove discount from product.
    """
    try:
        product_id_uuid = uuid.UUID(product_id)

        result = await db.execute(
            select(Product).where(
                Product.id == product_id_uuid,
                Product.shop.has(user_id=current_user["sub"])
            )
        )
        product = result.scalar_one_or_none()

        if not product:
            raise ForbiddenException(
                detail="You don't have permission to remove discount"
            )

        if not product.is_on_sale:
            return {
                "message": "Product is not on sale",
                "product_id": str(product.id),
                "product_name": product.name,
                "is_on_sale": False
            }

        # Reset pricing fields
        product.is_on_sale = False
        product.sale_starts_at = None
        product.sale_ends_at = None

        await db.commit()
        await db.refresh(product)

        logger.info(f"Discount removed: {product.name} by {current_user['email']}")

        return {
            "message": "Discount removed successfully",
            "product_id": str(product.id),
            "product_name": product.name,
            "is_on_sale": False
        }

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid product ID format"
        )
    except ForbiddenException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error removing discount: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not remove discount"
        )


# ==================== IMAGE UPLOAD ====================

MAX_IMAGES_PER_UPLOAD = 10

@router.post("/{product_id}/images")
async def upload_product_images(
    product_id: str,
    files: List[UploadFile] = File(...),
    set_as_featured: Optional[int] = Form(None),
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db),
    file_validator: FileUploadValidator = Depends(
        FileUploadValidator(
            max_size_mb=10,
            allowed_types=["image/jpeg", "image/png", "image/webp", "image/gif"]
        )
    )
):
    """
    Upload product images.
    """
    try:
        import os
        import aiofiles
        from pathlib import Path
        
        product_id_uuid = uuid.UUID(product_id)

        if len(files) > MAX_IMAGES_PER_UPLOAD:
            raise ValidationException(
                detail=f"Maximum {MAX_IMAGES_PER_UPLOAD} images allowed per upload"
            )

        result = await db.execute(
            select(Product).where(
                Product.id == product_id_uuid,
                Product.shop.has(user_id=current_user["sub"])
            )
        )
        product = result.scalar_one_or_none()

        if not product:
            raise ForbiddenException(
                detail="You don't have permission to upload images"
            )

        # Upload klasörünü oluştur
        upload_dir = Path(f"uploads/products/{product_id_uuid}")
        upload_dir.mkdir(parents=True, exist_ok=True)

        image_urls = []

        for i, file in enumerate(files):
            await file_validator(file)

            # Dosya uzantısını al
            extension = file.filename.split(".")[-1]
            secure_filename = f"{uuid.uuid4()}.{extension}"
            file_path = upload_dir / secure_filename
            
            # DOSYAYI KAYDET (İŞTE BURASI ÖNEMLİ!)
            async with aiofiles.open(file_path, 'wb') as out_file:
                content = await file.read()
                await out_file.write(content)
            
            # URL oluştur
            image_url = f"/uploads/products/{product_id_uuid}/{secure_filename}"
            image_urls.append(image_url)

        # Validate featured index
        if set_as_featured is not None:
            if set_as_featured < 0 or set_as_featured >= len(image_urls):
                raise ValidationException(
                    detail="Invalid featured image index"
                )
            product.feature_image_url = image_urls[set_as_featured]

        # Update gallery safely
        product.image_gallery = (product.image_gallery or []) + image_urls

        await db.commit()
        await db.refresh(product)

        logger.info(f"Product images uploaded: {product.name}, {len(files)} images")

        return {
            "message": f"{len(files)} images uploaded successfully",
            "product_id": str(product.id),
            "product_name": product.name,
            "feature_image_url": product.feature_image_url,
            "image_gallery": product.image_gallery,
        }

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid product ID format"
        )
    except (ForbiddenException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error uploading product images: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not upload images: {str(e)}"
        )

# ==================== BULK OPERATIONS ====================

ALLOWED_BULK_FIELDS = {
    "base_price",
    "low_stock_threshold",
    "allows_backorder"
}

@router.post("/bulk/update")
async def bulk_update_products(
    updates: ProductBulkUpdate,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db),
    bulk_validator: BulkOperationValidator = Depends(
        BulkOperationValidator(max_items=50)
    )
):
    """
    Bulk update products safely.
    """
    try:
        await bulk_validator(updates.product_ids)

        # Parse UUIDs safely
        try:
            parsed_ids = [uuid.UUID(pid) for pid in updates.product_ids]
        except ValueError:
            raise ValidationException(detail="Invalid product ID format")

        # Get allowed update data only
        raw_update_data = updates.dict(exclude_unset=True, exclude={"product_ids"})
        update_data = {
            k: v for k, v in raw_update_data.items()
            if k in ALLOWED_BULK_FIELDS
        }

        if not update_data:
            raise ValidationException(detail="No valid fields to update")

        # Fetch products owned by user
        result = await db.execute(
            select(Product).where(
                Product.id.in_(parsed_ids),
                Product.shop.has(user_id=current_user["sub"])
            )
        )
        products = result.scalars().all()

        if len(products) != len(parsed_ids):
            raise ForbiddenException(
                detail="Some products don't exist or you don't have permission"
            )

        # Apply updates
        for product in products:
            for field, value in update_data.items():
                setattr(product, field, value)

        await db.commit()

        logger.info(
            f"Bulk update: {len(products)} products updated "
            f"by {current_user['email']}, fields={list(update_data.keys())}"
        )

        return {
            "message": f"Successfully updated {len(products)} products",
            "updated_count": len(products),
            "fields_updated": list(update_data.keys())
        }

    except (ForbiddenException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error bulk updating products: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not bulk update products"
        )


# ==================== PUBLIC MARKETPLACE ENDPOINTS ====================

MAX_LIMIT = 50
MIN_SEARCH_LENGTH = 2


@router.get("/public/search")
async def search_products(
    pagination: PaginationParams = Depends(),
    search: ProductSearchParams = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Public marketplace product search (production-ready).
    """
    try:
        start_time = datetime.utcnow()

        # Limit guard
        limit = min(pagination.limit, MAX_LIMIT)
        offset = max(pagination.offset, 0)

        # Base query
        base_query = select(Product).where(
            Product.status == ProductStatus.PUBLISHED.value,  # String
            Product.is_approved.is_(True),
            Product.shop.has(
                status=ShopStatus.ACTIVE.value,  # String
                is_approved=True
            )
        )

        # --------------------
        # FILTERS
        # --------------------

        if search.q:
            q = search.q.strip()

            if len(q) < MIN_SEARCH_LENGTH:
                raise ValidationException(
                    detail=f"Search query must be at least {MIN_SEARCH_LENGTH} characters"
                )

            base_query = base_query.where(
                or_(
                    Product.name.ilike(f"%{q}%"),
                    Product.short_description.ilike(f"%{q}%")
                )
            )

        if search.category:
            base_query = base_query.where(
                Product.primary_category == search.category
            )

        if search.product_type:
            base_query = base_query.where(
                Product.product_type == search.product_type.value  # String
            )

        if search.shop_id:
            base_query = base_query.where(
                Product.shop_id == search.shop_id
            )

        if search.is_featured:
            base_query = base_query.where(Product.is_featured.is_(True))

        if search.is_best_seller:
            base_query = base_query.where(Product.is_best_seller.is_(True))

        if search.is_new_arrival:
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            base_query = base_query.where(
                Product.created_at >= thirty_days_ago
            )

        # Price validation
        if (
            search.min_price is not None and
            search.max_price is not None and
            search.min_price > search.max_price
        ):
            raise ValidationException(
                detail="min_price cannot be greater than max_price"
            )

        if search.min_price is not None:
            base_query = base_query.where(
                Product.base_price >= Decimal(str(search.min_price))
            )

        if search.max_price is not None:
            base_query = base_query.where(
                Product.base_price <= Decimal(str(search.max_price))
            )

        # --------------------
        # COUNT QUERY
        # --------------------

        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await db.execute(count_query)
        total_count = total_result.scalar() or 0

        # --------------------
        # SORTING
        # --------------------

        if search.sort_by == "price":
            sort_column = Product.base_price
        elif search.sort_by == "date":
            sort_column = Product.created_at
        elif search.sort_by == "popularity":
            sort_column = Product.purchase_count
        elif search.sort_by == "rating":
            sort_column = func.coalesce(Product.average_rating, 0)
        else:
            sort_column = None

        query = base_query.options(
            joinedload(Product.shop)
        )

        if sort_column is not None:
            if search.sort_order == "asc":
                query = query.order_by(sort_column.asc())
            else:
                query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(
                Product.is_featured.desc(),
                Product.created_at.desc()
            )

        # --------------------
        # PAGINATION
        # --------------------

        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        products = result.scalars().all()

        # --------------------
        # PERFORMANCE LOG
        # --------------------

        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        performance_logger.log_database_query(
            query="search_products",
            duration_ms=duration_ms,
            rows_returned=len(products),
            user_id=None,
            shop_id=None
        )

        # --------------------
        # RESPONSE
        # --------------------

        return {
            "items": [ProductDetailResponse.from_orm(p) for p in products],
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total_count
        }

    except ValidationException:
        raise
    except Exception as e:
        logger.error(f"Error searching products: {e}")
        raise HTTPException(
            status_code=500,
            detail="Could not search products"
        )


@router.get("/public/categories")
async def get_product_categories(
    db: AsyncSession = Depends(get_db)
):
    """
    Get product categories with product counts (public endpoint).
    """
    try:
        # Hardcoded categories (MVP)
        base_categories = [
            {"id": "digital-art", "name": "Digital Art"},
            {"id": "templates", "name": "Templates"},
            {"id": "ebooks", "name": "E-books"},
            {"id": "courses", "name": "Courses"},
            {"id": "software", "name": "Software"},
            {"id": "music", "name": "Music"},
            {"id": "photography", "name": "Photography"},
            {"id": "3d-models", "name": "3D Models"},
        ]

        # Single grouped query
        result = await db.execute(
            select(
                Product.primary_category,
                func.count(Product.id)
            ).where(
                Product.status == ProductStatus.PUBLISHED.value,  # String
                Product.is_approved.is_(True),
                Product.shop.has(
                    status=ShopStatus.ACTIVE.value,  # String
                    is_approved=True
                )
            ).group_by(Product.primary_category)
        )

        counts = {row[0]: row[1] for row in result.all() if row[0]}

        # Merge counts with base categories
        categories = []
        for category in base_categories:
            categories.append({
                "id": category["id"],
                "name": category["name"],
                "product_count": counts.get(category["id"], 0)
            })

        return categories

    except Exception as e:
        logger.error(f"Error getting categories: {e}")
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve categories"
        )


# ==================== ADMIN ENDPOINTS ====================

MAX_ADMIN_LIMIT = 100

ALLOWED_ADMIN_SORT_FIELDS = {
    "created_at": Product.created_at,
    "base_price": Product.base_price,
    "purchase_count": Product.purchase_count,
    "average_rating": Product.average_rating,
    "status": Product.status
}


@router.get("/admin/list")
async def list_products_admin(
    pagination: PaginationParams = Depends(),
    search: ProductSearchParams = Depends(),
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin: List all products with filters and metadata.
    """
    try:
        limit = min(pagination.limit, MAX_ADMIN_LIMIT)
        offset = max(pagination.offset, 0)

        base_query = select(Product)

        # ----------------
        # FILTERS
        # ----------------

        if search.q:
            q = search.q.strip()
            if len(q) >= 2:
                base_query = base_query.where(
                    or_(
                        Product.name.ilike(f"%{q}%"),
                        Product.description.ilike(f"%{q}%")
                    )
                )

        if search.status:
            base_query = base_query.where(
                Product.status == search.status.value  # String
            )

        if search.shop_id:
            base_query = base_query.where(
                Product.shop_id == search.shop_id
            )

        # ----------------
        # COUNT QUERY
        # ----------------

        count_query = select(func.count()).select_from(
            base_query.subquery()
        )
        total_result = await db.execute(count_query)
        total_count = total_result.scalar() or 0

        # ----------------
        # SORTING
        # ----------------

        sort_column = ALLOWED_ADMIN_SORT_FIELDS.get(
            pagination.sort_by,
            Product.created_at
        )

        if pagination.sort_order == "asc":
            base_query = base_query.order_by(sort_column.asc())
        else:
            base_query = base_query.order_by(sort_column.desc())

        # ----------------
        # PAGINATION
        # ----------------

        query = (
            base_query
            .options(joinedload(Product.shop))
            .offset(offset)
            .limit(limit)
        )

        result = await db.execute(query)
        products = result.scalars().all()

        # Audit log
        logger.info(
            f"Admin {current_user['email']} listed products "
            f"(offset={offset}, limit={limit})"
        )

        return {
            "items": [
                ProductAdminResponse.from_orm(p)
                for p in products
            ],
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total_count
        }

    except Exception as e:
        logger.error(f"Error listing products admin: {e}")
        raise HTTPException(
            status_code=500,
            detail="Could not list products"
        )


@router.post("/admin/{product_id}/approve")
async def approve_product_admin(
    product_id: str,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Approve product (admin only).
    """
    try:
        # UUID validation
        try:
            product_id_uuid = uuid.UUID(product_id)
        except ValueError:
            raise ValidationException(detail="Invalid product ID format")

        # Lock row to prevent race condition
        result = await db.execute(
            select(Product)
            .where(Product.id == product_id_uuid)
            .with_for_update()
        )
        product = result.scalar_one_or_none()

        if not product:
            raise NotFoundException(
                resource_type="Product",
                identifier=product_id
            )

        # Already approved?
        if product.is_approved:
            return {
                "message": "Product already approved",
                "product_id": str(product.id),
                "product_name": product.name,
                "approved_at": (
                    product.published_at.isoformat()
                    if product.published_at else None
                )
            }

        # Approve
        product.is_approved = True
        
        if product.status == ProductStatus.DRAFT.value:  # String
            product.status = ProductStatus.PUBLISHED.value  # String

        if not product.published_at:
            product.published_at = datetime.utcnow()

        await db.commit()
        await db.refresh(product)

        logger.info(
            f"Admin {current_user['email']} approved product {product.name}"
        )

        return {
            "message": "Product approved successfully",
            "product_id": str(product.id),
            "product_name": product.name,
            "approved_by": current_user["email"],
            "approved_at": product.published_at.isoformat()
        }

    except (NotFoundException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error approving product: {e}")
        raise HTTPException(
            status_code=500,
            detail="Could not approve product"
        )


# ==================== DİJİTAL ÜRÜN OLUŞTURMA (FORMDATA) ====================

@router.post("/digital", response_model=ProductResponse)
async def create_digital_product(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    primary_category: str = Form(...),
    base_price: float = Form(...),
    compare_at_price: Optional[float] = Form(None),
    product_type: ProductType = Form(ProductType.DIGITAL),
    currency: Currency = Form(Currency.TRY),
    file_type: Optional[FileType] = Form(None),
    tags: Optional[str] = Form(None),
    stock_quantity: int = Form(-1),
    product_file: UploadFile = File(None),
    cover_images: List[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new digital product with file upload support.
    """
    try:
        from sqlalchemy import select, text
        from models.shop import Shop
        from models.product import Product
        import slugify
        import random
        import string
        from datetime import datetime
        
        # ===== SHOP KONTROLÜ =====
        # Kullanıcının aktif shop'larını bul
        result = await db.execute(
            select(Shop).where(
                Shop.user_id == current_user["sub"],
                Shop.status == ShopStatus.ACTIVE.value  # String
            )
        )
        shops = result.scalars().all()
        
        if not shops:
            raise HTTPException(
                status_code=400,
                detail="You need an active shop to create products"
            )
        
        # İlk shop'u kullan (veya birden fazla varsa seçim yapılabilir)
        shop = shops[0]
        
        # ===== DİJİTAL ÜRÜN VALİDASYONU =====
        if product_type == ProductType.DIGITAL and not product_file:
            raise HTTPException(
                status_code=400,
                detail="Digital products must have a file uploaded"
            )
        
        # ===== SLUG OLUŞTUR =====
        base_slug = slugify.slugify(name)
        slug = base_slug
        
        # Slug benzersiz mi kontrol et
        result = await db.execute(
            select(Product).where(
                Product.shop_id == shop.id,
                Product.slug == slug
            )
        )
        
        if result.first():
            suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
            slug = f"{base_slug}-{suffix}"
        
        # ===== DOSYA URL'LERİ =====
        file_url = None
        if product_file:
            # TODO: Gerçek dosya yükleme işlemi
            file_url = f"/uploads/{shop.id}/products/{product_file.filename}"
        
        cover_urls = []
        if cover_images and cover_images[0]:
            for i, img in enumerate(cover_images):
                # TODO: Gerçek dosya yükleme işlemi
                cover_urls.append(f"/uploads/{shop.id}/products/covers/{i}_{img.filename}")
        
        # ===== ETİKETLER =====
        tags_list = []
        if tags:
            tags_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
        
        # ===== STOK MANTIĞI =====
        if product_type == ProductType.DIGITAL:
            db_stock_quantity = 999999 if stock_quantity == -1 else stock_quantity
        else:
            db_stock_quantity = max(0, stock_quantity)
        
        # ===== ÜRÜN OLUŞTUR =====
        product = Product(
            shop_id=shop.id,
            name=name,
            description=description,
            base_price=Decimal(str(base_price)),
            compare_at_price=Decimal(str(compare_at_price)) if compare_at_price else None,
            primary_category=primary_category,
            tags=tags_list,
            file_url=file_url,
            file_type=file_type.value if file_type else None,
            stock_quantity=db_stock_quantity,
            slug=slug,
            image_gallery=cover_urls if cover_urls else None,
            feature_image_url=cover_urls[0] if cover_urls else None,
            status=ProductStatus.DRAFT.value,  # String
            is_approved=True,
            product_type=product_type.value,    # String
            base_currency=currency.value,       # String
            requires_approval=False,
            published_at=datetime.utcnow(),
        )
        
        db.add(product)
        await db.commit()
        await db.refresh(product)
        
        # Shop'un ürün sayısını güncelle
        await db.execute(
            update(Shop)
            .where(Shop.id == shop.id)
            .values(total_products=Shop.total_products + 1)
        )
        await db.commit()
        
        logger.info(f"Digital product created: {product.name}")
        
        return ProductResponse.from_orm(product)
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating digital product: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Could not create digital product: {str(e)}"
        )# test_api.py

