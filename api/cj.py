"""
CJ Dropshipping integration API endpoints
Fetch products, import to store, manage inventory
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import httpx
import os
import uuid
import re
import asyncio
from pydantic import BaseModel, Field
from models.user import User
from database.database import get_db
from helpers.security import get_current_user_clean, get_current_verified_user
from nix.exceptions import (
    ValidationException,
    ForbiddenException,
)

from routers.users import (
    CJConnectRequest, 
    CJConnectResponse, 
    CJStatusResponse, 
    CJDisconnectResponse
)

from models.product import Product, ProductStatus, ProductType, Currency
from models.shop import Shop, ShopStatus
from slugify import slugify

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cj", tags=["cj"])

# ==================== CONFIG ====================

CJ_API_KEY = os.getenv("CJ_API_KEY")
CJ_API_SECRET = os.getenv("CJ_API_SECRET")
CJ_BASE_URL = "https://developers.cjdropshipping.com/api2.0/v1"

# Token cache
_cj_access_token = None
_cj_token_expiry = None
_token_lock = asyncio.Lock()

if not CJ_API_KEY:
    logger.warning("⚠️ CJ_API_KEY environment variable is not set!")

# ==================== MODELS ====================

class CJShippingMethod(BaseModel):
    method: str
    price: float
    currency: str = "USD"
    estimated_days: str
    from_location: str

class CJVariant(BaseModel):
    name: str
    values: List[str]

class ImportProductRequest(BaseModel):
    supplier_product_id: str
    name: str
    description: str
    price: float = Field(..., gt=0)
    compare_price: Optional[float] = Field(None, gt=0)
    images: List[str]
    variants: List[Dict] = []
    shipping_methods: List[Dict] = []
    shop_id: str
    category_id: Optional[str] = None
    markup_percent: float = Field(20, ge=0, le=100)

class CJFetchRequest(BaseModel):
    url: Optional[str] = None
    product_id: Optional[str] = None

# ==================== TOKEN MANAGEMENT ====================

async def get_cj_access_token() -> str:
    """CJ API access token al veya cache'den getir - RATE LIMIT KORUMALI"""
    global _cj_access_token, _cj_token_expiry
    
    # Token varsa ve geçerliyse direkt döndür
    if _cj_access_token and _cj_token_expiry:
        if datetime.now() < _cj_token_expiry:
            logger.info("✅ Using cached CJ access token")
            return _cj_access_token
    
    # Aynı anda birden fazla istek token almaya çalışmasın
    async with _token_lock:
        # Lock içinde tekrar kontrol et (başka istek almış olabilir)
        if _cj_access_token and _cj_token_expiry:
            if datetime.now() < _cj_token_expiry:
                return _cj_access_token
        
        logger.info("🔄 Getting new CJ access token...")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{CJ_BASE_URL}/authentication/getAccessToken",
                    json={"apiKey": CJ_API_KEY}
                )
                
                if response.status_code == 429:
                    logger.error("❌ Rate limit exceeded (429). Waiting 5 minutes...")
                    raise HTTPException(
                        status_code=429,
                        detail="CJ API rate limit exceeded. Please wait 5 minutes and try again."
                    )
                
                if response.status_code != 200:
                    logger.error(f"❌ Token error: {response.text}")
                    raise Exception(f"Token alınamadı: {response.status_code}")
                
                data = response.json()
                
                if data.get("code") != 200:
                    logger.error(f"❌ Token error: {data}")
                    raise Exception(f"Token alınamadı: {data.get('message')}")
                
                result = data.get("data", {})
                _cj_access_token = result.get("accessToken")
                
                # Expiry date'i parse et
                expiry_str = result.get("accessTokenExpiryDate")
                if expiry_str:
                    # ISO format parse et
                    expiry_str = expiry_str.replace("+08:00", "")
                    _cj_token_expiry = datetime.fromisoformat(expiry_str) - timedelta(hours=8)
                else:
                    # Fallback: 15 gün
                    _cj_token_expiry = datetime.now() + timedelta(days=14)
                
                logger.info(f"✅ CJ token alındı, expires: {_cj_token_expiry}")
                return _cj_access_token
                
        except httpx.RequestError as e:
            logger.error(f"❌ Token connection error: {e}")
            raise Exception(f"CJ API bağlantı hatası: {str(e)}")

