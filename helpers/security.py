import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Union
from jose import JWTError, jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from google.auth.transport import requests
from google.oauth2 import id_token
from google.auth.exceptions import GoogleAuthError
import secrets
import aiohttp
import json
from cachetools import TTLCache
from pydantic import BaseModel
from typing import Optional
from config.config import settings
from sqlalchemy.ext.asyncio import AsyncSession
from database.database import get_db
import traceback

# Configure logging
logger = logging.getLogger(__name__)

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_PREFIX}/auth/login",
    auto_error=True
)

class TokenResponse(BaseModel):
    """Token response model - Moved from routers.auth"""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    email: str
    role: str
    is_verified: bool
    is_active: bool
    auth_provider: str = "google"


class SecurityManager:
    """Security manager for OAuth authentication and authorization."""
    
    def __init__(self):
        # In-memory cache for Apple public keys (24 hours)
        self.apple_keys_cache = TTLCache(maxsize=1, ttl=86400)
        # In-memory token cache (5 minutes)
        self.token_cache = TTLCache(maxsize=1000, ttl=300)
    
    # ==================== JWT TOKEN HANDLING ====================
    
    def create_access_token(
        self, 
        data: Dict[str, Any], 
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create JWT access token."""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access",
            "jti": secrets.token_urlsafe(16)
        })
        
        return jwt.encode(
            to_encode, 
            settings.SECRET_KEY, 
            algorithm=settings.ALGORITHM
        )
    
    def create_refresh_token(
        self, 
        user_id: str, 
        email: str
    ) -> tuple[str, str]:
        """Create JWT refresh token with token family."""
        token_family = secrets.token_urlsafe(16)
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
        to_encode = {
            "sub": user_id,
            "email": email,
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "refresh",
            "family": token_family,
            "jti": secrets.token_urlsafe(16)
        }
        
        encoded_jwt = jwt.encode(
            to_encode, 
            settings.SECRET_KEY, 
            algorithm=settings.ALGORITHM
        )
        return encoded_jwt, token_family
    
    def create_tokens(
        self, 
        user_id: str, 
        email: str, 
        role: str,
        auth_provider: str = "google",
        is_verified: bool = True,
        is_active: bool = True
    ) -> TokenResponse:
        """Create both access and refresh tokens."""
        access_data = {
            "sub": user_id,
            "email": email,
            "role": role,
            "auth_provider": auth_provider,
            "is_verified": is_verified,
            "is_active": is_active
        }
        
        access_token = self.create_access_token(access_data)
        refresh_token, token_family = self.create_refresh_token(user_id, email)
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_id=user_id,
            email=email,
            role=role,
            is_verified=is_verified,
            is_active=is_active,
            auth_provider=auth_provider
        )
    
    def decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        print(f"\n🔐 DECODE_TOKEN - Gelen token (ilk 50): {token[:50]}...")
        try:
            cache_key = f"token:{hash(token)}"
            print(f"   Cache key: {cache_key}")
        
            if cache_key in self.token_cache:
                print(f"   ✅ Cache'den alındı!")
                return self.token_cache[cache_key]
            print(f"   ⏳ JWT decode ediliyor...")
            payload = jwt.decode(
                token, 
                settings.SECRET_KEY, 
                algorithms=[settings.ALGORITHM]
            )
            print(f"   ✅ JWT decode başarılı!")
            print(f"   📦 Payload: {payload}")
        
            if payload.get("type") not in ["access", "refresh"]:
                print(f"   ❌ Geçersiz token tipi: {payload.get('type')}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type"
                )
            self.token_cache[cache_key] = payload
            return payload
        except jwt.ExpiredSignatureError:
            print(f"   ❌ Token süresi dolmuş!")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        except JWTError as e:
            print(f"   ❌ JWT decode hatası: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials"
            )
        
    # ==================== GOOGLE OAUTH ====================
    
    async def verify_google_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify Google ID token and return user info."""
        if not settings.GOOGLE_CLIENT_ID:
            logger.error("Google OAuth not configured")
            return None
        try:
            request = requests.Request()
            id_info = id_token.verify_oauth2_token(
                token,
                requests.Request(),
                settings.GOOGLE_CLIENT_ID
                )
            # Validate
            if id_info['aud'] != settings.GOOGLE_CLIENT_ID:
                logger.error(f"Invalid audience: {id_info['aud']} != {settings.GOOGLE_CLIENT_ID}")
                return None
            valid_issuers = ['accounts.google.com', 'https://accounts.google.com']
            if id_info['iss'] not in valid_issuers:
                logger.error(f"Invalid issuer: {id_info['iss']}")
                return None
            exp_time = datetime.fromtimestamp(id_info['exp'], tz=timezone.utc)
            current_time = datetime.now(timezone.utc)
            if exp_time < current_time:
                time_diff = (current_time - exp_time).total_seconds()
                logger.warning(f"Token expired but within grace period: {time_diff}s")
            if not id_info.get('email_verified', False):
                logger.warning(f"Email not verified for: {id_info.get('email')}")
            logger.info(f"Google token verified for: {id_info.get('email')}")
            
            return {
                "google_id": id_info["sub"],
                "email": id_info["email"],
                "email_verified": id_info.get("email_verified", False),
                "full_name": id_info.get("name"),
                "avatar_url": id_info.get("picture"),
                "locale": id_info.get("locale", "en"),
                "given_name": id_info.get("given_name"),
                "family_name": id_info.get("family_name"),
                "auth_provider": "google"
            }
            
        except ValueError as e:
            logger.error(f"Google token verification failed (ValueError): {e}")
            return None
        except GoogleAuthError as e:
            logger.error(f"Google auth error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in Google token verification: {e}", exc_info=True)
            return None
    # ==================== APPLE OAUTH ====================

    
    
    async def _get_apple_public_keys(self) -> Dict[str, Any]:
        """Get Apple's public keys with caching."""
        cache_key = "apple_public_keys"
        if cache_key in self.apple_keys_cache:
            return self.apple_keys_cache[cache_key]
        
        async with aiohttp.ClientSession() as session:
            async with session.get("https://appleid.apple.com/auth/keys") as response:
                keys = await response.json()
                self.apple_keys_cache[cache_key] = keys
                return keys
    
    def _find_apple_public_key(self, keys: Dict[str, Any], kid: str) -> str:
        """Find the correct Apple public key by kid."""
        import jwt as pyjwt
        for key in keys.get("keys", []):
            if key["kid"] == kid:
                # Convert JWK to PEM format
                return pyjwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
        raise ValueError(f"Apple public key not found for kid: {kid}")
    
    async def verify_apple_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify Apple ID token and return user info."""
        if not settings.APPLE_CLIENT_ID:
            logger.error("Apple OAuth not configured")
            return None
        
        try:
            # Get Apple public keys
            apple_public_keys = await self._get_apple_public_keys()
            
            # Decode header to get kid
            header = jwt.get_unverified_header(token)
            kid = header.get('kid')
            
            if not kid:
                raise ValueError("Apple token missing kid")
            
            # Find correct public key
            public_key = self._find_apple_public_key(apple_public_keys, kid)
            
            # Verify token
            payload = jwt.decode(
                token,
                public_key,
                algorithms=['RS256'],
                audience=settings.APPLE_CLIENT_ID,
                issuer='https://appleid.apple.com'
            )
            
            # Check expiration
            if datetime.fromtimestamp(payload['exp']) < datetime.utcnow():
                raise ValueError("Apple token has expired")
            
            # Extract user info
            email = payload.get("email")
            is_private_email = email and "@privaterelay.appleid.com" in email
            
            return {
                "apple_id": payload["sub"],
                "email": email,
                "is_private_email": is_private_email,
                "email_verified": True,
                "full_name": None,  # Apple only provides name on first login
                "auth_provider": "apple"
            }
            
        except Exception as e:
            logger.error(f"Apple token verification failed: {e}")
            return None
    
    # ==================== AUTHORIZATION ====================
    
    def require_role(self, required_role: str, user_role: str) -> bool:
        """Check if user has required role."""
        role_hierarchy = {
            "admin": ["admin", "seller", "user"],
            "seller": ["seller", "user"],
            "user": ["user"]
        }
        
        if required_role not in role_hierarchy:
            return False
        
        return user_role in role_hierarchy[required_role]
    
    def require_auth_provider(self, required_provider: str, user_provider: str) -> bool:
        """Check if user authenticated with specific provider."""
        return user_provider == required_provider
    
    def revoke_token(self, token: str) -> bool:
        try:
            payload = self.decode_token(token)
            if not payload:
                logger.warning("❌ Revoke failed: Invalid token")
                return False
            token_id = payload.get("jti")
            if not token_id:
                logger.warning("❌ Revoke failed: No jti in token")
                return False
            logger.info(f"✅ Token revoked: {token_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Revoke error: {e}")
            return False
        
# Global security manager instance
security_manager = SecurityManager()


# ==================== FASTAPI DEPENDENCIES ====================
    


async def get_current_user_clean(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    JWT token'dan current user'ı çözer - TEMİZ VERSİYON
    """
    print("\n" + "🧼"*50)
    print("🧼 GET CURRENT USER CLEAN BAŞLADI!")
    print(f"🧼 Token (ilk 50): {token[:50]}...")
    
    try:
        # 1. Token'ı decode et
        payload = security_manager.decode_token(token)
        if not payload:
            print("🧼❌ Payload boş!")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials"
            )
        
        print(f"🧼 Payload içindeki anahtarlar: {list(payload.keys())}")
        
        # 2. sub'dan user_id'yi al
        user_id = payload.get("sub")
        print(f"🧼 Token'daki sub: {user_id}")
        
        if not user_id:
            print("🧼❌ Token'da sub yok!")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing user ID"
            )
        
        # 3. UUID formatını kontrol et
        from uuid import UUID
        try:
            user_uuid = UUID(user_id)
            print(f"🧼 UUID'ye çevrildi: {user_uuid}")
        except ValueError:
            print(f"🧼❌ Geçersiz UUID formatı: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid user ID format: {user_id}"
            )
        
        # 4. Database'den kullanıcıyı getir
        from sqlalchemy import select
        from models.user import User
        
        result = await db.execute(
            select(User).where(User.id == user_uuid)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"🧼❌ Kullanıcı bulunamadı! ID: {user_id}")
            
            # Debug: Tüm kullanıcıları listele
            all_users = await db.execute(select(User.id, User.email))
            users_list = all_users.all()
            print("🧼 DB'deki kullanıcılar:")
            for u in users_list:
                print(f"   - {u.id} | {u.email}")
                if str(u.id) == user_id:
                    print(f"   ✅ EŞLEŞEN VAR! {u.id}")
            
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User not found with id: {user_id}"
            )
        
        print(f"🧼✅ Kullanıcı bulundu: {user.email}")
        print(f"🧼✅ Kullanıcı ID: {user.id}")
        
        # 5. User dict döndür
        return {
            "user_id": str(user.id),
            "sub": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value if hasattr(user.role, 'value') else user.role,
            "auth_provider": user.auth_provider,
            "is_verified": user.is_verified,
            "is_active": user.is_active
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"🧼💥 Beklenmeyen hata: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication error: {str(e)}"
        )
    
   
