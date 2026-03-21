"""
Google OAuth Authentication Service
"""
import httpx
from typing import Dict, Any, Optional
import jwt
from fastapi import HTTPException, status
from config.config import settings
import json


class GoogleAuthError(Exception):
    """Google authentication error."""
    pass


async def verify_google_token(
    id_token: str, 
    access_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Verify Google OAuth token and return user info.
    
    Args:
        id_token: Google JWT ID token
        access_token: Google OAuth access token (optional)
    
    Returns:
        Dict containing verified user information
    
    Raises:
        HTTPException: If token verification fails
    """
    try:
        # For development/testing without real tokens
        if settings.ENVIRONMENT == "development" and id_token == "test_token":
            return {
                "sub": "07da0742-bf89-4966-a7d0-d5626d40724c", 
                "email": "test@craftora.com",  
                "email_verified": True,
                "name": "Test User",
                "picture": "https://example.com/avatar.jpg",
                "given_name": "Test",
                "family_name": "User",
                "locale": "tr-TR"
            }
        
        # Get Google's public keys
        async with httpx.AsyncClient() as client:
            # Get public keys from Google
            response = await client.get("https://www.googleapis.com/oauth2/v3/certs")
            if response.status_code != 200:
                raise GoogleAuthError("Failed to fetch Google public keys")
            
            jwks = response.json()
            
            # Decode and verify the ID token
            try:
                # Get the key ID from the token header
                unverified_header = jwt.get_unverified_header(id_token)
                kid = unverified_header.get("kid")
                
                # Find the matching key
                key = None
                for jwk in jwks.get("keys", []):
                    if jwk.get("kid") == kid:
                        key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
                        break
                
                if not key:
                    raise GoogleAuthError("No matching key found for token")
                
                # Verify the token
                payload = jwt.decode(
                    id_token,
                    key,
                    algorithms=["RS256"],
                    audience=settings.GOOGLE_CLIENT_ID,
                    issuer=["accounts.google.com", "https://accounts.google.com"]
                )
                
                # Verify email is present and verified
                if not payload.get("email"):
                    raise GoogleAuthError("Email not found in token")
                
                if not payload.get("email_verified", False):
                    raise GoogleAuthError("Email not verified")
                
                # Optionally verify access token
                if access_token:
                    token_info = await verify_access_token(access_token)
                    if token_info.get("sub") != payload.get("sub"):
                        raise GoogleAuthError("Token mismatch")
                
                return {
                    "sub": payload.get("sub"),
                    "email": payload.get("email"),
                    "email_verified": payload.get("email_verified", False),
                    "name": payload.get("name"),
                    "picture": payload.get("picture"),
                    "given_name": payload.get("given_name"),
                    "family_name": payload.get("family_name"),
                    "locale": payload.get("locale", "tr-TR")
                }
                
            except jwt.InvalidTokenError as e:
                raise GoogleAuthError(f"Invalid token: {str(e)}")
                
    except GoogleAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Google authentication failed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Google authentication error: {str(e)}"
        )


async def verify_access_token(access_token: str) -> Dict[str, Any]:
    """
    Verify Google access token.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/oauth2/v3/tokeninfo",
            params={"access_token": access_token}
        )
        
        if response.status_code != 200:
            raise GoogleAuthError("Invalid access token")
        
        return response.json()


async def get_google_user_info(access_token: str) -> Dict[str, Any]:
    """
    Get user info from Google API using access token.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        if response.status_code != 200:
            raise GoogleAuthError("Failed to fetch user info")
        
        return response.json()