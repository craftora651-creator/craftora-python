from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
import uuid
router = APIRouter(prefix="/users", tags=["users"])
import logging

from database.database import get_db
from models.user import User, UserRole as ModelUserRole, AuthProvider as ModelAuthProvider
# ✅ DOĞRU IMPORT PATH:
from routers.users import (
    UserResponse, 
    UserUpdate, 
    UserPublic,
    UserAdmin,
    UserSearchParams,
    UserStats,
    PaginationParams,
    AuthProvider as SchemaAuthProvider,
    UserRole as SchemaUserRole,
    BecomeSellerRequest  # ✅ EKLE
)
from helpers.security import security_manager, oauth2_scheme
from nix.logging import get_logger, get_audit_logger
from helpers.security import get_current_user_clean, get_current_verified_user
print(f"🔍 get_current_user module: {get_current_user_clean.__module__}")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # DEBUG seviyesinde log tut

# audit_logger'ı da ayarla
audit_logger = logger


# ==================== REQUEST MODELS ====================

class BecomeSellerRequestSchema:
    """Temporary schema until we fix imports"""
    pass

# ==================== ADMIN DEPENDENCY ====================

async def require_admin(
    current_user: dict = Depends(get_current_user_clean),  # ✅ Önce current user kontrolü
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Admin yetkisi kontrolü."""
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format"
            )
        
        result = await db.execute(
            select(User).where(
                User.id == user_uuid,
                User.role == ModelUserRole.ADMIN,
                User.is_active == True
            )
        )
        admin_user = result.scalar_one_or_none()
        
        if not admin_user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required"
            )
        
        return {
            "user_id": str(admin_user.id),
            "email": admin_user.email,
            "role": admin_user.role.value,
            "user": admin_user.to_dict(include_sensitive=True)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin check error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error"
        )

# ==================== PUBLIC ENDPOINTS ====================

@router.get("/{user_id}/public", response_model=UserPublic)
async def get_user_public_profile(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get public user profile (anyone can view)."""
    logger.info(f"Public profile requested for: {user_id}")
    
    try:
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format"
            )
        
        stmt = select(User).where(
            User.id == user_uuid,
            User.is_active == True
        )
        
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return UserPublic(
            id=str(user.id),
            full_name=user.full_name,
            avatar_url=user.avatar_url,
            is_seller=user.is_seller,
            seller_since=user.seller_since,
            shop_count=user.shop_count,
            created_at=user.created_at,
            last_active_at=user.last_active_at,
            bio=None,
            website=None,
            location=None,
            total_public_reviews=0,
            average_rating=0.0
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in public profile: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

# ==================== AUTHENTICATED USER ENDPOINTS ====================



@router.get("/me", response_model=UserResponse)
async def get_my_profile(
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """Get current authenticated user's profile."""
    print("\n" + "🔥"*50)
    print("🔥 USERS.PY - get_my_profile - BAŞLANGIÇ")
    print(f"🔥 get_current_user fonksiyonu: {get_current_user_clean}")
    print(f"🔥 get_current_user module: {get_current_user_clean.__module__}")
    print("🔥"*50)
    
    # 1. current_user'ın TÜM anahtarlarını görelim
    print(f"📌 current_user.keys(): {list(current_user.keys())}")
    print(f"📌 current_user içeriği: {current_user}")
    
    # 2. sub'ı al
    user_id = current_user.get("sub")
    print(f"📌 user_id (sub): {user_id}")
    
    # 3. Token'dan geldiyse email'i de görelimQ
    email = current_user.get("email")
    print(f"📌 email: {email}")
    
    if not user_id:
        # Alternatifleri dene
        user_id = current_user.get("user_id") or current_user.get("id")
        print(f"📌 Alternatif ID: {user_id}")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token - no user ID"
            )
    
    try:
        from uuid import UUID
        user_uuid = UUID(user_id)
        print(f"📌 UUID'ye çevrildi: {user_uuid}")
        
        from sqlalchemy import select
        result = await db.execute(
            select(User).where(User.id == user_uuid)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"❌ Kullanıcı bulunamadı! UUID: {user_uuid}")
            
            # DEBUG: Tüm kullanıcıları listele
            all_users = await db.execute(select(User))
            users = all_users.scalars().all()
            print(f"📊 Toplam {len(users)} kullanıcı:")
            for u in users:
                print(f"   - {u.id} | {u.email}")
                if u.id == user_uuid:
                    print(f"   ✅ EŞLEŞEN BULUNDU! {u.id}")
            
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User not found with id: {user_id}"
            )
        
        print(f"✅ Kullanıcı bulundu: {user.email}")
        return UserResponse(**user.to_dict(include_sensitive=True))
        
    except ValueError as e:
        print(f"❌ UUID dönüşüm hatası: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid user ID format: {user_id}"
        )
    except Exception as e:
        print(f"💥 Beklenmeyen hata: {e}")
        raise

   
   
