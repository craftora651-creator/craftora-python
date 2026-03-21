# api/aliexpress.py
"""
AliExpress integration API endpoints
Fetch products, import to store
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import httpx
import os
import uuid
from pydantic import BaseModel, Field

from database.database import get_db
from helpers.security import get_current_user_clean, get_current_verified_user
from nix.exceptions import (
    NotFoundException,
    ValidationException,
    ForbiddenException
)
from config.config import settings
from models.product import Product, ProductStatus, ProductType, Currency
from models.shop import Shop, ShopStatus
from slugify import slugify
import logging
import hashlib
import time

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/aliexpress", tags=["aliexpress"])

# ==================== CONFIG ====================

ALIEXPRESS_API_KEY = os.getenv("ALIEXPRESS_API_KEY")
ALIEXPRESS_API_SECRET = os.getenv("ALIEXPRESS_API_SECRET")
ALIEXPRESS_BASE_URL = "https://api.aliexpress.com/v2"

if not ALIEXPRESS_API_KEY:
    logger.warning("⚠️ ALIEXPRESS_API_KEY environment variable is not set!")

# ==================== MODELS ====================

class AliExpressProduct(BaseModel):
    supplier: str = "aliexpress"
    supplier_product_id: str
    name: str
    description: str
    price: float
    compare_price: Optional[float] = None
    currency: str = "USD"
    images: List[str] = []
    categories: List[str] = []
    variants: List[Dict] = []
    shipping_cost: Optional[float] = None
    stock_status: str
    product_url: str

class ImportProductRequest(BaseModel):
    supplier_product_id: str
    name: str
    description: str
    price: float = Field(..., gt=0)
    compare_price: Optional[float] = Field(None, gt=0)
    images: List[str]
    variants: List[Dict] = []
    shop_id: str
    markup_percent: float = Field(20, ge=0, le=100)

# ==================== HELPER FUNCTIONS ====================

def generate_sign(params: dict, secret: str) -> str:
    """AliExpress için imza oluştur"""
    sorted_keys = sorted(params.keys())
    sign_str = secret
    for key in sorted_keys:
        sign_str += f"{key}{params[key]}"
    sign_str += secret
    return hashlib.md5(sign_str.encode()).hexdigest().upper()

# ==================== ENDPOINTS ====================

@router.get("/fetch-product", response_model=Dict[str, Any])
async def fetch_aliexpress_product(
    product_id: str = Query(..., description="AliExpress ürün ID"),
    current_user: dict = Depends(get_current_user_clean)
):
    """
    AliExpress'ten ürün bilgisi getir (Product ID ile)
    
    Örnek: 1005005005005000
    """
    if not ALIEXPRESS_API_KEY:
        # Mock data döndür
        return {
            "success": True,
            "product": {
                "supplier": "aliexpress",
                "supplier_product_id": product_id,
                "name": f"AliExpress Ürünü {product_id}",
                "description": "Bu bir test ürünüdür. Gerçek AliExpress API'si için API anahtarı gerekli.",
                "price": 49.99,
                "compare_price": 79.99,
                "currency": "USD",
                "images": [
                    "https://ae01.alicdn.com/kf/example1.jpg",
                    "https://ae01.alicdn.com/kf/example2.jpg"
                ],
                "categories": ["Elektronik"],
                "variants": [
                    {"name": "Renk", "values": ["Siyah", "Beyaz", "Mavi"]}
                ],
                "shipping_cost": 7.99,
                "stock_status": "in_stock",
                "product_url": f"https://www.aliexpress.com/item/{product_id}.html"
            }
        }
    
    try:
        # AliExpress API'sine istek
        timestamp = str(int(time.time() * 1000))
        params = {
            "method": "aliexpress.product.get",
            "app_key": ALIEXPRESS_API_KEY,
            "timestamp": timestamp,
            "format": "json",
            "product_id": product_id,
            "v": "2.0"
        }
        
        # İmza ekle
        params["sign"] = generate_sign(params, ALIEXPRESS_API_SECRET)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{ALIEXPRESS_BASE_URL}/rest",
                params=params
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"AliExpress API error: {response.text}"
                )
            
            data = response.json()
            
            # AliExpress response'u normalize et
            product_data = data.get("aliexpress_product_get_response", {}).get("result", {})
            
            normalized = {
                "supplier": "aliexpress",
                "supplier_product_id": product_id,
                "name": product_data.get("product_title"),
                "description": product_data.get("product_description"),
                "price": float(product_data.get("product_price", 0)),
                "compare_price": float(product_data.get("market_price")) if product_data.get("market_price") else None,
                "currency": "USD",
                "images": product_data.get("image_urls", "").split(";"),
                "categories": [product_data.get("category_name", "")],
                "variants": product_data.get("sku_list", []),
                "shipping_cost": float(product_data.get("freight", {}).get("price", 0)),
                "stock_status": "in_stock" if product_data.get("stock") > 0 else "out_of_stock",
                "product_url": f"https://www.aliexpress.com/item/{product_id}.html"
            }
            
            logger.info(f"AliExpress product fetched: {normalized['name']} by {current_user['email']}")
            
            return {
                "success": True,
                "product": normalized
            }
            
    except httpx.RequestError as e:
        logger.error(f"AliExpress connection error: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"AliExpress connection error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error fetching AliExpress product: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )


@router.post("/import-product", response_model=Dict[str, Any])
async def import_aliexpress_product(
    request: ImportProductRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_verified_user)
):
    """
    AliExpress'ten getirilen ürünü mağazaya ekle
    """
    try:
        # Mağaza kontrolü
        shop_id_uuid = uuid.UUID(request.shop_id)
        user_id_uuid = uuid.UUID(current_user["sub"])
        
        result = await db.execute(
            select(Shop).where(
                Shop.id == shop_id_uuid,
                Shop.user_id == user_id_uuid,
                Shop.status == ShopStatus.ACTIVE.value
            )
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            raise ForbiddenException(
                detail="Shop not found, not active, or you don't have permission"
            )
        
        # Kar marjı ekle
        final_price = request.price * (1 + request.markup_percent / 100)
        
        # Benzersiz slug oluştur
        base_slug = slugify(request.name)
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
        
        # Ürünü kaydet
        product = Product(
            shop_id=shop.id,
            name=request.name,
            description=request.description,
            base_price=Decimal(str(final_price)),
            compare_at_price=Decimal(str(request.compare_price)) if request.compare_price else None,
            product_type=ProductType.PHYSICAL.value,
            currency=Currency.TRY.value,
            stock_quantity=0,
            image_gallery=request.images,
            feature_image_url=request.images[0] if request.images else None,
            slug=slug,
            metadata={
                "supplier": "aliexpress",
                "supplier_product_id": request.supplier_product_id,
                "variants": request.variants
            },
            status=ProductStatus.DRAFT.value,
            is_approved=True,
            created_at=datetime.utcnow()
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
        
        logger.info(f"AliExpress product imported: {product.name} to shop {shop.shop_name}")
        
        return {
            "success": True,
            "message": "Product imported successfully",
            "product_id": str(product.id),
            "product_name": product.name
        }
        
    except ForbiddenException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error importing AliExpress product: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Could not import product: {str(e)}"
        )


@router.get("/search", response_model=Dict[str, Any])
async def search_aliexpress_products(
    query: str = Query(..., min_length=2),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    current_user: dict = Depends(get_current_user_clean)
):
    """
    AliExpress'te ürün ara
    """
    if not ALIEXPRESS_API_KEY:
        # Mock search results
        return {
            "success": True,
            "total": 3,
            "page": page,
            "limit": limit,
            "products": [
                {
                    "supplier_product_id": "1005005005005000",
                    "name": f"Test Ürün 1 - {query}",
                    "price": 29.99,
                    "image": "https://ae01.alicdn.com/kf/test1.jpg",
                    "stock_status": "in_stock"
                },
                {
                    "supplier_product_id": "1005005005005001",
                    "name": f"Test Ürün 2 - {query}",
                    "price": 49.99,
                    "image": "https://ae01.alicdn.com/kf/test2.jpg",
                    "stock_status": "in_stock"
                }
            ]
        }
    
    try:
        # AliExpress arama API'si
        timestamp = str(int(time.time() * 1000))
        params = {
            "method": "aliexpress.product.search",
            "app_key": ALIEXPRESS_API_KEY,
            "timestamp": timestamp,
            "format": "json",
            "keywords": query,
            "page": page,
            "page_size": limit,
            "v": "2.0"
        }
        
        params["sign"] = generate_sign(params, ALIEXPRESS_API_SECRET)
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{ALIEXPRESS_BASE_URL}/rest",
                params=params
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="AliExpress API error"
                )
            
            data = response.json()
            products = data.get("aliexpress_product_search_response", {}).get("result", {}).get("products", [])
            
            normalized = []
            for p in products:
                normalized.append({
                    "supplier_product_id": p.get("product_id"),
                    "name": p.get("product_title"),
                    "price": float(p.get("product_price", 0)),
                    "image": p.get("image_urls", "").split(";")[0] if p.get("image_urls") else None,
                    "stock_status": "in_stock" if p.get("stock") > 0 else "out_of_stock"
                })
            
            return {
                "success": True,
                "total": data.get("total_results", 0),
                "page": page,
                "limit": limit,
                "products": normalized
            }
            
    except httpx.RequestError as e:
        logger.error(f"AliExpress connection error: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"AliExpress connection error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error searching AliExpress products: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )