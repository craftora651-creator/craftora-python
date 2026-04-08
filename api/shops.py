"""
Shop management API endpoints
Create, update, delete shops, manage shop settings
"""
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
import httpx
from database.database import get_db
from helpers.security import get_current_user_clean, get_current_verified_user
from nix.dependencies import (
    PaginationParams, 
    SearchParams,
    require_seller,
    require_shop_ownership,
    FileUploadValidator,
    require_admin
)
from nix.exceptions import (
    NotFoundException,
    ValidationException,
    ForbiddenException,
    ResourceExistsException
)
from nix.logging import logger, audit_logger, performance_logger
from config.config import settings
from models.shop import Shop, ShopStatus
from models.user import User
from routers.shops import (
    ShopCreate, 
    ShopUpdate, 
    ShopResponse, 
    ShopDetailResponse,
    ShopAdminResponse,
    ShopSearchParams
)
from models.shop import Shop, ShopStatus, SubscriptionStatus, ShopVisibility  # ✅
import httpx

router = APIRouter(prefix="/shops", tags=["shops"])

# ==================== SHOP CREATION & BASIC CRUD ====================


@router.post("/", response_model=ShopResponse)
async def create_shop(
    shop_data: ShopCreate,
    current_user: dict = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new shop.
    User must be verified to create a shop.
    """
    try:
        print(f"🔍 PENDING.value: {SubscriptionStatus.PENDING.value}")
        print(f"🔍 PENDING: {SubscriptionStatus.PENDING}")
        print(f"🔍 PENDING type: {type(SubscriptionStatus.PENDING.value)}")
        result = await db.execute(
            select(Shop).where(
                (Shop.slug == shop_data.slug) |
                (Shop.shop_name == shop_data.shop_name)
            )
        )
        existing_shop = result.scalar_one_or_none()
        if existing_shop:
            raise ResourceExistsException(
                resource_type="Shop",
                identifier=shop_data.slug,
                detail="Shop with this name or slug already exists"
            )
        from uuid import UUID
        user_uuid = UUID(current_user["sub"])

        result = await db.execute(
            select(Shop).where(Shop.user_id == user_uuid)
        )
        user_shops = result.scalars().all()
        
        if len(user_shops) >= 3:
            raise ValidationException(
                detail="You can only have up to 3 shops"
            )
        
        # Create shop
        shop = Shop(
            **shop_data.dict(),
            user_id=user_uuid,
            subscription_status="pending",
            is_verified=False,
            is_featured=False,
            visibility="public"
        )
        
        db.add(shop)
        await db.commit()
        await db.refresh(shop)
        
        # Update user's shop count
        await db.execute(
            update(User)
            .where(User.id == user_uuid)
            .values(shop_count=len(user_shops) + 1)
        )
        await db.commit()
        
        print(f"✅ Shop created: {shop.shop_name} by {current_user['email']}")
        
        # ============================================
        # ✅ MAĞAZA OLUŞTUKTAN SONRA GO BACKEND'E HABER VER (TEMA OLUŞTUR)
        # ============================================
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8082/api/shop/theme/initialize",
                    json={"shop_id": str(shop.id)},
                    timeout=5.0
                )
                if response.status_code == 200:
                    print(f"✅ Go backend'de tema oluşturuldu: {shop.shop_name}")
                else:
                    print(f"⚠️ Go backend tema oluşturma hatası: {response.status_code} - {response.text}")
        except httpx.ConnectError:
            print(f"⚠️ Go backend'e bağlanılamadı (8082 portu kapalı olabilir)")
        except Exception as e:
            print(f"⚠️ Go backend isteği başarısız: {e}")
        
        return ShopResponse.from_orm(shop)
        
    except (ResourceExistsException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        print(f"❌ Error creating shop: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not create shop: {str(e)}"
        )
   

@router.get("/my")
async def get_my_shops(
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's shops.
    """
    try:
        from uuid import UUID
        user_uuid = UUID(current_user["sub"])
        
        result = await db.execute(
            select(Shop).where(
                Shop.user_id == user_uuid
            ).order_by(Shop.created_at.desc())
        )
        shops = result.scalars().all()
        
        # MANUEL DICT DÖNDÜR - Pydantic'ten kaçın
        response_shops = []
        for shop in shops:
            response_shops.append({
                "id": str(shop.id),
                "user_id": str(shop.user_id),
                "shop_name": shop.shop_name,
                "slug": shop.slug,
                "description": shop.description,
                "short_description": shop.short_description,
                "slogan": shop.slogan,
                "logo_url": shop.logo_url,
                "banner_url": shop.banner_url,
                "favicon_url": shop.favicon_url,
                "theme_color": shop.theme_color or "#3B82F6",
                "accent_color": shop.accent_color or "#10B981",
                "contact_email": shop.contact_email,
                "support_email": shop.support_email,
                "phone": shop.phone,
                "website_url": shop.website_url,
                "tax_number": shop.tax_number,
                "tax_office": shop.tax_office,
                "primary_category": shop.primary_category,
                "secondary_categories": shop.secondary_categories or [],
                "tags": shop.tags or [],
                "status": shop.status.value if shop.status else "draft",
                "visibility": shop.visibility.value if shop.visibility else "public",
                "subscription_status": shop.subscription_status.value if shop.subscription_status else "pending",
                "is_verified": shop.is_verified or False,
                "is_featured": shop.is_featured or False,
                "total_products": shop.total_products or 0,
                "total_orders": shop.total_orders or 0,
                "total_revenue": float(shop.total_revenue) if shop.total_revenue else 0.0,
                "average_rating": float(shop.average_rating) if shop.average_rating else 0.0,
                "review_count": shop.review_count or 0,
                "created_at": shop.created_at.isoformat() if shop.created_at else None,
                "updated_at": shop.updated_at.isoformat() if shop.updated_at else None,
                "published_at": shop.published_at.isoformat() if shop.published_at else None,
            })
        
        return response_shops
        
    except Exception as e:
        print(f"❌ Error getting user shops: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not retrieve your shops: {str(e)}"
        )
   
@router.get("/{shop_id}", response_model=ShopDetailResponse)
async def get_shop(
    shop_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get shop details by ID (public endpoint).
    """
    try:
        result = await db.execute(
            select(Shop).where(
                Shop.id == shop_id,
                Shop.status == ShopStatus.ACTIVE,
                Shop.is_approved == True
            )
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            raise NotFoundException(
                resource_type="Shop",
                identifier=shop_id,
                detail="Shop not found or not active"
            )
        
        return ShopDetailResponse.from_orm(shop)
        
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error getting shop: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve shop"
        )


@router.put("/{shop_id}", response_model=ShopResponse)
async def update_shop(
    shop_id: str,
    shop_data: ShopUpdate,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Update shop details (owner only).
    """
    try:
        result = await db.execute(
            select(Shop).where(
                Shop.id == shop_id,
                Shop.user_id == current_user["sub"]
            )
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            raise ForbiddenException(
                detail="You don't have permission to update this shop"
            )
        
        # Check if shop can be updated
        if shop.status not in [ShopStatus.DRAFT, ShopStatus.ACTIVE]:
            raise ValidationException(
                detail=f"Cannot update shop with status: {shop.status.value}"
            )
        
        # Update fields
        update_data = shop_data.dict(exclude_unset=True)
        
        # Don't allow updating restricted fields
        restricted_fields = ["owner_id", "status", "is_approved", "is_verified"]
        for field in restricted_fields:
            update_data.pop(field, None)
        
        for field, value in update_data.items():
            setattr(shop, field, value)
        
        await db.commit()
        await db.refresh(shop)
        
        logger.info(f"Shop updated: {shop.name} by {current_user['email']}")
        
        return ShopResponse.from_orm(shop)
        
    except (ForbiddenException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating shop: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update shop"
        )

@router.delete("/{shop_id}")
async def delete_shop(
    shop_id: str,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete shop (soft delete - changes status to CLOSED).
    """
    try:
        from uuid import UUID
        user_uuid = UUID(current_user["sub"])
        shop_uuid = UUID(shop_id)
        
        result = await db.execute(
            select(Shop).where(
                Shop.id == shop_uuid,
                Shop.user_id == user_uuid
            )
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to delete this shop"
            )
        
        # Direkt sil (soft delete yerine)
        await db.delete(shop)
        await db.commit()
        
        print(f"✅ Shop deleted: {shop.shop_name}")
        
        return {
            "message": "Shop successfully deleted",
            "shop_id": shop_id,
            "shop_name": shop.shop_name
        }
        
    except Exception as e:
        print(f"❌ Error deleting shop: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Could not delete shop: {str(e)}"
        )


# ==================== SHOP STATUS MANAGEMENT ====================

@router.post("/{shop_id}/publish")
async def publish_shop(
    shop_id: str,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Publish shop (change status from DRAFT to PENDING_REVIEW).
    In MVP, automatically approves if all requirements met.
    """
    try:
        result = await db.execute(
            select(Shop).where(
                Shop.id == shop_id,
                Shop.user_id == current_user["sub"]
            )
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            raise ForbiddenException(
                detail="You don't have permission to publish this shop"
            )
        
        if shop.status != ShopStatus.DRAFT:
            raise ValidationException(
                detail=f"Cannot publish shop with status: {shop.status.value}"
            )
        if not shop.name or not shop.description:
            raise ValidationException(
                detail="Shop must have name and description to publish"
            )
        shop.status = ShopStatus.ACTIVE
        shop.is_approved = True
        shop.published_at = datetime.utcnow()
        await db.commit()
        await db.refresh(shop)
        logger.info(f"Shop published: {shop.name} by {current_user['email']}")
        return {
            "message": "Shop published successfully",
            "shop_id": shop_id,
            "shop_name": shop.name,
            "status": "active",
            "is_approved": True
        }
        
    except (ForbiddenException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error publishing shop: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not publish shop"
        )


@router.post("/{shop_id}/suspend")
async def suspend_shop(
    shop_id: str,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Suspend shop (owner can temporarily suspend their shop).
    """
    try:
        result = await db.execute(
            select(Shop).where(
                Shop.id == shop_id,
                Shop.user_id == current_user["sub"]
            )
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            raise ForbiddenException(
                detail="You don't have permission to suspend this shop"
            )
        
        if shop.status != ShopStatus.ACTIVE:
            raise ValidationException(
                detail=f"Cannot suspend shop with status: {shop.status.value}"
            )
        
        shop.status = ShopStatus.SUSPENDED
        shop.suspended_at = datetime.utcnow()
        
        await db.commit()
        
        logger.warning(f"Shop suspended: {shop.name} by {current_user['email']}")
        
        return {
            "message": "Shop suspended successfully",
            "shop_id": shop_id,
            "shop_name": shop.name,
            "status": "suspended",
            "suspended_at": shop.suspended_at.isoformat()
        }
        
    except (ForbiddenException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error suspending shop: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not suspend shop"
        )


@router.post("/{shop_id}/activate")
async def activate_shop(
    shop_id: str,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Activate suspended shop.
    """
    try:
        result = await db.execute(
            select(Shop).where(
                Shop.id == shop_id,
                Shop.user_id == current_user["sub"]
            )
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            raise ForbiddenException(
                detail="You don't have permission to activate this shop"
            )
        
        if shop.status != ShopStatus.SUSPENDED:
            raise ValidationException(
                detail=f"Cannot activate shop with status: {shop.status.value}"
            )
        
        shop.status = ShopStatus.ACTIVE
        shop.suspended_at = None
        
        await db.commit()
        
        logger.info(f"Shop activated: {shop.name} by {current_user['email']}")
        
        return {
            "message": "Shop activated successfully",
            "shop_id": shop_id,
            "shop_name": shop.name,
            "status": "active"
        }
        
    except (ForbiddenException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error activating shop: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not activate shop"
        )


# ==================== SHOP SETTINGS & CONFIGURATION ====================



@router.get("/{shop_id}/settings")
async def get_shop_settings(
    shop_id: str,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Get shop settings (owner only).
    """
    try:
        from uuid import UUID
        
        print("=" * 50)
        print("📤 GET SHOP SETTINGS ÇAĞRILDI")
        print(f"📤 shop_id: {shop_id}")
        
        user_uuid = UUID(current_user["sub"])
        shop_uuid = UUID(shop_id)
        
        # 🔥 KRİTİK: YENİ BİR SORGU YAP - CACHE KULLANMA!
        result = await db.execute(
            select(Shop).where(
                Shop.id == shop_uuid,
                Shop.user_id == user_uuid
            )
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            raise HTTPException(status_code=403, detail="No permission or shop not found")
        
        # 🔥 KRİTİK: Session'ı kapatıp yeni sorgu yapmak için
        await db.flush()
        
        # 🔥 KRİTİK: JSON field'ı manuel olarak oku
        # SQLAlchemy'nin JSON field'ı bazen güncel olmayabiliyor
        # Bu yüzden direkt veritabanından tekrar çekelim
        from sqlalchemy import text
        
        raw_result = await db.execute(
            text("SELECT settings FROM shops WHERE id = :id AND user_id = :user_id"),
            {"id": str(shop_uuid), "user_id": str(user_uuid)}
        )
        raw_settings = raw_result.scalar_one_or_none()
        
        print(f"📦 RAW settings from DB: {raw_settings}")
        
        if raw_settings:
            settings_data = raw_settings
        else:
            settings_data = shop.settings if shop.settings else {}
        
        print(f"📦 settings_data: {settings_data}")
        
        response_data = {
            "shop_id": str(shop.id),
            "contact_email": settings_data.get("contact_email", shop.contact_email or "") if isinstance(settings_data, dict) else "",
            "support_email": settings_data.get("support_email", shop.support_email or "") if isinstance(settings_data, dict) else "",
            "phone": settings_data.get("phone", shop.phone or "") if isinstance(settings_data, dict) else "",
            "address": settings_data.get("address", {
                "street": "",
                "city": "",
                "country": "",
                "postal_code": ""
            }) if isinstance(settings_data, dict) else {
                "street": "",
                "city": "",
                "country": "",
                "postal_code": ""
            },
            "social_media": settings_data.get("social_media", {
                "instagram": "",
                "facebook": "",
                "tiktok": "",
                "twitter": "",
                "youtube": "",
                "pinterest": ""
            }) if isinstance(settings_data, dict) else {
                "instagram": "",
                "facebook": "",
                "tiktok": "",
                "twitter": "",
                "youtube": "",
                "pinterest": ""
            }
        }
        
        print(f"📤 Dönen response: {response_data}")
        print("=" * 50)
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error getting shop settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not retrieve shop settings: {str(e)}"
        )
        
        

@router.put("/{shop_id}/settings")
async def update_shop_settings(
    shop_id: str,
    settings: dict,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Update shop settings (owner only).
    """
    try:
        from uuid import UUID
        
        print("=" * 50)
        print("📥 UPDATE SHOP SETTINGS ÇAĞRILDI")
        print(f"📥 shop_id: {shop_id}")
        print(f"📥 Gelen settings: {settings}")
        
        user_uuid = UUID(current_user["sub"])
        shop_uuid = UUID(shop_id)
        
        result = await db.execute(
            select(Shop).where(
                Shop.id == shop_uuid,
                Shop.user_id == user_uuid
            )
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            raise HTTPException(status_code=403, detail="No permission or shop not found")
        
        # 🔥 KRİTİK: JSON field'ı manuel olarak güncelle
        current_settings = dict(shop.settings) if shop.settings else {}
        current_settings.update(settings)
        
        # 🔥 KRİTİK: Yeni dict'i ata
        shop.settings = current_settings
        
        # Also update direct fields if provided
        if "contact_email" in settings:
            shop.contact_email = settings["contact_email"]
        if "support_email" in settings:
            shop.support_email = settings["support_email"]
        if "phone" in settings:
            shop.phone = settings["phone"]
        
        await db.commit()
        await db.refresh(shop)
        
        print(f"✅ COMMIT sonrası shop.settings: {shop.settings}")
        
        return {
            "message": "Settings updated successfully", 
            "shop_id": str(shop.id),
            "settings": shop.settings
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        print(f"❌ Error updating shop settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not update shop settings: {str(e)}"
        )


# ==================== SHOP STATISTICS ====================

@router.get("/{shop_id}/stats")
async def get_shop_stats(
    shop_id: str,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Get shop statistics (owner only).
    """
    try:
        result = await db.execute(
            select(Shop).where(
                Shop.id == shop_id,
                Shop.user_id == current_user["sub"]
            )
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            raise ForbiddenException(
                detail="You don't have permission to view these statistics"
            )
        
        # In MVP, return basic stats
        # In production, calculate from orders, products, etc.
        stats = {
            "shop_id": str(shop.id),
            "shop_name": shop.name,
            "status": shop.status.value,
            "total_products": shop.total_products or 0,
            "total_orders": shop.total_orders or 0,
            "total_revenue": float(shop.total_revenue) if shop.total_revenue else 0.0,
            "created_at": shop.created_at.isoformat(),
            "published_at": shop.published_at.isoformat() if shop.published_at else None,
            "is_approved": shop.is_approved,
            "is_verified": shop.is_verified,
            "plan": shop.plan.value if shop.plan else None
        }
        
        return stats
        
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(f"Error getting shop stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve shop statistics"
        )


# ==================== SHOP LOGO/UPLOAD ====================

@router.post("/{shop_id}/logo")
async def upload_shop_logo(
    shop_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db),
    file_validator: FileUploadValidator = Depends(FileUploadValidator(
        max_size_mb=5,
        allowed_types=["image/jpeg", "image/png", "image/webp"]
    ))
):
    """
    Upload shop logo (owner only).
    In MVP, store URL. In production, upload to S3/Cloudinary.
    """
    try:
        # Validate file
        await file_validator(file)
        
        result = await db.execute(
            select(Shop).where(
                Shop.id == shop_id,
                Shop.user_id == current_user["sub"]
            )
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            raise ForbiddenException(
                detail="You don't have permission to upload logo for this shop"
            )
        logo_url = f"/uploads/shops/{shop_id}/logo_{datetime.utcnow().timestamp()}.{file.filename.split('.')[-1]}"
        shop.logo_url = logo_url
        await db.commit()
        await db.refresh(shop)
        logger.info(f"Shop logo uploaded: {shop.name} by {current_user['email']}")
        return {
            "message": "Logo uploaded successfully",
            "shop_id": str(shop.id),
            "logo_url": logo_url,
            "filename": file.filename,
            "content_type": file.content_type,
            "size": file.size
        }
    except (ForbiddenException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error uploading shop logo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not upload logo"
        )
        
# ==================== PUBLIC MARKETPLACE ENDPOINTS ====================

@router.get("/public/list", response_model=List[ShopDetailResponse])
async def list_shops_public(
    pagination: PaginationParams = Depends(),
    search: ShopSearchParams = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    List all active shops (public marketplace).
    """
    try:
        query = select(Shop).where(
            Shop.status == ShopStatus.ACTIVE,
            Shop.is_approved == True
        )
        if search.name:
            query = query.where(Shop.name.ilike(f"%{search.name}%"))
        if search.category:
            query = query.where(Shop.category == search.category)
        if search.is_verified:
            query = query.where(Shop.is_verified == search.is_verified)
        query = query.offset(pagination.offset).limit(pagination.limit)
        if pagination.sort_by:
            sort_column = getattr(Shop, pagination.sort_by, None)
            if sort_column:
                if pagination.sort_order == "desc":
                    query = query.order_by(sort_column.desc())
                else:
                    query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(Shop.created_at.desc())
        result = await db.execute(query)
        shops = result.scalars().all()
        return [ShopDetailResponse.from_orm(shop) for shop in shops]
    except Exception as e:
        logger.error(f"Error listing public shops: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve shops"
        )


@router.get("/public/{slug}", response_model=ShopDetailResponse)
async def get_shop_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get shop by slug (public marketplace).
    """
    try:
        result = await db.execute(
            select(Shop).where(
                Shop.slug == slug,
                Shop.status == ShopStatus.ACTIVE,
                Shop.is_approved == True
            )
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            raise NotFoundException(
                resource_type="Shop",
                identifier=slug,
                detail="Shop not found or not active"
            )
        
        return ShopDetailResponse.from_orm(shop)
        
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error getting shop by slug: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve shop"
        )


# ==================== ADMIN ENDPOINTS ====================

@router.get("/admin/list", response_model=List[ShopAdminResponse])
async def list_shops_admin(
    pagination: PaginationParams = Depends(),
    search: ShopSearchParams = Depends(),
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    List all shops (admin only).
    """
    try:
        query = select(Shop)
        
        # Apply filters
        if search.name:
            query = query.where(Shop.name.ilike(f"%{search.name}%"))
        if search.status:
            query = query.where(Shop.status == search.status)
        if search.owner_email:
            # Join with users table
            from sqlalchemy.orm import joinedload
            query = query.join(User).where(User.email.ilike(f"%{search.owner_email}%"))
        
        # Apply pagination
        query = query.offset(pagination.offset).limit(pagination.limit)
        
        # Apply sorting
        if pagination.sort_by:
            sort_column = getattr(Shop, pagination.sort_by, None)
            if sort_column:
                if pagination.sort_order == "desc":
                    query = query.order_by(sort_column.desc())
                else:
                    query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(Shop.created_at.desc())
        
        result = await db.execute(query)
        shops = result.scalars().all()
        
        return [ShopAdminResponse.from_orm(shop) for shop in shops]
        
    except Exception as e:
        logger.error(f"Error listing shops admin: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not list shops"
        )


@router.post("/admin/{shop_id}/approve")
async def approve_shop_admin(
    shop_id: str,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Approve shop (admin only).
    """
    try:
        result = await db.execute(
            select(Shop).where(Shop.id == shop_id)
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            raise NotFoundException(
                resource_type="Shop",
                identifier=shop_id
            )
        
        shop.is_approved = True
        shop.status = ShopStatus.ACTIVE
        shop.published_at = datetime.utcnow()
        
        await db.commit()
        
        logger.info(f"Shop approved by admin: {shop.name} by {current_user['email']}")
        
        return {
            "message": "Shop approved successfully",
            "shop_id": shop_id,
            "shop_name": shop.name,
            "approved_by": current_user["email"],
            "approved_at": datetime.utcnow().isoformat()
        }
        
    except NotFoundException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error approving shop: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not approve shop"
        )


@router.post("/admin/{shop_id}/suspend")
async def suspend_shop_admin(
    shop_id: str,
    reason: str,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Suspend shop (admin only).
    """
    try:
        result = await db.execute(
            select(Shop).where(Shop.id == shop_id)
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            raise NotFoundException(
                resource_type="Shop",
                identifier=shop_id
            )
        
        shop.status = ShopStatus.SUSPENDED
        shop.suspended_at = datetime.utcnow()
        shop.suspension_reason = reason
        
        await db.commit()
        
        logger.warning(f"Shop suspended by admin: {shop.name} by {current_user['email']}, reason: {reason}")
        
        return {
            "message": "Shop suspended successfully",
            "shop_id": shop_id,
            "shop_name": shop.name,
            "suspended_by": current_user["email"],
            "suspended_at": shop.suspended_at.isoformat(),
            "reason": reason
        }
        
    except NotFoundException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error suspending shop admin: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not suspend shop"
        )
