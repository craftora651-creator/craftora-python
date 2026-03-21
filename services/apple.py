"""
Apple Sign-In Authentication Service
"""
import jwt
import httpx
from typing import Dict, Any, Optional
import json
from fastapi import HTTPException, status
from config.config import settings
import time


class AppleAuthError(Exception):
    """Apple authentication error."""
    pass

async def verify_apple_token(
    identity_token: str,
    authorization_code: Optional[str] = None,
    user_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Verify Apple Sign-In token.
    
    Args:
        identity_token: Apple JWT identity token
        authorization_code: Apple authorization code (optional, for first-time login)
        user_info: Apple user info (optional, contains name only on first login)
    
    Returns:
        Dict containing verified user information
    """
    try:
        # For development/testing without real tokens
        if settings.ENVIRONMENT == "development" and identity_token == "test_token":
            return {
                "sub": "001234.567890abcdef.1234",
                "email": "user@privaterelay.appleid.com",
                "email_verified": True,
                "is_private_email": True,
                "name": user_info.get("name") if user_info else None
            }
        
        # Decode token header to get key ID
        unverified_header = jwt.get_unverified_header(identity_token)
        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg", "RS256")
        
        # Get Apple's public keys
        async with httpx.AsyncClient() as client:
            response = await client.get("https://appleid.apple.com/auth/keys")
            if response.status_code != 200:
                raise AppleAuthError("Failed to fetch Apple public keys")
            
            jwks = response.json()
            
            # Find the matching key
            key = None
            for jwk in jwks.get("keys", []):
                if jwk.get("kid") == kid:
                    key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
                    break
            
            if not key:
                raise AppleAuthError("No matching key found for token")
            
            # Verify the token
            payload = jwt.decode(
                identity_token,
                key,
                algorithms=[alg],
                audience=settings.APPLE_CLIENT_ID,
                issuer="https://appleid.apple.com"
            )
            
            # Validate required claims
            if not payload.get("sub"):
                raise AppleAuthError("Subject (sub) not found in token")
            
            if payload.get("aud") != settings.APPLE_CLIENT_ID:
                raise AppleAuthError(f"Invalid audience: {payload.get('aud')}")
            
            if payload.get("iss") != "https://appleid.apple.com":
                raise AppleAuthError(f"Invalid issuer: {payload.get('iss')}")
            
            # Check token expiration
            current_time = int(time.time())
            if payload.get("exp", 0) < current_time:
                raise AppleAuthError("Token has expired")
            
            # Check email
            email = payload.get("email")
            email_verified = payload.get("email_verified", False)
            
            # Apple private relay email check
            is_private_email = False
            if email and ("privaterelay.appleid.com" in email or "appleid.com" in email):
                is_private_email = True
            
            # If email is not in token, it might be in user_info (first login only)
            if not email and user_info:
                email = user_info.get("email")
                if email:
                    is_private_email = "privaterelay.appleid.com" in email
            
            return {
                "sub": payload.get("sub"),
                "email": email,
                "email_verified": email_verified or bool(email),
                "is_private_email": is_private_email,
                "name": user_info.get("name") if user_info else None
            }
            
    except jwt.InvalidTokenError as e:
        raise AppleAuthError(f"Invalid token: {str(e)}")
    except AppleAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Apple authentication failed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Apple authentication error: {str(e)}"
        )


async def validate_authorization_code(
    authorization_code: str,
    client_id: str,
    client_secret: str
) -> Dict[str, Any]:
    """
    Validate Apple authorization code and exchange for tokens.
    Only needed for additional verification.
    """
    async with httpx.AsyncClient() as client:
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": authorization_code,
            "grant_type": "authorization_code"
        }
        
        response = await client.post(
            "https://appleid.apple.com/auth/token",
            data=data
        )
        
        if response.status_code != 200:
            raise AppleAuthError("Invalid authorization code")
        
        return response.json()