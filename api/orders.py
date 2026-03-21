"""
Order management API endpoints
Create, view, update orders, manage order fulfillment
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.orm import joinedload, selectinload
import httpx
from database.database import get_db
from helpers.security import (
    get_current_active_user, 
    get_current_verified_user,
    get_current_user_clean
)
from fastapi import Depends, HTTPException, status
from helpers.security import security_manager, oauth2_scheme
from nix.dependencies import (
    PaginationParams, 
    SearchParams,
    require_shop_ownership,
    require_product_ownership,
    BulkOperationValidator
)
from nix.exceptions import (
    NotFoundException,
    ValidationException,
    ForbiddenException,
    InsufficientStockException,
    PaymentRequiredException
)
from nix.logging import logger, audit_logger, performance_logger
from config.config import settings
from models.order import Order, OrderStatus, OrderType, FulfillmentStatus, PaymentMethod
from models.product import Product, ProductStatus
from models.shop import Shop, ShopStatus
from models.user import User
from routers.orders import (
    OrderCreate,
    OrderUpdate,
    OrderResponse,
    OrderCustomer,
    OrderSeller,
    OrderStatusUpdate,
    OrderRefundRequest,
    OrderSearchParams,
    OrderBulkAction,
    OrderFulfillmentRequest,
    OrderDeliveryConfirmation
)

router = APIRouter(prefix="/orders", tags=["orders"])

# ==================== ORDER CREATION & CHECKOUT ====================

async def require_admin(
    token: str = Depends(oauth2_scheme)
) -> dict:
    """Admin yetkisi kontrolü"""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    payload = security_manager.decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )
    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return payload

async def require_seller(
    token: str = Depends(oauth2_scheme)
) -> dict:
    """Seller yetkisi kontrolü"""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    payload = security_manager.decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )
    if payload.get("role") != "seller":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seller privileges required"
        )
    return payload

async def validate_cart_items(cart_items: List[Dict[str, Any]], db: AsyncSession):
    """
    Validate cart items before creating order.
    """
    validated_items = []
    items_subtotal = Decimal('0.00')
    for item in cart_items:
        product_id = item.get("product_id")
        quantity = item.get("quantity", 1)
        if not product_id or quantity < 1:
            raise ValidationException(
                detail=f"Invalid cart item: {item}"
            )
        result = await db.execute(
            select(Product).where(
                Product.id == product_id,
                Product.status == ProductStatus.PUBLISHED,
                Product.is_approved == True
            ).options(
                joinedload(Product.shop)
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            raise NotFoundException(
                resource_type="Product",
                identifier=product_id,
                detail="Product not found or not available"
            )
        if product.product_type == "physical" and not product.is_in_stock:
            raise InsufficientStockException(
                product_name=product.name,
                requested=quantity,
                available=product.stock_quantity
            )
        if product.product_type == "physical" and quantity > product.stock_quantity and not product.allows_backorder:
            raise InsufficientStockException(
                product_name=product.name,
                requested=quantity,
                available=product.stock_quantity
            )
        item_price = product.current_price
        item_total = item_price * Decimal(str(quantity))
        validated_item = {
            "product_id": product.id,
            "shop_id": product.shop_id,
            "product_name": product.name,
            "product_type": product.product_type.value,
            "quantity": quantity,
            "unit_price": float(item_price),
            "item_total": float(item_total),
            "product_data": product.to_public_dict()
        }
        validated_items.append(validated_item)
        items_subtotal += item_total
    return validated_items, items_subtotal

async def calculate_order_totals(
    validated_items: List[Dict[str, Any]],
    shipping_address: Optional[Dict[str, Any]] = None,
    coupon_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate order totals including taxes, shipping, fees.
    """
    # Group items by shop
    shop_items = {}
    for item in validated_items:
        shop_id = item["shop_id"]
        if shop_id not in shop_items:
            shop_items[shop_id] = []
        shop_items[shop_id].append(item)
    items_subtotal = sum(Decimal(str(item["item_total"])) for item in validated_items)
    shipping_total = Decimal('0.00')
    for shop_id, items in shop_items.items():
        has_physical = any(item["product_type"] == "physical" for item in items)
        if has_physical:
            shipping_total += Decimal('5.00')
    tax_rate = Decimal('0.10')
    tax_total = items_subtotal * tax_rate
    platform_fee_rate = Decimal('0.05')
    platform_fee = items_subtotal * platform_fee_rate
    order_total = items_subtotal + shipping_total + tax_total
    return {
        "items_subtotal": items_subtotal,
        "shipping_total": shipping_total,
        "tax_total": tax_total,
        "platform_fee": platform_fee,
        "order_total": order_total,
        "shop_items": shop_items,
        "item_count": len(validated_items),
        "shop_count": len(shop_items)
    }