# ==================== HELPER FUNCTIONS ====================

def extract_product_id_from_url(url: str) -> str:
    """URL'den ürün ID'sini çıkar - TÜM FORMATLARI DENE"""
    
    # 1. /product/details/ UUID FORMATI (YENİ)
    match = re.search(r'/product/details/([A-Z0-9-]+)', url)
    if match:
        return match.group(1)
    
    # 2. /product/details/ RAKAM FORMATI
    match = re.search(r'/product/details/(\d+)', url)
    if match:
        return match.group(1)
    
    # 3. -p- UUID FORMATI (ESKİ)
    match = re.search(r'-p-([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})', url)
    if match:
        return match.group(1)
    
    # 4. -p- RAKAM FORMATI
    match = re.search(r'-p-(\d{10,})', url)
    if match:
        return match.group(1)
    
    # 5. /product/ RAKAM FORMATI
    match = re.search(r'/product/(\d{10,})', url)
    if match:
        return match.group(1)
    
    # 6. HİÇBİRİ YOKSA HATA
    raise ValidationException(f"URL'den ID çıkarılamadı: {url}")



def parse_price(price_str: Any) -> float:
    """Fiyat string'ini float'a çevir (aralıklı fiyatları da işler)"""
    if price_str is None:
        return 0.0
    
    price_str = str(price_str)
    
    try:
        if "-" in price_str:
            # "3.86-14.76" -> minimum 3.86
            return float(price_str.split("-")[0].strip())
        else:
            return float(price_str)
    except (ValueError, TypeError):
        logger.warning(f"Fiyat parse edilemedi: {price_str}")
        return 0.0

async def _extract_variants(cj_data: Dict) -> List[Dict]:
    """CJ varyantlarını çıkar"""
    variants = []
    
    # Attribute'ları çıkar (renk, beden vb.)
    if "productAttribute" in cj_data:
        for attr in cj_data.get("productAttribute", []):
            variants.append({
                "name": attr.get("attributeName", ""),
                "values": attr.get("attributeValue", "").split(",")
            })
    
    # SKU'ları çıkar (direkt "variants" array'i varsa)
    if "variants" in cj_data and cj_data.get("variants"):
        skus = []
        for sku in cj_data.get("variants", []):
            skus.append({
                "vid": sku.get("vid"),
                "sku": sku.get("variantSku"),
                "price": parse_price(sku.get("variantSellPrice")),
                "weight": sku.get("variantWeight"),
                "image": sku.get("variantImage")
            })
        if skus:
            variants.append({
                "name": "Varyantlar",
                "skus": skus
            })
    
    return variants