@router.put("/me", response_model=UserResponse)
async def update_my_profile(
    user_data: UserUpdate,
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """Update current user's profile."""
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format"
            )
        
        result = await db.execute(
            select(User).where(User.id == user_uuid)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Update allowed fields
        update_data = user_data.model_dump(exclude_unset=True)  # ✅ Pydantic v2 için model_dump
        
        # Don't allow updating sensitive fields through this endpoint
        restricted_fields = [
            "role", "is_active", "is_verified", "google_id", 
            "apple_id", "stripe_account_id", "stripe_customer_id",
            "seller_verified", "verified_at"
        ]
        for field in restricted_fields:
            update_data.pop(field, None)
        
        # Update user fields
        for field, value in update_data.items():
            if hasattr(user, field):
                setattr(user, field, value)
        
        user.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(user)
        
        # Log audit event
        audit_logger.info(
            f"User profile updated: {user.email}",
            extra={
                "user_id": str(user.id),
                "action": "profile_update",
                "updated_fields": list(update_data.keys())
            }
        )
        
        logger.info(f"User profile updated: {user.email}")
        return UserResponse(**user.to_dict(include_sensitive=True))
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update profile"
        )

@router.delete("/me")
async def delete_my_account(
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """Delete current user's account (soft delete)."""
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format"
            )
        
        result = await db.execute(
            select(User).where(User.id == user_uuid)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Soft delete (mark as inactive)
        user.is_active = False
        user.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        
        # Log audit event
        audit_logger.warning(
            f"User account deactivated: {user.email}",
            extra={
                "user_id": str(user.id),
                "action": "account_deactivation",
                "deactivated_by": "self"
            }
        )
        
        logger.warning(f"User account deactivated: {user.email}")
        
        return {
            "message": "Account successfully deactivated",
            "user_id": str(user.id),
            "email": user.email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting account: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete account"
        )

@router.post("/me/become-seller")
async def become_seller(
    request: Dict[str, Any] = Body(default_factory=dict),  # ✅ Request body için
    current_user: dict = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Request to become a seller (upgrade role from user to seller)."""
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format"
            )
        
        result = await db.execute(
            select(User).where(User.id == user_uuid)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if user.role == ModelUserRole.SELLER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are already a seller"
            )
        
        if user.role == ModelUserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admins are automatically sellers"
            )
        
        # Extract stripe_account_id from request if provided
        stripe_account_id = request.get("stripe_account_id")
        
        # Convert to seller
        user.convert_to_seller(stripe_account_id=stripe_account_id)
        user.updated_at = datetime.now(timezone.utc)
        
        # Optional: Update business info from request
        if "business_name" in request:
            user.business_name = request.get("business_name")
        if "phone_number" in request:
            user.phone_number = request.get("phone_number")
        
        await db.commit()
        await db.refresh(user)
        
        # Log audit event
        audit_logger.info(
            f"User upgraded to seller: {user.email}",
            extra={
                "user_id": str(user.id),
                "action": "role_upgrade",
                "old_role": "user",
                "new_role": "seller"
            }
        )
        
        logger.info(f"User upgraded to seller: {user.email}")
        
        return {
            "message": "Successfully upgraded to seller",
            "user_id": str(user.id),
            "new_role": "seller",
            "seller_since": user.seller_since.isoformat() if user.seller_since else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error becoming seller: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not upgrade to seller"
        )

# ==================== USER PREFERENCES ====================

@router.get("/me/preferences")
async def get_my_preferences(
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's preferences."""
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format"
            )
        
        result = await db.execute(
            select(User).where(User.id == user_uuid)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return {
            "preferences": user.preferences,
            "user_id": str(user.id)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting preferences: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve preferences"
        )

@router.put("/me/preferences")
async def update_my_preferences(
    preferences: Dict[str, Any],
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """Update current user's preferences."""
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format"
            )
        
        result = await db.execute(
            select(User).where(User.id == user_uuid)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Merge preferences
        user.preferences.update(preferences)
        user.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(user)
        
        logger.info(f"User preferences updated: {user.email}")
        
        return {
            "message": "Preferences updated successfully",
            "preferences": user.preferences
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating preferences: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update preferences"
        )

# ==================== ADMIN ENDPOINTS ====================

@router.get("/admin/list", response_model=List[UserAdmin])
async def list_users_admin(
    pagination: PaginationParams = Depends(),
    search: UserSearchParams = Depends(),
    current_user: dict = Depends(require_admin),  # ✅ require_admin yeterli
    db: AsyncSession = Depends(get_db)
):
    """List all users (admin only)."""
    try:
        query = select(User)
        
        # Apply filters
        if search.email:
            query = query.where(User.email.ilike(f"%{search.email}%"))
        if search.full_name:
            query = query.where(User.full_name.ilike(f"%{search.full_name}%"))
        if search.role:
            query = query.where(User.role == ModelUserRole(search.role.value))
        if search.auth_provider:
            query = query.where(User.auth_provider == search.auth_provider.value)
        if search.is_active is not None:
            query = query.where(User.is_active == search.is_active)
        if search.is_verified is not None:
            query = query.where(User.is_verified == search.is_verified)
        if search.is_seller is not None:
            if search.is_seller:
                query = query.where(User.role == ModelUserRole.SELLER)
            else:
                query = query.where(User.role != ModelUserRole.SELLER)
        if search.date_from:
            query = query.where(User.created_at >= search.date_from)
        if search.date_to:
            query = query.where(User.created_at <= search.date_to)
        
        # Apply pagination
        offset = (pagination.page - 1) * pagination.limit
        query = query.offset(offset).limit(pagination.limit)
        
        # Apply sorting
        if pagination.sort_by:
            sort_column = getattr(User, pagination.sort_by, None)
            if sort_column:
                if pagination.sort_order == "desc":
                    query = query.order_by(sort_column.desc())
                else:
                    query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(User.created_at.desc())
        
        result = await db.execute(query)
        users = result.scalars().all()
        
        # Convert to response models
        return [
            UserAdmin(
                **user.to_dict(include_sensitive=True),
                google_id=user.google_id,
                apple_id=user.apple_id,
                apple_private_email=user.apple_private_email,
                is_apple_provided_email=user.is_apple_provided_email,
                user_metadata=user.user_metadata,
                login_attempts=user.login_attempts,
                locked_until=user.locked_until,
                two_factor_enabled=user.two_factor_enabled
            )
            for user in users
        ]
        
    except Exception as e:
        logger.error(f"Error listing users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not list users"
        )

@router.get("/admin/{user_id}", response_model=UserAdmin)
async def get_user_admin(
    user_id: str,
    current_user: dict = Depends(require_admin),  # ✅ require_admin yeterli
    db: AsyncSession = Depends(get_db)
):
    """Get user details (admin only)."""
    try:
        # Get target user
        try:
            target_uuid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format"
            )
        
        result = await db.execute(
            select(User).where(User.id == target_uuid)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return UserAdmin(
            **user.to_dict(include_sensitive=True),
            google_id=user.google_id,
            apple_id=user.apple_id,
            apple_private_email=user.apple_private_email,
            is_apple_provided_email=user.is_apple_provided_email,
            user_metadata=user.user_metadata,
            login_attempts=user.login_attempts,
            locked_until=user.locked_until,
            two_factor_enabled=user.two_factor_enabled
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user admin: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve user details"
        )

@router.put("/admin/{user_id}/role")
async def update_user_role_admin(
    user_id: str,
    role_data: Dict[str, Any] = Body(...),  # ✅ Request body olarak al
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update user role (admin only)."""
    try:
        admin_info = current_user
        
        # Extract role and reason from request body
        role_value = role_data.get("role")
        reason = role_data.get("reason")
        
        if not role_value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role is required"
            )
        
        try:
            role_enum = SchemaUserRole(role_value)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role. Must be one of: {[r.value for r in SchemaUserRole]}"
            )
        
        # Get target user
        try:
            target_uuid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format"
            )
        
        result = await db.execute(
            select(User).where(User.id == target_uuid)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        old_role = user.role
        # Update role
        user.role = ModelUserRole(role_enum.value)
        
        # Update seller_since if becoming seller
        if role_enum == SchemaUserRole.SELLER and old_role != ModelUserRole.SELLER:
            user.seller_since = datetime.now(timezone.utc)
        # Clear seller_since if no longer seller
        elif role_enum != SchemaUserRole.SELLER and old_role == ModelUserRole.SELLER:
            user.seller_since = None
            user.seller_verified = False
            user.verified_at = None
        
        user.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(user)
        
        # Log audit event
        audit_logger.info(
            f"User role changed by admin: {user.email} from {old_role.value} to {role_enum.value}",
            extra={
                "target_user_id": str(user.id),
                "target_email": user.email,
                "admin_id": admin_info.get("user_id"),
                "admin_email": admin_info.get("email"),
                "old_role": old_role.value,
                "new_role": role_enum.value,
                "reason": reason
            }
        )
        
        logger.info(f"User role updated: {user.email} from {old_role.value} to {role_enum.value}")
        
        return {
            "message": "User role updated successfully",
            "user_id": str(user.id),
            "old_role": old_role.value,
            "new_role": role_enum.value,
            "updated_by": admin_info.get("email"),
            "reason": reason
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating user role: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update user role"
        )

@router.put("/admin/{user_id}/status")
async def update_user_status_admin(
    user_id: str,
    status_data: Dict[str, Any] = Body(...),  # ✅ Request body olarak al
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update user active status (admin only)."""
    try:
        admin_info = current_user
        
        # Extract is_active and reason from request body
        is_active = status_data.get("is_active")
        reason = status_data.get("reason")
        
        if is_active is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="is_active is required"
            )
        
        # Get target user
        try:
            target_uuid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format"
            )
        
        result = await db.execute(
            select(User).where(User.id == target_uuid)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        old_status = user.is_active
        user.is_active = bool(is_active)
        user.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(user)
        
        # Log audit event
        action = "activated" if is_active else "deactivated"
        audit_logger.warning(
            f"User account {action} by admin: {user.email}",
            extra={
                "target_user_id": str(user.id),
                "target_email": user.email,
                "admin_id": admin_info.get("user_id"),
                "admin_email": admin_info.get("email"),
                "old_status": old_status,
                "new_status": is_active,
                "reason": reason
            }
        )
        
        logger.warning(f"User status updated: {user.email} from {old_status} to {is_active}")
        
        return {
            "message": f"User account {'activated' if is_active else 'deactivated'} successfully",
            "user_id": str(user.id),
            "old_status": old_status,
            "new_status": is_active,
            "updated_by": admin_info.get("email"),
            "reason": reason
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating user status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update user status"
        )

@router.post("/admin/{user_id}/verify-seller")
async def verify_seller_admin(
    user_id: str,
    documents: Dict[str, Any] = Body(...),
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Verify a seller (admin only)."""
    try:
        admin_info = current_user
        
        # Get target user
        try:
            target_uuid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format"
            )
        
        result = await db.execute(
            select(User).where(User.id == target_uuid)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if user.role != ModelUserRole.SELLER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is not a seller"
            )
        
        user.verify_seller(documents)
        user.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(user)
        
        # Log audit event
        audit_logger.info(
            f"Seller verified by admin: {user.email}",
            extra={
                "seller_id": str(user.id),
                "seller_email": user.email,
                "verified_by": admin_info.get("user_id"),
                "admin_email": admin_info.get("email"),
                "documents_type": list(documents.keys()) if documents else []
            }
        )
        
        logger.info(f"Seller verified: {user.email}")
        
        return {
            "message": "Seller verified successfully",
            "user_id": str(user.id),
            "seller_verified": user.seller_verified,
            "verified_at": user.verified_at.isoformat() if user.verified_at else None,
            "verified_by": admin_info.get("email")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error verifying seller: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not verify seller"
        )

# ==================== STATISTICS ====================

@router.get("/me/stats", response_model=UserStats)
async def get_my_stats(
    current_user: dict = Depends(get_current_user_clean),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's statistics."""
    try:
        user_id = current_user.get("user_id") or current_user.get("sub")
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format"
            )
        
        result = await db.execute(
            select(User).where(User.id == user_uuid)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        stats = UserStats(
            total_orders=user.total_orders,
            total_spent=float(user.total_spent or 0) / 100 if user.total_spent else 0.0,
            average_order_value=(
                float(user.total_spent or 0) / user.total_orders / 100 
                if user.total_orders > 0 else 0.0
            ),
            favorite_categories=[],
            last_order_date=user.last_order_at,
            order_count_30d=0,
            spent_30d=0.0
        )
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve user statistics"
        )

@router.get("/admin/stats/summary")
async def get_admin_stats_summary(
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get admin statistics summary."""
    try:
        # Get statistics
        total_users = await db.scalar(select(func.count(User.id)))
        active_users = await db.scalar(
            select(func.count(User.id)).where(User.is_active == True)
        )
        sellers = await db.scalar(
            select(func.count(User.id)).where(User.role == ModelUserRole.SELLER)
        )
        verified_sellers = await db.scalar(
            select(func.count(User.id)).where(
                User.role == ModelUserRole.SELLER,
                User.seller_verified == True
            )
        )
        apple_users = await db.scalar(
            select(func.count(User.id)).where(User.auth_provider == ModelAuthProvider.APPLE.value)
        )
        google_users = await db.scalar(
            select(func.count(User.id)).where(User.auth_provider == ModelAuthProvider.GOOGLE.value)
        )
        
        # New users today
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        new_users_today = await db.scalar(
            select(func.count(User.id)).where(User.created_at >= today_start)
        )
        
        # New sellers today
        new_sellers_today = await db.scalar(
            select(func.count(User.id)).where(
                User.role == ModelUserRole.SELLER,
                User.seller_since >= today_start
            )
        )
        
        return {
            "total_users": total_users,
            "active_users": active_users,
            "sellers": sellers,
            "verified_sellers": verified_sellers,
            "apple_users": apple_users,
            "google_users": google_users,
            "new_users_today": new_users_today,
            "new_sellers_today": new_sellers_today,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting admin stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve admin statistics"
        )
