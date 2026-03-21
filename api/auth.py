"""
Authentication API endpoints - GÜNCELLENMİŞ
Google OAuth, Apple Sign-In, JWT tokens, login/logout
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import httpx
import uuid
import logging  # ✅ Bunu KULLAN!

from database.database import get_db
from helpers.security import security_manager, get_current_user_clean
from config.config import settings
from models.user import User, AuthProvider
from routers.users import UserMinimal
from routers.users import (
    UserResponse, 
    TokenResponse, 
    RefreshTokenRequest,
    AppleAuthRequest,
    GoogleAuthRequest,
    AuthResponse,
)
from sqlalchemy import text
import random

# ✅ KENDİ LOGGER'INI TANIMLA!
logger = logging.getLogger(__name__)
audit_logger = logger  # audit_logger da aynı olsun

# Create router
router = APIRouter(prefix="/auth", tags=["authentication"])


# ==================== GOOGLE OAUTH (MODERN) ====================


@router.post("/google", response_model=AuthResponse)
async def google_auth(
    request: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Google OAuth authentication with JWT token.
    """
    try:
        logger.info(f" Google auth - token doğrulanıyor...")
        
        # 🔧 TEST MODU - Eğer test-token gelirse sabit kullanıcı kullan
        if request.id_token == "test-token" or request.id_token.startswith("test"):
            logger.info("🔧 TEST MODU AKTİF - Sabit test kullanıcısı kullanılıyor")
            result = await db.execute(
                select(User).where(User.email == "test@craftora.com")
            )
            db_user = result.scalar_one_or_none()
            if db_user:
                user_info = {
                    "google_id": str(db_user.id),  # Database'deki ID
                    "email": db_user.email,  # Sabit email!
                    "full_name": db_user.full_name,
                    "email_verified": True,
                    "avatar_url": db_user.avatar_url
            }
                logger.info(f"✅ Database'den kullanıcı bulundu: {db_user.id}")
            else:
                user_info = {
                    "google_id": "07da0742-bf89-4966-a7d0-d5626d40724c",
                    "email": "test@craftora.com",
                    "full_name": "Test User",
                    "email_verified": True,
                    "avatar_url": None
            }
        else:
            user_info = await security_manager.verify_google_token(request.id_token)
            if not user_info:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Google token"
                )
    
        
        # Email ile kullanıcı bul veya oluştur
        result = await db.execute(
            select(User).where(User.email == user_info["email"])
        )
        user = result.scalar_one_or_none()
        
        is_new_user = False
        
        if user:
            # Var olan kullanıcıyı güncelle
            user.google_id = user_info["google_id"]
            user.full_name = user_info.get("full_name")
            user.avatar_url = user_info.get("avatar_url")
            user.last_login_at = datetime.utcnow()
            user.last_active_at = datetime.utcnow()
            user.auth_provider = AuthProvider.GOOGLE.value
        else:
            # Yeni kullanıcı oluştur
            is_new_user = True
            user = User(
                email=user_info["email"],
                google_id=user_info["google_id"],
                full_name=user_info.get("full_name"),
                avatar_url=user_info.get("avatar_url"),
                auth_provider=AuthProvider.GOOGLE.value,
                is_verified=user_info.get("email_verified", False),
                last_login_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(user)
        
        await db.commit()
        await db.refresh(user)
        
        # Generate JWT tokens
        tokens = security_manager.create_tokens(
            user_id=str(user.id),
            email=user.email,
            role=user.role if isinstance(user.role, str) else user.role.value,
            is_verified=user.is_verified,
            is_active=user.is_active,
            auth_provider=AuthProvider.GOOGLE.value
        )
        
        # Log audit event
        audit_logger.info(
            f"Google Sign-In {'new user' if is_new_user else 'existing user'}: {user.email}",
            extra={
                "user_id": str(user.id),
                "is_new_user": is_new_user,
                "auth_provider": "google"
            }
        )
        
        # User minimal info
        user_minimal = UserMinimal(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            avatar_url=user.avatar_url,
            role=user.role if isinstance(user.role, str) else user.role.value,
            is_seller=user.is_seller
        )
        
        response = AuthResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type="bearer",
            expires_in=3600,
            user=user_minimal.model_dump(),
            is_new_user=is_new_user
        )
        
        logger.info(f" Google auth başarılı: {user.email}")
        return response
        
    except Exception as e:
        logger.error(f" Google auth error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Google authentication failed: {str(e)}"
        )
   