async def _get_shipping_methods(product_id: str, access_token: str) -> List[Dict]:
    """Ürün için kargo metodlarını getir"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{CJ_BASE_URL}/product/shipping",
                params={"pid": product_id},
                headers={"CJ-Access-Token": access_token}
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 200 and data.get("data"):
                    shipping_methods = []
                    for method in data.get("data", []):
                        shipping_methods.append({
                            "method": method.get("shippingMethod", "CJ Standard"),
                            "price": float(method.get("shippingCost", 5.99)),
                            "currency": "USD",
                            "estimated_days": method.get("estimatedDays", "7-15 days"),
                            "from_location": method.get("warehouse", "China")
                        })
                    return shipping_methods
    except Exception as e:
        logger.error(f"Error fetching shipping methods: {e}")
    
    # Fallback shipping method
    return [{
        "method": "CJ Standard Shipping",
        "price": 5.99,
        "currency": "USD",
        "estimated_days": "7-15 days",
        "from_location": "China"
    }]

# ==================== ENDPOINTS ====================

@router.post("/fetch-product")
async def fetch_cj_product(
    request: CJFetchRequest,
    current_user: dict = Depends(get_current_user_clean)
):
    """
    CJ'den ürün bilgisi getir (URL veya PID ile)
    """
    logger.info(f"📦 CJ fetch-product called by {current_user['email']}")
    
    if not CJ_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="CJ API key not configured"
        )
    
    if not request.url and not request.product_id:
        raise ValidationException(detail="url or product_id required")
    
    try:
        # 1. Access token al
        access_token = await get_cj_access_token()
        
        # 2. Product ID'yi bul
        product_id = request.product_id
        if request.url:
            product_id = extract_product_id_from_url(request.url)
        
        logger.info(f"🔍 Fetching product ID: {product_id}")
        
        # 3. CJ API'den ürün detayını getir
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{CJ_BASE_URL}/product/query",
                params={"pid": product_id},
                headers={"CJ-Access-Token": access_token}
            )
            
            if response.status_code != 200:
                logger.error(f"❌ CJ API error: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"CJ API error: {response.text}"
                )
            
            data = response.json()
            
            if data.get("code") != 200:
                raise HTTPException(
                    status_code=400,
                    detail=f"CJ API error: {data.get('message', 'Unknown error')}"
                )
            
            result = data.get("data", {})
            
            # 4. Kargo metodlarını getir
            shipping_methods = await _get_shipping_methods(product_id, access_token)
            
            # 5. Varyantları çıkar
            variants = await _extract_variants(result)
            
            # 6. Fiyatı parse et
            price = parse_price(result.get("sellPrice"))
            compare_price = parse_price(result.get("marketPrice")) if result.get("marketPrice") else None
            
            # 7. Resimleri düzenle
            images = []
            if result.get("productImageSet"):
                images = result.get("productImageSet")
            elif result.get("productImage"):
                # JSON string olabilir
                img_str = result.get("productImage")
                if img_str.startswith('['):
                    try:
                        import json
                        images = json.loads(img_str)
                    except:
                        images = [img_str]
                else:
                    images = [img_str]
            
            # 8. Normalize et
            normalized = {
                "supplier": "cj",
                "supplier_product_id": result.get("pid", product_id),
                "name": result.get("productNameEn", result.get("productName", "")),
                "description": result.get("description", ""),
                "price": price,
                "compare_price": compare_price,
                "currency": "USD",
                "images": images,
                "categories": [result.get("categoryName", "")],
                "variants": variants,
                "shipping_methods": shipping_methods,
                "stock_status": "in_stock",
                "product_url": request.url or f"https://cjdropshipping.com/product/{product_id}.html",
                "weight": result.get("productWeight"),
                "size": None
            }
            
            logger.info(f"✅ CJ product fetched: {normalized['name'][:50]}...")
            
            return {
                "success": True,
                "product": normalized
            }
            
    except ValidationException:
        raise
    except HTTPException:
        raise
    except httpx.RequestError as e:
        logger.error(f"❌ CJ connection error: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"CJ connection error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"❌ Error fetching CJ product: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )


@router.post("/import-product", response_model=Dict[str, Any])
async def import_cj_product(
    request: ImportProductRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_verified_user)
):
    """CJ'den getirilen ürünü mağazaya ekle"""
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
                "supplier": "cj",
                "supplier_product_id": request.supplier_product_id,
                "variants": request.variants,
                "shipping_methods": request.shipping_methods
            },
            status=ProductStatus.DRAFT.value,
            is_approved=True,
            created_at=datetime.utcnow()
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
        
        logger.info(f"✅ CJ product imported: {product.name}")
        
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
        logger.error(f"❌ Error importing CJ product: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Could not import product: {str(e)}"
        )


@router.get("/search", response_model=Dict[str, Any])
async def search_cj_products(
    query: str = Query(..., min_length=2),
    category_id: Optional[str] = Query(None, description="Kategori ID'si"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum fiyat"),
    max_price: Optional[float] = Query(None, ge=0, description="Maksimum fiyat"),
    sort_by: str = Query("relevance", regex="^(relevance|price_asc|price_desc|newest)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    current_user: dict = Depends(get_current_user_clean)
):
    """
    CJ'de ürün ara - GELİŞTİRİLMİŞ VERSİYON
    - query: aranan kelime
    - category_id: kategori filtresi
    - min_price/max_price: fiyat aralığı
    - sort_by: sıralama
    """
    if not CJ_API_KEY:
        raise HTTPException(status_code=500, detail="CJ API key not configured")
    
    try:
        # 1. Access token al
        access_token = await get_cj_access_token()
        
        # 2. Arama parametrelerini hazırla
        params = {
            "keyword": query,
            "pageNum": page,
            "pageSize": limit
        }
        
        # 3. Kategori filtresi ekle (CJ API'sinde categoryId varsa)
        if category_id:
            # CJ'de kategori ID'si farklı olabilir, mapping yapalım
            category_mapping = {
                "electronics": "1001",  # Örnek ID'ler
                "clothing": "1002",
                "home": "1003",
                "sports": "1004",
                "toys": "1005",
                "beauty": "1006",
                "jewelry": "1007",
                "shoes": "1008",
                "bags": "1009"
            }
            cj_category_id = category_mapping.get(category_id)
            if cj_category_id:
                params["categoryId"] = cj_category_id
        
        # 4. Fiyat filtresi ekle
        if min_price is not None:
            params["minPrice"] = min_price
        if max_price is not None:
            params["maxPrice"] = max_price
        
        # 5. Sıralama
        sort_mapping = {
            "relevance": "0",      # En iyi eşleşme
            "price_asc": "2_asc",   # Fiyat artan
            "price_desc": "2_desc", # Fiyat azalan
            "newest": "3_desc"      # En yeni
        }
        params["sort"] = sort_mapping.get(sort_by, "0")
        
        # 6. CJ API'ye istek at
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{CJ_BASE_URL}/product/list",
                params=params,
                headers={"CJ-Access-Token": access_token}
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="CJ API error")
            
            data = response.json()
            
            if data.get("code") != 200:
                raise HTTPException(status_code=400, detail=data.get("message", "Unknown error"))
            
            result = data.get("data", {})
            products = result.get("list", [])
            
            # 7. Sonuçları normalize et
            normalized = []
            for p in products:
                normalized.append({
                    "supplier_product_id": p.get("pid"),
                    "name": p.get("productNameEn", p.get("productName")),
                    "price": parse_price(p.get("sellPrice")),
                    "image": p.get("productImage"),
                    "category": p.get("categoryName"),
                    "stock_status": "in_stock" if p.get("stock", 0) > 0 else "out_of_stock"
                })
            
            return {
                "success": True,
                "total": result.get("total", 0),
                "page": page,
                "limit": limit,
                "products": normalized
            }
            
    except httpx.RequestError as e:
        logger.error(f"❌ CJ connection error: {e}")
        raise HTTPException(status_code=502, detail=f"CJ connection error: {str(e)}")
    except Exception as e:
        logger.error(f"❌ Error searching CJ products: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

# ==================== KULLANICI CJ HESAP YÖNETİMİ ====================

@router.post("/connect", response_model=CJConnectResponse)
async def connect_cj_account(
    request: CJConnectRequest,  # schemas/user.py'den
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user_clean)
):
    """
    Kullanıcının CJ hesabını bağla (Puppeteer otomasyonu ile)
    - Kullanıcıdan CJ email/şifre al
    - Puppeteer ile CJ'ye gir, API Key al
    - Kullanıcının veritabanına kaydet
    """
    from services.cj_automation import auto_get_cj_api_key  # Sonra yazacağız
    
    try:
        # 1. Kullanıcı zaten bağlı mı kontrol et
        if current_user.get('cj_api_key'):
            raise HTTPException(
                status_code=400,
                detail="CJ hesabı zaten bağlı. Önce bağlantıyı kesin."
            )
        
        # 2. Puppeteer ile CJ'den API Key al
        result = await auto_get_cj_api_key(
            email=request.cj_email,
            password=request.cj_password
        )
        
        if not result['success']:
            raise HTTPException(
                status_code=400,
                detail=f"CJ bağlantı hatası: {result.get('error')}"
            )
        
        # 3. Veritabanına kaydet
        user_id = uuid.UUID(current_user['sub'])
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                cj_email=request.cj_email,
                cj_api_key=result['api_key'],
                cj_api_secret=result.get('api_secret'),
                cj_connected_at=datetime.utcnow()
            )
        )
        await db.commit()
        
        logger.info(f"✅ CJ account connected for user {current_user['email']}")
        
        return CJConnectResponse(
            success=True,
            message="CJ hesabı başarıyla bağlandı",
            connected_at=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"❌ CJ connect error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=CJStatusResponse)
async def get_cj_status(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user_clean)
):
    """
    Kullanıcının CJ bağlantı durumunu getir
    """
    user_id = uuid.UUID(current_user['sub'])
    
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return CJStatusResponse(
        connected=user.is_cj_connected,
        email=user.cj_email,
        connected_at=user.cj_connected_at,
        last_sync=user.cj_last_sync
    )


