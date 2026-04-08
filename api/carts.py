"""
Cart management API endpoints
Add/remove items, update quantities, calculate totals
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import json
from database.database import get_db
from helpers.security import get_current_active_user, get_current_user_clean
from nix.dependencies import rate_limiter
from nix.exceptions import (
    NotFoundException,
    ValidationException,
    ForbiddenException,
    InsufficientStockException
)
from nix.logging import logger
from config.config import settings
from models.product import Product, ProductStatus
from models.shop import Shop, ShopStatus
from routers.carts import (
    CartCreate,
    CartUpdate,
    CartResponse,
    CartItemAdd,
    CartItemCreate,
    CartItemUpdate,
    CartCheckoutPreview
)
from uuid import UUID


from models.cart import Cart, CartItem, CartStatus  # CartStatus'u da ekle

import uuid
import logging
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/carts", tags=["carts"])
from sqlalchemy.orm import joinedload
from datetime import timedelta, datetime
# ==================== CART MANAGEMENT ====================

@router.get("/my", response_model=CartResponse)
async def get_my_cart(
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's cart.
    Creates cart if it doesn't exist.
    """
    try:
        cart_id = UUID(current_user["sub"])
        
        # Get cart items from database (in production, use Redis or cart table)
        # For MVP, we'll use a simple in-memory approach
        cart_items = await get_cart_items(cart_id, db)
        
        # Calculate totals
        totals = await calculate_cart_totals(cart_items, db)
        
        cart_data = {
            "id": cart_id,
            "cart_token": str(cart_id),  # ✅ String'e çevir
            "user_id": current_user["sub"],
            "items": cart_items,
            "items_subtotal": totals.get("items_subtotal", 0),
            "shipping_total": totals.get("shipping_total", 0),
            "tax_total": totals.get("tax_total", 0),
            "order_total": totals.get("order_total", 0),
            "discount_total": 0.0,
            "coupon_code": None,
            "last_activity_at": datetime.utcnow(),  # ✅ EKLE
            "expires_at": datetime.utcnow() + timedelta(days=7),  # ✅ EKLE
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "item_count": len(cart_items),
            "shop_count": len(set(item.get("shop_id") for item in cart_items if item.get("shop_id")))
        }
        
        return CartResponse(**cart_data)
        
    except Exception as e:
        logger.error(f"Error getting cart: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve cart"
        )


async def get_cart_items(cart_id: UUID, db: AsyncSession):
    result = await db.execute(
        select(CartItem).where(CartItem.cart_id == cart_id)
    )
    items = result.scalars().all()
    return [item.to_dict() for item in items]


@router.post("/items", response_model=CartResponse)
async def add_to_cart(
    item_data: CartItemAdd,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    try:
        # Validate product
        result = await db.execute(
            select(Product).where(
                Product.id == item_data.product_id,
                Product.status == ProductStatus.PUBLISHED,
                Product.is_approved == True
            ).options(joinedload(Product.shop))
        )
        product = result.scalar_one_or_none()
        
        if not product:
            raise NotFoundException(
                resource_type="Product",
                identifier=item_data.product_id,
                detail="Product not found or not available"
            )
        
        if not product.shop or product.shop.status != ShopStatus.ACTIVE:
            raise ValidationException(detail="Shop is not active")
        
        if product.product_type == "physical":
            if not product.is_in_stock:
                raise InsufficientStockException(
                    product_name=product.name,
                    requested=item_data.quantity,
                    available=product.stock_quantity
                )
            if item_data.quantity > product.stock_quantity and not product.allows_backorder:
                raise InsufficientStockException(
                    product_name=product.name,
                    requested=item_data.quantity,
                    available=product.stock_quantity
                )
        
        # Get or create cart
        cart_id = UUID(current_user["sub"])
        
        # ÖNCE CART'I BUL VEYA OLUŞTUR
        result = await db.execute(select(Cart).where(Cart.id == cart_id))
        cart = result.scalar_one_or_none()
        
        if not cart:
            cart = Cart(
                cart_token=cart_id,
                user_id=cart_id,
                status="active"
            )
            db.add(cart)
            await db.flush()  # SADECE FLUSH, COMMIT YOK
        
        # ŞİMDİ ITEM'E BAK
        result = await db.execute(
            select(CartItem).where(
                CartItem.cart_id == cart_id,
                CartItem.product_id == item_data.product_id
            )
        )
        existing_item = result.scalar_one_or_none()
        
        if existing_item:
            new_quantity = existing_item.quantity + item_data.quantity
            
            if product.product_type == "physical":
                if new_quantity > product.stock_quantity and not product.allows_backorder:
                    raise InsufficientStockException(
                        product_name=product.name,
                        requested=new_quantity,
                        available=product.stock_quantity
                    )
            
            existing_item.quantity = new_quantity
        else:
            new_item = CartItem(
                cart_id=cart_id,
                product_id=product.id,
                shop_id=product.shop_id,
                product_name=product.name,
                product_slug=product.slug,
                product_type=product.product_type.value,
                quantity=item_data.quantity,
                unit_price=Decimal(str(product.base_price)),
            )
            db.add(new_item)
        
        # Update product cart add count
        await db.execute(
            update(Product)
            .where(Product.id == item_data.product_id)
            .values(cart_add_count=Product.cart_add_count + 1)
        )
        
        # TEK COMMIT
        await db.commit()
        
        # Get updated cart items
        result = await db.execute(
            select(CartItem).where(CartItem.cart_id == cart_id)
        )
        cart_items = result.scalars().all()
        cart_items_dict = [item.to_dict() for item in cart_items]
        totals = await calculate_cart_totals(cart_items_dict, db)
        
        cart_data = {
            "id": cart_id,
            "cart_token": str(cart_id),
            "user_id": cart_id,
            "items": cart_items_dict,
            "items_subtotal": totals.get("items_subtotal", 0),
            "shipping_total": totals.get("shipping_total", 0),
            "tax_total": totals.get("tax_total", 0),
            "order_total": totals.get("order_total", 0),
            "discount_total": 0.0,
            "coupon_code": None,
            "last_activity_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(days=7),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "item_count": len(cart_items_dict),
            "shop_count": len(set(item.get("shop_id") for item in cart_items_dict if item.get("shop_id")))
        }
        
        logger.info(f"Item added to cart: {product.name} x{item_data.quantity} by {current_user['email']}")
        return CartResponse(**cart_data)
        
    except (NotFoundException, ValidationException, InsufficientStockException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error adding to cart: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not add item to cart"
        )

@router.put("/items/{product_id}", response_model=CartResponse)
async def update_cart_item(
    product_id: str,
    item_update: CartItemUpdate,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Update cart item quantity or remove item.
    """
    try:
        # Get current cart
        cart_id = UUID(current_user["sub"])
        cart_items = await get_cart_items(cart_id, db)
        
        # Find item in cart
        item_index = -1
        for i, item in enumerate(cart_items):
            if item.get("product_id") == product_id:
                item_index = i
                break
        
        if item_index < 0:
            raise NotFoundException(
                resource_type="Cart item",
                identifier=product_id
            )
        
        # Get product info
        result = await db.execute(
            select(Product).where(Product.id == product_id)
        )
        product = result.scalar_one_or_none()
        
        if not product:
            # Product no longer exists, remove from cart
            cart_items.pop(item_index)
        else:
            if item_update.quantity <= 0:
                # Remove item
                cart_items.pop(item_index)
            else:
                # Update quantity
                # Check stock for physical products
                if product.product_type == "physical":
                    if item_update.quantity > product.stock_quantity and not product.allows_backorder:
                        raise InsufficientStockException(
                            product_name=product.name,
                            requested=item_update.quantity,
                            available=product.stock_quantity
                        )
                
                cart_items[item_index]["quantity"] = item_update.quantity
                cart_items[item_index]["item_total"] = float(product.base_price * Decimal(str(item_update.quantity)))
        
        # Save cart
        # await save_cart_items(cart_id, cart_items)
        
        # Calculate totals
        totals = await calculate_cart_totals(cart_items, db)
        
        cart_data = {
            "id": cart_id,
            "cart_token": str(cart_id),
            "user_id": current_user["sub"],
            "items": cart_items,
            **totals,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "item_count": len(cart_items),
            "shop_count": len(set(item.get("shop_id") for item in cart_items if item.get("shop_id")))
        }
        
        action = "removed" if item_update.quantity <= 0 else "updated"
        logger.info(f"Cart item {action}: {product_id} by {current_user['email']}")
        
        return CartResponse(**cart_data)
        
    except (NotFoundException, ValidationException, InsufficientStockException):
        raise
    except Exception as e:
        logger.error(f"Error updating cart item: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update cart item"
        )


@router.delete("/items/{product_id}", response_model=CartResponse)
async def remove_from_cart(
    product_id: str,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Remove item from cart.
    """
    try:
        # Get current cart
        cart_id = UUID(current_user["sub"])
        cart_items = await get_cart_items(cart_id, db)
        
        # Find and remove item
        new_items = [item for item in cart_items if item.get("product_id") != product_id]
        
        if len(new_items) == len(cart_items):
            raise NotFoundException(
                resource_type="Cart item",
                identifier=product_id
            )
        
        # Save cart
        # await save_cart_items(cart_id, new_items)
        
        # Calculate totals
        totals = await calculate_cart_totals(new_items, db)
        
        cart_data = {
            "id": cart_id,
            "user_id": current_user["sub"],
            "items": new_items,
            "cart_token": str(cart_id),
            **totals,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "item_count": len(new_items),
            "shop_count": len(set(item.get("shop_id") for item in new_items if item.get("shop_id")))
        }
        
        logger.info(f"Item removed from cart: {product_id} by {current_user['email']}")
        
        return CartResponse(**cart_data)
        
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error removing from cart: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not remove item from cart"
        )


@router.delete("/", response_model=CartResponse)
async def clear_cart(
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Clear all items from cart.
    """
    try:
        cart_id = UUID(current_user["sub"])
        empty_cart = []
        cart_data = {
            "id": cart_id,
            "user_id": current_user["sub"],
            "cart_token": str(cart_id),
            "items": empty_cart,
            "items_subtotal": 0.0,
            "shipping_total": 0.0,
            "tax_total": 0.0,
            "order_total": 0.0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "item_count": 0,
            "shop_count": 0
        }
        
        logger.info(f"Cart cleared by {current_user['email']}")
        return CartResponse(**cart_data)
    except Exception as e:
        logger.error(f"Error clearing cart: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not clear cart"
        )


# ==================== CART CALCULATIONS ====================

async def calculate_cart_totals(cart_items: List[Dict[str, Any]], db: AsyncSession) -> Dict[str, float]:
    """
    Calculate cart totals including shipping and taxes.
    """
    if not cart_items:
        return {
            "items_subtotal": 0.0,
            "shipping_total": 0.0,
            "tax_total": 0.0,
            "order_total": 0.0
        }
    
    # Calculate items subtotal
    items_subtotal = sum(Decimal(str(item.get("item_total", 0))) for item in cart_items)
    shop_items = {}
    for item in cart_items:
        shop_id = item.get("shop_id")
        if shop_id not in shop_items:
            shop_items[shop_id] = []
        shop_items[shop_id].append(item)
    
    # Shipping calculation (simplified for MVP)
    # $5 per shop with physical products, free for digital-only shops
    shipping_total = Decimal('0.00')
    for shop_id, items in shop_items.items():
        has_physical = any(item.get("product_type") == "physical" for item in items)
        if has_physical:
            shipping_total += Decimal('5.00')
    # Tax calculation (simplified: 10%)
    tax_rate = Decimal('0.10')
    tax_total = items_subtotal * tax_rate
    
    # Order total
    order_total = items_subtotal + shipping_total + tax_total
    
    return {
        "items_subtotal": float(items_subtotal),
        "shipping_total": float(shipping_total),
        "tax_total": float(tax_total),
        "order_total": float(order_total)
    }
    
async def get_cart_data(cart_id: str, db: AsyncSession, current_user: dict) -> dict:
    """Get full cart data from database."""
    from models.cart import Cart, CartItem  # import'u burada da yapabilirsin
    cart_uuid = UUID(cart_id)  # Önce UUID'ye çevir
    result = await db.execute(
        select(Cart).where(Cart.id == cart_uuid)
    )
    cart = result.scalar_one_or_none()
    
    if not cart:
        cart = Cart(
            cart_token=cart_uuid,  # UUID
            status=CartStatus.ACTIVE,
            user_id=UUID(current_user["sub"])
        )
        db.add(cart)
        await db.flush()
    
    # Get cart items
    result = await db.execute(
        select(CartItem).where(CartItem.cart_id == cart_uuid)
    )
    items = result.scalars().all()
    
    totals = await calculate_cart_totals([item.to_dict() for item in items], db)
    
    return {
        "id": cart_id,
        "cart_token": str(cart_id),
        "user_id": current_user["sub"],
        "items": [item.to_dict() for item in items],
        "items_subtotal": totals.get("items_subtotal", 0),
        "shipping_total": totals.get("shipping_total", 0),
        "tax_total": totals.get("tax_total", 0),
        "order_total": totals.get("order_total", 0),
        "discount_total": 0.0,
        "coupon_code": None,
        "last_activity_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=7),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "item_count": len(items),
        "shop_count": len(set(item.shop_id for item in items))
    }


@router.get("/checkout/preview", response_model=CartCheckoutPreview)
async def checkout_preview(
    shipping_address: Optional[Dict[str, Any]] = None,
    coupon_code: Optional[str] = None,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Get checkout preview with calculated totals.
    """
    try:
        # Get current cart
        cart_id = UUID(current_user["sub"])
        cart_items = await get_cart_items(cart_id, db)
        
        if not cart_items:
            raise ValidationException(
                detail="Cart is empty"
            )
        
        # Validate cart items
        validated_items = []
        for item in cart_items:
            product_id = item.get("product_id")
            quantity = item.get("quantity", 1)
            
            result = await db.execute(
                select(Product).where(
                    Product.id == product_id,
                    Product.status == ProductStatus.PUBLISHED,
                    Product.is_approved == True
                )
            )
            product = result.scalar_one_or_none()
            
            if not product:
                raise ValidationException(
                    detail=f"Product {product_id} is no longer available"
                )
            
            # Check stock
            if product.product_type == "physical":
                if not product.is_in_stock:
                    raise InsufficientStockException(
                        product_name=product.name,
                        requested=quantity,
                        available=product.stock_quantity
                    )
                
                if quantity > product.stock_quantity and not product.allows_backorder:
                    raise InsufficientStockException(
                        product_name=product.name,
                        requested=quantity,
                        available=product.stock_quantity
                    )
            
            validated_items.append(item)
        
        # Calculate totals
        totals = await calculate_cart_totals(validated_items, db)
        
        # Apply coupon if provided (simplified for MVP)
        discount_total = Decimal('0.00')
        if coupon_code:
            # In production, validate coupon
            if coupon_code.upper() == "WELCOME10":
                discount_total = Decimal(str(totals["items_subtotal"])) * Decimal('0.10')
                totals["order_total"] = float(Decimal(str(totals["order_total"])) - discount_total)
        
        # Check if user owns any shops in cart
        shop_ids = set(item.get("shop_id") for item in validated_items if item.get("shop_id"))
        result = await db.execute(
            select(Shop).where(
                Shop.id.in_(list(shop_ids)),
                Shop.owner_id == current_user["sub"]
            )
        )
        user_shops = result.scalars().all()
        
        if user_shops:
            shop_names = [shop.name for shop in user_shops]
            raise ValidationException(
                detail=f"Cannot checkout from your own shops: {', '.join(shop_names)}"
            )
        
        preview_data = {
            "cart_id": cart_id,
            "items": validated_items,
            **totals,
            "discount_total": float(discount_total),
            "coupon_code": coupon_code,
            "coupon_applied": coupon_code is not None,
            "shipping_address_required": any(item.get("product_type") == "physical" for item in validated_items),
            "item_count": len(validated_items),
            "shop_count": len(shop_ids),
            "estimated_delivery": (datetime.utcnow() + timedelta(days=7)).isoformat() if shop_ids else None
        }
        
        return CartCheckoutPreview(**preview_data)
        
    except (ValidationException, InsufficientStockException):
        raise
    except Exception as e:
        logger.error(f"Error generating checkout preview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate checkout preview"
        )


# ==================== CART MIGRATION/MERGE ====================

@router.post("/merge")
async def merge_carts(
    guest_cart: Optional[List[Dict[str, Any]]] = None,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Merge guest cart with user cart after login.
    """
    try:
        if not guest_cart:
            return {"message": "No guest cart to merge"}
        
        cart_id = f"cart_{current_user['sub']}"
        user_cart_items = await get_cart_items(cart_id, db)
        
        merged_items = user_cart_items.copy()
        
        for guest_item in guest_cart:
            product_id = guest_item.get("product_id")
            quantity = guest_item.get("quantity", 1)
            
            # Check if product exists
            result = await db.execute(
                select(Product).where(
                    Product.id == product_id,
                    Product.status == ProductStatus.PUBLISHED,
                    Product.is_approved == True
                )
            )
            product = result.scalar_one_or_none()
            
            if not product:
                continue
            
            # Check if already in user cart
            found = False
            for i, user_item in enumerate(merged_items):
                if user_item.get("product_id") == product_id:
                    # Update quantity
                    new_quantity = user_item["quantity"] + quantity
                    
                    # Check stock
                    if product.product_type == "physical":
                        if new_quantity > product.stock_quantity and not product.allows_backorder:
                            new_quantity = product.stock_quantity
                    
                    merged_items[i]["quantity"] = new_quantity
                    merged_items[i]["item_total"] = float(product.base_price * Decimal(str(new_quantity)))
                    found = True
                    break
            
            if not found:
                # Add new item
                new_item = {
                    "product_id": product.id,
                    "shop_id": product.shop_id,
                    "product_name": product.name,
                    "product_type": product.product_type.value,
                    "quantity": quantity,
                    "unit_price": float(product.base_price),
                    "item_total": float(product.base_price * Decimal(str(quantity))),
                    "product_data": product.to_public_dict(),
                    "added_at": datetime.utcnow().isoformat()
                }
                merged_items.append(new_item)
        
        # Save merged cart
        # await save_cart_items(cart_id, merged_items)
        
        # Calculate totals
        totals = await calculate_cart_totals(merged_items, db)
        
        logger.info(f"Carts merged for user {current_user['email']}, items: {len(merged_items)}")
        
        return {
            "message": "Carts merged successfully",
            "merged_items": len(merged_items),
            "totals": totals
        }
        
    except Exception as e:
        logger.error(f"Error merging carts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not merge carts"
        )