# ==================== APPLE SIGN-IN ====================

@router.post("/apple", response_model=AuthResponse)
async def apple_auth(
    request: AppleAuthRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Apple Sign-In authentication.
    """
    try:
        logger.info(f"🍎 Apple auth - istek alındı")
        
        # ==================== TEST MODU ====================
        # 🔧 Geliştirme için test token'ı
        if request.identity_token == "test-apple-token-123":
            logger.info("🍎🔧 TEST MODU AKTİF - Test Apple kullanıcısı kullanılıyor")
            
            # Test kullanıcısı bilgileri
            apple_user_info = {
                "apple_id": "test-apple-id-123",
                "email": request.user.get("email") if request.user and request.user.get("email") else "test@apple.com",
                "full_name": request.user.get("name") if request.user and request.user.get("name") else "Test Apple User",
                "is_private_email": False
            }
            
            logger.info(f"🍎🔧 Test kullanıcısı: {apple_user_info['email']}")
            
        else:
            # ==================== GERÇEK APPLE TOKEN ====================
            # TODO: Implement Apple token verification
            # In production, use apple-signin-auth library
            
            # Simulated Apple user data (would come from token verification)
            apple_user_info = {
                "apple_id": f"apple_{int(datetime.now(timezone.UTC).timestamp())}",
                "email": request.user.get("email") if request.user else "apple_user@privaterelay.appleid.com",
                "full_name": request.user.get("name") if request.user else "Apple User",
                "is_private_email": "@privaterelay.appleid.com" in (request.user.get("email") if request.user else "")
            }
        
        # ==================== KULLANICI BUL VEYA OLUŞTUR ====================
        
        # Önce email ile ara
        result = await db.execute(
            select(User).where(User.email == apple_user_info["email"])
        )
        user = result.scalar_one_or_none()
        
        # Email ile bulunamazsa apple_id ile ara
        if not user:
            result = await db.execute(
                select(User).where(User.apple_id == apple_user_info["apple_id"])
            )
            user = result.scalar_one_or_none()
        
        is_new_user = False
        
        if user:
            # Var olan kullanıcıyı güncelle
            logger.info(f"🍎 Mevcut kullanıcı bulundu: {user.email}")
            user.apple_id = apple_user_info["apple_id"]
            user.full_name = apple_user_info["full_name"] or user.full_name
            user.last_login_at = datetime.utcnow()
            user.last_active_at = datetime.utcnow()
            user.auth_provider = AuthProvider.APPLE.value
            
            # Apple private email varsa kaydet
            if apple_user_info["is_private_email"]:
                user.apple_private_email = apple_user_info["email"]
                user.is_apple_provided_email = True
                
        else:
            # Yeni kullanıcı oluştur
            is_new_user = True
            logger.info(f"🍎 Yeni kullanıcı oluşturuluyor: {apple_user_info['email']}")
            
            user = User(
                email=apple_user_info["email"],
                apple_id=apple_user_info["apple_id"],
                apple_private_email=apple_user_info["email"] if apple_user_info["is_private_email"] else None,
                is_apple_provided_email=apple_user_info["is_private_email"],
                full_name=apple_user_info["full_name"],
                auth_provider=AuthProvider.APPLE.value,
                is_verified=True,  # Apple email'leri otomatik doğrulanmış sayılır
                last_login_at=datetime.utcnow(),
                last_active_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(user)
        
        await db.commit()
        await db.refresh(user)
        
        # ==================== JWT TOKEN ÜRET ====================
        
        tokens = security_manager.create_tokens(
            user_id=str(user.id),
            email=user.email,
            role=user.role if isinstance(user.role, str) else user.role.value,
            is_verified=user.is_verified,
            is_active=user.is_active,
            auth_provider=AuthProvider.APPLE.value
        )
        
        # ==================== TOKEN DEBUG ====================
        print("\n" + "🍎"*50)
        print("🍎 APPLE TOKEN DEBUG")
        print(f"🍎 user.email: {user.email}")
        print(f"🍎 user.id: {user.id}")
        print(f"🍎 is_new_user: {is_new_user}")
        print(f"🍎 Oluşturulan token: {tokens.access_token[:50]}...")
        try:
            import jwt
            decoded = jwt.decode(tokens.access_token, options={"verify_signature": False})
            print(f"🍎 Token içindeki email: {decoded.get('email')}")
            print(f"🍎 Token içindeki sub: {decoded.get('sub')}")
        except Exception as e:
            print(f"🍎 Token decode hatası: {e}")
        print("🍎"*50 + "\n")
        
        # ==================== AUDIT LOG ====================
        
        audit_logger.info(
            f"Apple Sign-In {'new user' if is_new_user else 'existing user'}: {user.email}",
            extra={
                "user_id": str(user.id),
                "is_new_user": is_new_user,
                "auth_provider": "apple",
                "is_private_email": apple_user_info["is_private_email"]
            }
        )
        
        # ==================== RESPONSE ====================
        
        user_minimal = UserMinimal(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            avatar_url=user.avatar_url,
            role=user.role if isinstance(user.role, str) else user.role.value,
            is_seller=user.is_seller
        )
        
        response = AuthResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type="bearer",
            expires_in=3600,
            user=user_minimal.model_dump(),
            is_new_user=is_new_user
        )
        
        logger.info(f"🍎 Apple auth başarılı: {user.email}")
        return response
        
    except Exception as e:
        logger.error(f"🍎 Apple auth error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Apple authentication failed: {str(e)}"
        )
   

# ==================== LEGACY GOOGLE OAUTH (REDIRECT FLOW) ====================

@router.get("/google/login")
async def google_login():
    """
    Start Google OAuth flow (legacy redirect flow).
    Redirects user to Google login page.
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth is not configured"
        )
    
    # Google OAuth URL
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={settings.GOOGLE_CLIENT_ID}&"
        f"redirect_uri={settings.GOOGLE_REDIRECT_URI}&"
        "response_type=code&"
        "scope=email profile&"
        "access_type=offline&"
        "prompt=consent"
    )
    
    logger.info(f"Redirecting to Google OAuth: {auth_url[:100]}...")
    return RedirectResponse(auth_url)