@router.post("/", response_model=OrderResponse)
async def create_order(
    order_data: OrderCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new order from cart.
    """
    try:
        cart_items = order_data.cart_items or []
        
        if not cart_items:
            raise ValidationException(
                detail="Cart is empty"
            )
        validated_items, items_subtotal = await validate_cart_items(cart_items, db)
        
        # 2. Calculate order totals
        totals = await calculate_order_totals(
            validated_items=validated_items,
            shipping_address=order_data.shipping_address if not order_data.shipping_same_as_billing else None
        )
        
        # 3. Check if user has any active shops in the order (prevent self-purchase)
        shop_ids = list(totals["shop_items"].keys())
        result = await db.execute(
            select(Shop).where(
                Shop.id.in_(shop_ids),
                Shop.owner_id == current_user["sub"],
                Shop.status == ShopStatus.ACTIVE
            )
        )
        user_shops = result.scalars().all()
        
        if user_shops:
            shop_names = [shop.name for shop in user_shops]
            raise ValidationException(
                detail=f"Cannot purchase from your own shops: {', '.join(shop_names)}"
            )
        
        # 4. Create order
        order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{int(datetime.utcnow().timestamp()) % 1000000}"
        
        order = Order(
            order_number=order_number,
            buyer_id=current_user["sub"],
            cart_id=order_data.cart_id,
            customer_email=order_data.customer_email,
            customer_name=order_data.customer_name,
            customer_phone=order_data.customer_phone,
            customer_notes=order_data.customer_notes,
            billing_address=order_data.billing_address,
            shipping_address=order_data.shipping_address or order_data.billing_address,
            shipping_same_as_billing=order_data.shipping_same_as_billing,
            payment_method=order_data.payment_method,
            items_subtotal=totals["items_subtotal"],
            shipping_total=totals["shipping_total"],
            tax_total=totals["tax_total"],
            platform_fee=totals["platform_fee"],
            order_total=totals["order_total"],
            items=validated_items,
            item_count=totals["item_count"],
            order_type="mixed" if len(set(item["product_type"] for item in validated_items)) > 1 
                      else validated_items[0]["product_type"],
            requires_shipping=any(item["product_type"] == "physical" for item in validated_items),
            status=OrderStatus.PENDING,
            fulfillment_status=FulfillmentStatus.UNFULFILLED
        )
        
        db.add(order)
        for item in validated_items:
            product_id = item["product_id"]
            quantity = item["quantity"]
            await db.execute(
                update(Product)
                .where(Product.id == product_id)
                .values(
                    purchase_count=Product.purchase_count + quantity,
                    last_sold_at=datetime.utcnow()
                )
            )
            
            # Update stock for physical products
            result = await db.execute(
                select(Product).where(Product.id == product_id)
            )
            product = result.scalar_one_or_none()
            
            if product and product.product_type == "physical":
                new_stock = product.stock_quantity - quantity
                if new_stock < 0 and not product.allows_backorder:
                    raise InsufficientStockException(
                        product_name=product.name,
                        requested=quantity,
                        available=product.stock_quantity
                    )
                
                await db.execute(
                    update(Product)
                    .where(Product.id == product_id)
                    .values(stock_quantity=new_stock)
                )
        
        # 6. Update shop stats
        for shop_id in shop_ids:
            shop_total = sum(
                Decimal(str(item["item_total"])) 
                for item in validated_items 
                if item["shop_id"] == shop_id
            )
            
            await db.execute(
                update(Shop)
                .where(Shop.id == shop_id)
                .values(
                    total_orders=Shop.total_orders + 1,
                    total_revenue=Shop.total_revenue + shop_total
                )
            )
        
        await db.commit()
        await db.refresh(order)
        
        # 7. Add status log
        status_log = {
            "status": OrderStatus.PENDING.value,
            "timestamp": datetime.utcnow().isoformat(),
            "notes": "Order created",
            "changed_by": "system"
        }
        
        order.status_logs.append(status_log)
        await db.commit()
        
        # 8. Log audit event
        audit_logger.log_payment_event(
            payment_id=str(order.id),
            amount=float(order.order_total),
            currency="USD",
            user_id=current_user["sub"],
            shop_id=shop_ids[0] if shop_ids else None,
            event_type="order_created",
            status="pending"
        )
        
        logger.info(f"Order created: {order.order_number} by {current_user['email']}, total: ${order.order_total}")
        
        # 9. Send email confirmation (background task)
        background_tasks.add_task(
            send_order_confirmation_email,
            order_id=str(order.id),
            customer_email=order.customer_email
        )
        
        return OrderResponse.from_orm(order)
        
    except (
        ValidationException, 
        NotFoundException, 
        InsufficientStockException,
        ForbiddenException
    ):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create order"
        )

async def send_order_confirmation_email(order_id: str, customer_email: str):
    """
    Send order confirmation email (placeholder for Go service).
    """
    try:
        # In production, call Go email service
        # async with httpx.AsyncClient() as client:
        #     await client.post(
        #         "http://go-service:8080/email/send",
        #         json={
        #             "to": customer_email,
        #             "template": "order_confirmation",
        #             "data": {"order_id": order_id}
        #         }
        #     )
        
        logger.info(f"Order confirmation email queued for order {order_id} to {customer_email}")
    except Exception as e:
        logger.error(f"Error sending order confirmation email: {e}")

# ==================== ORDER VIEWING ====================

@router.get("/my", response_model=List[OrderCustomer])
async def get_my_orders(
    status: Optional[OrderStatus] = Query(None),
    shop_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's orders (as buyer).
    """
    try:
        query = select(Order).where(
            Order.buyer_id == current_user["sub"]
        ).options(
            joinedload(Order.shop)
        )
        
        if status:
            query = query.where(Order.status == status)
        
        if shop_id:
            # Get orders containing products from this shop
            query = query.where(
                Order.items.any(f"$.shop_id == '{shop_id}'")
            )
        if date_from:
            query = query.where(Order.created_at >= date_from)
        if date_to:
            query = query.where(Order.created_at <= date_to)
        query = query.order_by(Order.created_at.desc())
        result = await db.execute(query)
        orders = result.scalars().all()
        customer_orders = []
        for order in orders:
            order_dict = OrderCustomer.from_orm(order).dict()
            if order.items:
                first_item = order.items[0]
                shop_info = await get_shop_info(first_item["shop_id"], db)
                if shop_info:
                    order_dict.update(shop_info)
            order_dict.update({
                "can_cancel": order.status in [OrderStatus.PENDING, OrderStatus.PROCESSING],
                "cancel_deadline": order.created_at + timedelta(hours=24) if order.status == OrderStatus.PENDING else None,
                "can_request_refund": order.status == OrderStatus.COMPLETED and order.days_since_creation <= 30,
                "refund_deadline": order.created_at + timedelta(days=30) if order.status == OrderStatus.COMPLETED else None,
                "can_download_digital": order.digital_delivered and order.order_type in ["digital", "mixed"],
                "can_review": order.status == OrderStatus.COMPLETED and order.days_since_creation <= 14,
                "review_deadline": order.created_at + timedelta(days=14) if order.status == OrderStatus.COMPLETED else None
            })
            customer_orders.append(order_dict)
        return customer_orders
    except Exception as e:
        logger.error(f"Error getting user orders: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve your orders"
        )

async def get_shop_info(shop_id: str, db: AsyncSession) -> Optional[Dict[str, Any]]:
    """Get shop info for order display."""
    try:
        result = await db.execute(
            select(Shop).where(Shop.id == shop_id)
        )
        shop = result.scalar_one_or_none()
        if shop:
            return {
                "shop_name": shop.name,
                "shop_slug": shop.slug,
                "shop_logo_url": shop.logo_url,
                "shop_is_verified": shop.is_verified
            }
        return None
    except:
        return None

@router.get("/shop/{shop_id}", response_model=List[OrderSeller])
async def get_shop_orders(
    shop_id: str,
    status: Optional[OrderStatus] = Query(None),
    fulfillment_status: Optional[FulfillmentStatus] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get orders for a specific shop (seller only).
    """
    try:
        # Check shop ownership
        result = await db.execute(
            select(Shop).where(
                Shop.id == shop_id,
                Shop.owner_id == current_user["sub"]
            )
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            raise ForbiddenException(
                detail="You don't have permission to view orders for this shop"
            )
        
        # Get orders containing products from this shop
        query = select(Order).where(
            Order.items.any(f"$.shop_id == '{shop_id}'")
        ).options(
            joinedload(Order.buyer)
        )

        if status:
            query = query.where(Order.status == status)
        if fulfillment_status:
            query = query.where(Order.fulfillment_status == fulfillment_status)
        if date_from:
            query = query.where(Order.created_at >= date_from)
        if date_to:
            query = query.where(Order.created_at <= date_to)
        query = query.order_by(Order.created_at.desc())
        
        result = await db.execute(query)
        orders = result.scalars().all()
        
        # Convert to seller view
        seller_orders = []
        for order in orders:
            order_dict = OrderSeller.from_orm(order).dict()
            
            # Calculate shop-specific total
            shop_total = Decimal('0.00')
            for item in order.items:
                if item.get("shop_id") == shop_id:
                    shop_total += Decimal(str(item.get("item_total", 0)))
            
            # Add seller-specific info
            order_dict.update({
                "buyer_email": order.customer_email,
                "buyer_name": order.customer_name,
                "buyer_has_account": order.buyer_id is not None,
                "buyer_account_id": order.buyer_id,
                "buyer_total_orders": await get_buyer_order_count(order.buyer_id, db) if order.buyer_id else 0,
                "buyer_is_verified": await is_buyer_verified(order.buyer_id, db) if order.buyer_id else False,
                
                # Action permissions
                "can_fulfill": order.status in [OrderStatus.PROCESSING, OrderStatus.ON_HOLD] and order.fulfillment_status == FulfillmentStatus.UNFULFILLED,
                "can_ship": order.requires_shipping and order.fulfillment_status == FulfillmentStatus.UNFULFILLED,
                "can_mark_delivered": order.requires_shipping and order.fulfillment_status == FulfillmentStatus.FULFILLED,
                "can_cancel": order.status in [OrderStatus.PENDING, OrderStatus.PROCESSING],
                "can_refund": order.status == OrderStatus.COMPLETED,
                "can_update_tracking": order.requires_shipping and order.fulfillment_status in [FulfillmentStatus.FULFILLED, FulfillmentStatus.PARTIALLY_FULFILLED],
                
                # Financial info
                "payout_status": "pending",  # Simplified for MVP
                "payout_amount": float(shop_total * Decimal('0.95')),  # 5% platform fee
                "payout_date": order.created_at + timedelta(days=7) if order.status == OrderStatus.COMPLETED else None,
                "payout_method": "stripe",  # Simplified
                
                # Shop info
                "shop_currency": "USD",  # Simplified
                "shop_timezone": "UTC",
                "shop_notification_email": shop.contact_email,
                "shop_support_email": shop.contact_email
            })
            seller_orders.append(order_dict)
        return seller_orders
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(f"Error getting shop orders: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve shop orders"
        )

async def get_buyer_order_count(buyer_id: str, db: AsyncSession) -> int:
    """Get total orders for a buyer."""
    try:
        result = await db.execute(
            select(func.count(Order.id)).where(Order.buyer_id == buyer_id)
        )
        return result.scalar() or 0
    except:
        return 0

async def is_buyer_verified(buyer_id: str, db: AsyncSession) -> bool:
    """Check if buyer is verified."""
    try:
        result = await db.execute(
            select(User).where(User.id == buyer_id)
        )
        user = result.scalar_one_or_none()
        return user.is_verified if user else False
    except:
        return False


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get order details by ID.
    """
    try:
        result = await db.execute(
            select(Order).where(Order.id == order_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            raise NotFoundException(
                resource_type="Order",
                identifier=order_id
            )
        # Check permissions
        is_buyer = order.buyer_id == current_user["sub"]
        is_admin = current_user.get("role") == "admin"
        # Check if user is seller for any item in the order
        is_seller = False
        if order.items:
            shop_ids = set(item.get("shop_id") for item in order.items)
            result = await db.execute(
                select(Shop).where(
                    Shop.id.in_(list(shop_ids)),
                    Shop.owner_id == current_user["sub"]
                )
            )
            is_seller = result.scalar_one_or_none() is not None
        if not (is_buyer or is_seller or is_admin):
            raise ForbiddenException(
                detail="You don't have permission to view this order"
            )
        return OrderResponse.from_orm(order)
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Error getting order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve order"
        )
    
# ==================== ORDER STATUS UPDATES ====================

@router.put("/{order_id}/status")
async def update_order_status(
    order_id: str,
    status_update: OrderStatusUpdate,
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update order status (seller/admin only).
    """
    try:
        result = await db.execute(
            select(Order).where(Order.id == order_id)
        )
        order = result.scalar_one_or_none()
        
        if not order:
            raise NotFoundException(
                resource_type="Order",
                identifier=order_id
            )
        
        # Check permissions
        is_admin = current_user.get("role") == "admin"
        
        # Check if user is seller for any item in the order
        is_seller = False
        if order.items:
            shop_ids = set(item.get("shop_id") for item in order.items)
            result = await db.execute(
                select(Shop).where(
                    Shop.id.in_(list(shop_ids)),
                    Shop.owner_id == current_user["sub"]
                )
            )
            is_seller = result.scalar_one_or_none() is not None
        
        if not (is_seller or is_admin):
            raise ForbiddenException(
                detail="You don't have permission to update this order"
            )
        
        # Validate status transition
        valid_transitions = {
            OrderStatus.PENDING: [OrderStatus.PROCESSING, OrderStatus.CANCELLED],
            OrderStatus.PROCESSING: [OrderStatus.ON_HOLD, OrderStatus.COMPLETED, OrderStatus.CANCELLED],
            OrderStatus.ON_HOLD: [OrderStatus.PROCESSING, OrderStatus.CANCELLED],
            OrderStatus.COMPLETED: [OrderStatus.REFUNDED],
            OrderStatus.CANCELLED: [],
            OrderStatus.REFUNDED: [],
            OrderStatus.FAILED: []
        }
        
        current_status = order.status
        new_status = status_update.status
        if new_status not in valid_transitions.get(current_status, []):
            raise ValidationException(
                detail=f"Cannot transition from {current_status.value} to {new_status.value}"
            )
        # Update status
        old_status = order.status
        order.status = new_status
        # Handle status-specific logic
        if new_status == OrderStatus.COMPLETED:
            order.completed_at = datetime.utcnow()
            # Mark digital products as delivered
            if order.order_type in ["digital", "mixed"]:
                order.digital_delivered = True
                order.digital_delivered_at = datetime.utcnow()
        
        elif new_status == OrderStatus.CANCELLED:
            order.cancelled_at = datetime.utcnow()
            # Restock items
            await restock_order_items(order, db)
        
        elif new_status == OrderStatus.REFUNDED:
            order.refunded_at = datetime.utcnow()
            # Restock items
            await restock_order_items(order, db)
        
        # Add status log
        status_log = {
            "status": new_status.value,
            "timestamp": datetime.utcnow().isoformat(),
            "notes": status_update.notes,
            "changed_by": current_user["email"],
            "old_status": old_status.value
        }
        
        order.status_logs.append(status_log)
        
        await db.commit()
        await db.refresh(order)
        
        logger.info(f"Order status updated: {order.order_number} from {old_status.value} to {new_status.value} by {current_user['email']}")
        
        # Send notification if requested
        if status_update.notify_customer:
            # In production, send email/SMS notification
            pass
        
        return {
            "message": "Order status updated successfully",
            "order_id": order_id,
            "order_number": order.order_number,
            "old_status": old_status.value,
            "new_status": new_status.value,
            "updated_by": current_user["email"],
            "notes": status_update.notes
        }
    except (NotFoundException, ForbiddenException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating order status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update order status"
        )

async def restock_order_items(order: Order, db: AsyncSession):
    """Restock items when order is cancelled or refunded."""
    for item in order.items:
        product_id = item.get("product_id")
        quantity = item.get("quantity", 1)        
        if product_id and quantity > 0:
            await db.execute(
                update(Product)
                .where(Product.id == product_id)
                .values(stock_quantity=Product.stock_quantity + quantity)
            )

# ==================== ORDER FULFILLMENT ====================

@router.post("/{order_id}/fulfill")
async def fulfill_order(
    order_id: str,
    fulfillment: OrderFulfillmentRequest,
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Fulfill order items (mark as shipped/fulfilled).
    """
    try:
        result = await db.execute(
            select(Order).where(Order.id == order_id)
        )
        order = result.scalar_one_or_none()
        
        if not order:
            raise NotFoundException(
                resource_type="Order",
                identifier=order_id
            )
        
        # Check if user is seller for this order
        shop_ids = set(item.get("shop_id") for item in order.items)
        result = await db.execute(
            select(Shop).where(
                Shop.id.in_(list(shop_ids)),
                Shop.owner_id == current_user["sub"]
            )
        )
        user_shops = result.scalars().all()
        
        if not user_shops:
            raise ForbiddenException(
                detail="You don't have permission to fulfill this order"
            )
        
        # Validate order can be fulfilled
        if order.status not in [OrderStatus.PROCESSING, OrderStatus.ON_HOLD]:
            raise ValidationException(
                detail=f"Cannot fulfill order with status: {order.status.value}"
            )
        
        # Update fulfillment status
        if order.fulfillment_status == FulfillmentStatus.UNFULFILLED:
            order.fulfillment_status = FulfillmentStatus.FULFILLED
        else:
            order.fulfillment_status = FulfillmentStatus.PARTIALLY_FULFILLED
        
        # Update tracking info if provided
        if fulfillment.tracking_number:
            order.tracking_number = fulfillment.tracking_number
        
        if fulfillment.shipping_provider:
            order.shipping_provider = fulfillment.shipping_provider
        
        if fulfillment.estimated_delivery_date:
            order.estimated_delivery_date = fulfillment.estimated_delivery_date
        
        if fulfillment.notes:
            order.fulfillment_notes = fulfillment.notes
        
        # Add status log
        status_log = {
            "event": "fulfillment",
            "timestamp": datetime.utcnow().isoformat(),
            "notes": f"Order fulfilled{', tracking: ' + fulfillment.tracking_number if fulfillment.tracking_number else ''}",
            "changed_by": current_user["email"]
        }
        
        order.status_logs.append(status_log)
        
        await db.commit()
        await db.refresh(order)
        
        logger.info(f"Order fulfilled: {order.order_number} by {current_user['email']}")
        
        # Send notification if requested
        if fulfillment.notify_customer:
            # In production, send shipping notification
            pass
        
        return {
            "message": "Order fulfilled successfully",
            "order_id": order_id,
            "order_number": order.order_number,
            "fulfillment_status": order.fulfillment_status.value,
            "tracking_number": order.tracking_number,
            "estimated_delivery_date": order.estimated_delivery_date.isoformat() if order.estimated_delivery_date else None
        }
        
    except (NotFoundException, ForbiddenException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error fulfilling order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not fulfill order"
        )


@router.post("/{order_id}/deliver")
async def mark_order_delivered(
    order_id: str,
    delivery: OrderDeliveryConfirmation,
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark order as delivered (for physical orders).
    """
    try:
        result = await db.execute(
            select(Order).where(Order.id == order_id)
        )
        order = result.scalar_one_or_none()
        
        if not order:
            raise NotFoundException(
                resource_type="Order",
                identifier=order_id
            )
        
        # Only buyers can mark as delivered
        if order.buyer_id != current_user["sub"]:
            raise ForbiddenException(
                detail="Only the buyer can mark order as delivered"
            )
        
        if not order.requires_shipping:
            raise ValidationException(
                detail="This order doesn't require shipping"
            )
        
        if order.fulfillment_status != FulfillmentStatus.FULFILLED:
            raise ValidationException(
                detail=f"Cannot mark as delivered with fulfillment status: {order.fulfillment_status.value}"
            )
        
        order.fulfillment_status = FulfillmentStatus.DELIVERED
        
        # Add delivery confirmation
        delivery_confirmation = {
            "delivered_at": delivery.delivered_at.isoformat(),
            "delivery_notes": delivery.delivery_notes,
            "customer_signature": delivery.customer_signature,
            "delivery_proof": delivery.delivery_proof,
            "confirmed_by": current_user["email"]
        }
        
        if not hasattr(order, 'delivery_confirmations'):
            order.delivery_confirmations = []
        
        order.delivery_confirmations.append(delivery_confirmation)
        
        await db.commit()
        
        logger.info(f"Order marked as delivered: {order.order_number} by {current_user['email']}")
        
        return {
            "message": "Order marked as delivered successfully",
            "order_id": order_id,
            "order_number": order.order_number,
            "fulfillment_status": order.fulfillment_status.value,
            "delivered_at": delivery.delivered_at.isoformat()
        }
        
    except (NotFoundException, ForbiddenException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error marking order as delivered: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not mark order as delivered"
        )


# ==================== ORDER REFUNDS ====================

@router.post("/{order_id}/refund")
async def refund_order(
    order_id: str,
    refund_request: OrderRefundRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Refund order or partial order.
    """
    try:
        result = await db.execute(
            select(Order).where(Order.id == order_id)
        )
        order = result.scalar_one_or_none()
        
        if not order:
            raise NotFoundException(
                resource_type="Order",
                identifier=order_id
            )
        
        # Check permissions
        is_admin = current_user.get("role") == "admin"
        
        # Check if user is seller for this order
        shop_ids = set(item.get("shop_id") for item in order.items)
        result = await db.execute(
            select(Shop).where(
                Shop.id.in_(list(shop_ids)),
                Shop.owner_id == current_user["sub"]
            )
        )
        is_seller = result.scalar_one_or_none() is not None
        
        if not (is_seller or is_admin):
            raise ForbiddenException(
                detail="You don't have permission to refund this order"
            )
        
        # Validate refund
        if order.status != OrderStatus.COMPLETED:
            raise ValidationException(
                detail=f"Cannot refund order with status: {order.status.value}"
            )
        
        if order.refund_amount >= order.order_total:
            raise ValidationException(
                detail="Order is already fully refunded"
            )
        
        if refund_request.refund_amount > order.order_total - order.refund_amount:
            raise ValidationException(
                detail=f"Refund amount exceeds remaining refundable amount: {order.order_total - order.refund_amount}"
            )
        
        # Update order
        order.refund_amount += refund_request.refund_amount
        order.refund_reason = refund_request.refund_reason
        
        if order.refund_amount >= order.order_total:
            order.status = OrderStatus.REFUNDED
            order.refunded_at = datetime.utcnow()
        status_log = {
            "event": "refund",
            "timestamp": datetime.utcnow().isoformat(),
            "notes": f"Refund processed: ${refund_request.refund_amount}, reason: {refund_request.refund_reason}",
            "changed_by": current_user["email"]
        }
        order.status_logs.append(status_log)
        if refund_request.restock_items:
            await restock_order_items(order, db)
        await db.commit()
        await db.refresh(order)
        audit_logger.log_payment_event(
            payment_id=str(order.id),
            amount=float(refund_request.refund_amount),
            currency="USD",
            user_id=current_user["sub"],
            shop_id=list(shop_ids)[0] if shop_ids else None,
            event_type="order_refunded",
            status="completed"
        )
        logger.info(f"Order refunded: {order.order_number}, amount: ${refund_request.refund_amount} by {current_user['email']}")
        if refund_request.notify_customer:
            background_tasks.add_task(
                send_refund_notification_email,
                order_id=order_id,
                customer_email=order.customer_email,
                refund_amount=refund_request.refund_amount,
                refund_reason=refund_request.refund_reason
            )
        return {
            "message": "Refund processed successfully",
            "order_id": order_id,
            "order_number": order.order_number,
            "refund_amount": float(refund_request.refund_amount),
            "total_refunded": float(order.refund_amount),
            "remaining_balance": float(order.order_total - order.refund_amount),
            "order_status": order.status.value,
            "refund_reason": refund_request.refund_reason
        }
    except (NotFoundException, ForbiddenException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error refunding order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not process refund"
        )

async def send_refund_notification_email(
    order_id: str, 
    customer_email: str, 
    refund_amount: Decimal, 
    refund_reason: str
):
    """Send refund notification email."""
    try:
        # In production, call Go email service
        logger.info(f"Refund notification email queued for order {order_id}")
    except Exception as e:
        logger.error(f"Error sending refund notification: {e}")


# ==================== ORDER DOWNLOADS (DIGITAL PRODUCTS) ====================

@router.get("/{order_id}/downloads")
async def get_order_downloads(
    order_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get download links for digital products in order.
    """
    try:
        result = await db.execute(
            select(Order).where(Order.id == order_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            raise NotFoundException(
                resource_type="Order",
                identifier=order_id
            )
        if order.buyer_id != current_user["sub"]:
            raise ForbiddenException(
                detail="You don't have permission to download these files"
            )
        if not order.digital_delivered:
            raise ValidationException(
                detail="Digital products are not yet delivered for this order"
            )
        downloads = []
        for item in order.items:
            if item.get("product_type") == "digital":
                product_id = item.get("product_id")
                result = await db.execute(
                    select(Product).where(Product.id == product_id)
                )
                product = result.scalar_one_or_none()
                if product and product.file_url:
                    download_count = await get_download_count(order_id, product_id, db)
                    remaining_downloads = product.download_limit - download_count
                    if remaining_downloads > 0:
                        downloads.append({
                            "product_id": product_id,
                            "product_name": item.get("product_name"),
                            "file_url": product.file_url,
                            "file_name": product.file_name,
                            "downloads_used": download_count,
                            "downloads_remaining": remaining_downloads,
                            "download_limit": product.download_limit,
                            "access_expires": (
                                (order.created_at + timedelta(days=product.access_duration_days)).isoformat()
                                if product.access_duration_days else None
                            )
                        })
        if downloads:
            await log_download_access(order_id, current_user["sub"], db)
        return {
            "order_id": order_id,
            "order_number": order.order_number,
            "digital_delivered": order.digital_delivered,
            "digital_delivered_at": order.digital_delivered_at.isoformat() if order.digital_delivered_at else None,
            "downloads": downloads
        }
    except (NotFoundException, ForbiddenException, ValidationException):
        raise
    except Exception as e:
        logger.error(f"Error getting order downloads: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve downloads"
        )

async def get_download_count(order_id: str, product_id: str, db: AsyncSession) -> int:
    """Get download count for a product in an order."""
    return 0


async def log_download_access(order_id: str, user_id: str, db: AsyncSession):
    """Log download access."""
    # In MVP, do nothing
    # In production, create download log entry
    pass


# ==================== BULK ORDER ACTIONS ====================

@router.post("/bulk/action")
async def bulk_order_action(
    bulk_action: OrderBulkAction,
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    bulk_validator: BulkOperationValidator = Depends(BulkOperationValidator(max_items=50))
):
    """
    Perform bulk action on multiple orders.
    """
    try:
        # Validate bulk operation
        await bulk_validator(bulk_action.order_ids)
        
        # Check permissions based on action
        is_admin = current_user.get("role") == "admin"
        
        if bulk_action.action in ["update_status", "export_labels"] and not is_admin:
            raise ForbiddenException(
                detail="Admin permission required for this action"
            )
        
        # Get orders
        result = await db.execute(
            select(Order).where(Order.id.in_(bulk_action.order_ids))
        )
        orders = result.scalars().all()
        
        if len(orders) != len(bulk_action.order_ids):
            raise NotFoundException(
                resource_type="Orders",
                identifier="some orders not found"
            )
        
        # Perform bulk action
        results = []
        
        for order in orders:
            try:
                # Check seller permissions for shop-specific actions
                if bulk_action.action in ["fulfill", "ship", "complete"]:
                    shop_ids = set(item.get("shop_id") for item in order.items)
                    result = await db.execute(
                        select(Shop).where(
                            Shop.id.in_(list(shop_ids)),
                            Shop.owner_id == current_user["sub"]
                        )
                    )
                    if not result.scalar_one_or_none():
                        results.append({
                            "order_id": str(order.id),
                            "order_number": order.order_number,
                            "success": False,
                            "error": "Not authorized for this order"
                        })
                        continue
                
                # Perform action
                if bulk_action.action == "fulfill":
                    # Update fulfillment status
                    order.fulfillment_status = FulfillmentStatus.FULFILLED
                    result_message = "Order fulfilled"
                
                elif bulk_action.action == "complete":
                    # Mark as completed
                    order.status = OrderStatus.COMPLETED
                    order.completed_at = datetime.utcnow()
                    result_message = "Order completed"
                
                elif bulk_action.action == "cancel":
                    # Cancel order
                    order.status = OrderStatus.CANCELLED
                    order.cancelled_at = datetime.utcnow()
                    result_message = "Order cancelled"
                
                elif bulk_action.action == "update_status":
                    # Update status from data
                    new_status = bulk_action.data.get("status")
                    if new_status:
                        order.status = OrderStatus(new_status)
                        result_message = f"Status updated to {new_status}"
                    else:
                        results.append({
                            "order_id": str(order.id),
                            "order_number": order.order_number,
                            "success": False,
                            "error": "No status provided in data"
                        })
                        continue
                
                else:
                    results.append({
                        "order_id": str(order.id),
                        "order_number": order.order_number,
                        "success": False,
                        "error": f"Unknown action: {bulk_action.action}"
                    })
                    continue
                
                # Add status log
                status_log = {
                    "event": "bulk_action",
                    "timestamp": datetime.utcnow().isoformat(),
                    "notes": f"Bulk action: {bulk_action.action}{', reason: ' + bulk_action.reason if bulk_action.reason else ''}",
                    "changed_by": current_user["email"]
                }
                
                order.status_logs.append(status_log)
                
                results.append({
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                    "success": True,
                    "message": result_message
                })
                
            except Exception as e:
                results.append({
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                    "success": False,
                    "error": str(e)
                })
        
        await db.commit()
        
        success_count = sum(1 for r in results if r["success"])
        
        logger.info(f"Bulk order action: {bulk_action.action}, processed: {len(results)}, successful: {success_count}")
        
        return {
            "action": bulk_action.action,
            "total_orders": len(bulk_action.order_ids),
            "processed": len(results),
            "successful": success_count,
            "failed": len(results) - success_count,
            "results": results,
            "notify_customers": bulk_action.notify_customers
        }
        
    except (NotFoundException, ForbiddenException, ValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error performing bulk order action: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not perform bulk action"
        )

# ==================== ORDER STATISTICS ====================

@router.get("/stats/sales")
async def get_sales_statistics(
    period: str = Query("month", pattern="^(day|week|month|year)$"),
    shop_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get sales statistics for user (buyer or seller).
    """
    try:
        # Calculate date range
        now = datetime.utcnow()
        if period == "day":
            start_date = now - timedelta(days=1)
        elif period == "week":
            start_date = now - timedelta(weeks=1)
        elif period == "month":
            start_date = now - timedelta(days=30)
        else:  # year
            start_date = now - timedelta(days=365)
        
        # Build query based on user role
        is_admin = current_user.get("role") == "admin"
        if is_admin:
            # Admin sees all orders
            query = select(Order).where(
                Order.created_at >= start_date,
                Order.status.in_([OrderStatus.COMPLETED, OrderStatus.REFUNDED])
            )
        else:
            # Check if user is a seller
            result = await db.execute(
                select(Shop).where(Shop.owner_id == current_user["sub"])
            )
            user_shops = result.scalars().all()
            if user_shops and shop_id:
                # Seller viewing specific shop
                query = select(Order).where(
                    Order.created_at >= start_date,
                    Order.status.in_([OrderStatus.COMPLETED, OrderStatus.REFUNDED]),
                    Order.items.any(f"$.shop_id == '{shop_id}'")
                )
            elif user_shops:
                # Seller viewing all their shops
                shop_ids = [shop.id for shop in user_shops]
                shop_conditions = [f"$.shop_id == '{sid}'" for sid in shop_ids]
                query = select(Order).where(
                    Order.created_at >= start_date,
                    Order.status.in_([OrderStatus.COMPLETED, OrderStatus.REFUNDED]),
                    or_(*[Order.items.any(cond) for cond in shop_conditions])
                )
            else:
                # Buyer viewing their own orders
                query = select(Order).where(
                    Order.buyer_id == current_user["sub"],
                    Order.created_at >= start_date,
                    Order.status.in_([OrderStatus.COMPLETED, OrderStatus.REFUNDED])
                )
        
        result = await db.execute(query)
        orders = result.scalars().all()
        # Calculate statistics
        total_orders = len(orders)
        total_revenue = sum(order.order_total for order in orders)
        total_refunds = sum(order.refund_amount for order in orders)
        net_revenue = total_revenue - total_refunds
        
        # Group by date
        daily_stats = {}
        for order in orders:
            date_key = order.created_at.strftime("%Y-%m-%d")
            if date_key not in daily_stats:
                daily_stats[date_key] = {
                    "date": date_key,
                    "orders": 0,
                    "revenue": Decimal('0.00'),
                    "refunds": Decimal('0.00')
                }
            
            daily_stats[date_key]["orders"] += 1
            daily_stats[date_key]["revenue"] += order.order_total
            daily_stats[date_key]["refunds"] += order.refund_amount
        
        daily_stats_list = sorted(daily_stats.values(), key=lambda x: x["date"])
        
        return {
            "period": period,
            "start_date": start_date.isoformat(),
            "end_date": now.isoformat(),
            "total_orders": total_orders,
            "total_revenue": float(total_revenue),
            "total_refunds": float(total_refunds),
            "net_revenue": float(net_revenue),
            "average_order_value": float(total_revenue / total_orders) if total_orders > 0 else 0,
            "daily_stats": daily_stats_list
        }
        
    except Exception as e:
        logger.error(f"Error getting sales statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve sales statistics"
        )

# ==================== ADMIN ENDPOINTS ====================

@router.get("/admin/list", response_model=List[OrderResponse])
async def list_orders_admin(
    pagination: PaginationParams = Depends(),
    search: OrderSearchParams = Depends(),
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    List all orders (admin only).
    """
    try:
        query = select(Order).options(
            joinedload(Order.buyer)
        )
        if search.search:
            query = query.where(
                or_(
                    Order.order_number.ilike(f"%{search.search}%"),
                    Order.customer_email.ilike(f"%{search.search}%"),
                    Order.customer_name.ilike(f"%{search.search}%")
                )
            )
        if search.shop_id:
            query = query.where(
                Order.items.any(f"$.shop_id == '{search.shop_id}'")
            )
        if search.customer_email:
            query = query.where(Order.customer_email == search.customer_email)
        if search.status:
            query = query.where(Order.status == search.status)
        if search.order_type:
            query = query.where(Order.order_type == search.order_type)
        if search.payment_method:
            query = query.where(Order.payment_method == search.payment_method)
        if search.date_from:
            query = query.where(Order.created_at >= search.date_from)
        if search.date_to:
            query = query.where(Order.created_at <= search.date_to)
        if search.min_amount is not None:
            query = query.where(Order.order_total >= Decimal(str(search.min_amount)))
        if search.max_amount is not None:
            query = query.where(Order.order_total <= Decimal(str(search.max_amount)))
        query = query.offset(pagination.offset).limit(pagination.limit)
        if pagination.sort_by:
            sort_column = getattr(Order, pagination.sort_by, None)
            if sort_column:
                if pagination.sort_order == "desc":
                    query = query.order_by(sort_column.desc())
                else:
                    query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(Order.created_at.desc())
        result = await db.execute(query)
        orders = result.scalars().all()
        
        return [OrderResponse.from_orm(order) for order in orders]
        
    except Exception as e:
        logger.error(f"Error listing orders admin: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not list orders"
        )
    