@router.post("/disconnect", response_model=CJDisconnectResponse)
async def disconnect_cj_account(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user_clean)
):
    """
    Kullanıcının CJ bağlantısını kes
    """
    user_id = uuid.UUID(current_user['sub'])
    
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(
            cj_email=None,
            cj_api_key=None,
            cj_api_secret=None,
            cj_connected_at=None,
            cj_last_sync=None
        )
    )
    await db.commit()
    
    logger.info(f"✅ CJ account disconnected for user {current_user['email']}")
    
    return CJDisconnectResponse(
        success=True,
        message="CJ bağlantısı kesildi"
    )


@router.post("/sync")
async def sync_cj_products(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_verified_user)
):
    """
    Kullanıcının CJ ürünlerini senkronize et
    - Stok güncelle
    - Fiyat güncelle
    - Yeni ürünleri çek
    """
    user_id = uuid.UUID(current_user['sub'])
    
    # 1. Kullanıcının CJ bağlantısı var mı?
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user or not user.is_cj_connected:
        raise HTTPException(
            status_code=400,
            detail="CJ hesabı bağlı değil"
        )
    
    # 2. CJ API Key ile token al
    access_token = await get_cj_access_token_with_user_key(user.cj_api_key)
    
    # 3. Kullanıcının mağazalarını getir
    shops_result = await db.execute(
        select(Shop).where(Shop.user_id == user_id)
    )
    shops = shops_result.scalars().all()
    
    if not shops:
        raise HTTPException(status_code=400, detail="Önce bir mağaza oluşturun")
    
    # 4. Her mağaza için ürünleri güncelle
    updated_count = 0
    for shop in shops:
        # Burada ürün güncelleme mantığı
        pass
    
    # 5. Son sync zamanını güncelle
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(cj_last_sync=datetime.utcnow())
    )
    await db.commit()
    
    return {
        "success": True,
        "message": f"{updated_count} ürün güncellendi",
        "last_sync": datetime.utcnow()
    }
    


# ==================== KULLANICI CJ HESAP YÖNETİMİ ====================

# Kullanıcıya özel token cache


# ==================== KULLANICI TOKEN YÖNETİMİ ====================

# Kullanıcıya özel token cache
_user_tokens = {}  # {cache_key: {"token": "...", "expiry": ...}}

async def get_cj_access_token_with_user_key(cj_api_key: str) -> str:
    """
    Kullanıcının kendi CJ API Key'i ile token al
    """
    # Cache'de var mı kontrol et
    cache_key = f"user_token_{cj_api_key[:20]}"
    if cache_key in _user_tokens:
        token_data = _user_tokens[cache_key]
        if datetime.now() < token_data['expiry']:
            logger.info(f"✅ Using cached user token")
            return token_data['token']
    
    logger.info(f"🔄 Getting new token for user...")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{CJ_BASE_URL}/authentication/getAccessToken",
                json={"apiKey": cj_api_key}
            )
            
            if response.status_code != 200:
                raise Exception(f"Token alınamadı: {response.status_code}")
            
            data = response.json()
            
            if data.get("code") != 200:
                raise Exception(f"Token alınamadı: {data.get('message')}")
            
            result = data.get("data", {})
            token = result.get("accessToken")
            
            # Expiry hesapla
            expiry_str = result.get("accessTokenExpiryDate")
            if expiry_str:
                expiry_str = expiry_str.replace("+08:00", "")
                expiry = datetime.fromisoformat(expiry_str) - timedelta(hours=8)
            else:
                expiry = datetime.now() + timedelta(days=14)
            
            # Cache'e kaydet
            _user_tokens[cache_key] = {
                "token": token,
                "expiry": expiry
            }
            
            return token
            
    except Exception as e:
        logger.error(f"❌ User token error: {e}")
        raise