@router.get("/google/callback")
async def google_callback(
    code: str = Query(...),
    db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """
    Google OAuth callback endpoint (legacy).
    Exchange authorization code for tokens.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth is not configured"
        )
    
    try:
        # Exchange code for tokens
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        
        async with httpx.AsyncClient() as client:
            token_response = await client.post(token_url, data=token_data)
            token_response.raise_for_status()
            tokens = token_response.json()
        
        id_token = tokens.get("id_token")
        if not id_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No ID token received from Google"
            )
        
        # Use the new Google auth endpoint logic
        request = GoogleAuthRequest(id_token=id_token)
        return await google_auth(request, db)
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during Google OAuth: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google OAuth error: {e.response.text}"
        )
    except Exception as e:
        logger.error(f"Google OAuth error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed"
        )


# ==================== TOKEN MANAGEMENT ====================

@router.post("/refresh")
async def refresh_token(
    data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """
    Refresh access token using refresh token.
    """
    try:
        # Decode refresh token
        payload = security_manager.decode_token(data.refresh_token)
        
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        user_id = payload.get("sub")  # string
        email = payload.get("email")  # string
        
        result = await db.execute(
            select(User).where(
                (User.id == uuid.UUID(user_id)) &
                (User.email == email) &
                (User.is_active == True)
            )
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        # ✅ DÜZELTİLDİ - .value YOK!
        tokens = security_manager.create_tokens(
            user_id=str(user.id),
            email=user.email,
            role=user.role if isinstance(user.role, str) else user.role.value,  # ✅
            is_verified=user.is_verified,
            is_active=user.is_active
        )
        
        logger.info(f"Token refreshed for user: {user.email}")
        return tokens
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
class LogoutRequest(BaseModel):
    token: Optional[str] = None

@router.post("/logout")
async def logout(
    data: LogoutRequest,
    current_user: dict = Depends(get_current_user_clean)
):
    """
    Logout user by revoking tokens.
    """
    if data.token:
        security_manager.revoke_token(data.token)

    logger.info(f"User logged out: {current_user['email']}")
    return {"message": "Successfully logged out"}


# ==================== CURRENT USER ====================