async def get_current_active_user(
    current_user: Dict[str, Any] = Depends(get_current_user_clean)
) -> Dict[str, Any]:
    """Get current active user."""
    if not current_user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user"
        )
    return current_user


async def get_current_verified_user(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Get current verified user."""
    if not current_user.get("is_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified"
        )
    return current_user


async def require_role(required_role: str):
    """Dependency to require specific role."""
    async def role_checker(current_user: Dict[str, Any] = Depends(get_current_active_user)):
        if not security_manager.require_role(
            required_role, 
            current_user.get("role", "user")
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {required_role} role"
            )
        return current_user
    return role_checker


async def require_auth_provider(required_provider: str):
    """Dependency to require specific auth provider."""
    async def provider_checker(current_user: Dict[str, Any] = Depends(get_current_active_user)):
        if not security_manager.require_auth_provider(
            required_provider,
            current_user.get("auth_provider", "google")
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {required_provider} authentication"
            )
        return current_user
    return provider_checker


# ==================== TEST UTILITIES ====================

async def get_test_user_token(
    user_id: str = "test-user-id",
    email: str = "test@example.com",
    role: str = "user",
    auth_provider: str = "google"
) -> str:
    """Create test JWT token."""
    test_user_data = {
        "sub": user_id,
        "email": email,
        "role": role,
        "auth_provider": auth_provider,
        "is_verified": True,
        "is_active": True,
        "exp": datetime.utcnow() + timedelta(minutes=30),
        "iat": datetime.utcnow(),
        "type": "access",
        "jti": secrets.token_urlsafe(16)
    }
    
    return jwt.encode(
        test_user_data, 
        settings.SECRET_KEY, 
        algorithm=settings.ALGORITHM
    )
    

# helpers/security.py içinde, SecurityManager class'ının içine:

