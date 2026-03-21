import os
import secrets
from typing import List, Optional, Union
from pydantic import AnyHttpUrl, field_validator, EmailStr
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from typing import Dict
from pydantic import Field

load_dotenv()

class Settings(BaseSettings):
    # ==================== ENVIRONMENT ====================
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    # ==================== API CONFIG ====================
    API_PREFIX: str = "/api"
    PROJECT_NAME: str = "Craftora Platform"
    PROJECT_VERSION: str = "1.0.0"
    PROJECT_DESCRIPTION: str = "E-commerce platform for digital creators"
    
    SECRET_KEY: str  # Pydantic otomatik .env'den okuyacak
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 gün (10080 dakika)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30  # 30 gün
    RESET_TOKEN_EXPIRE_MINUTES: int = 15
    VERIFY_TOKEN_EXPIRE_MINUTES: int = 15
    
    # ==================== DATABASE ====================
    DATABASE_URL: str = "postgresql+asyncpg://admin:12345@localhost:5432/CraftoraDesing"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40
    DATABASE_POOL_RECYCLE: int = 3600
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_ECHO: bool = False
    
    # ==================== REDIS ====================
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_POOL_SIZE: int = 10
    REDIS_DECODE_RESPONSES: bool = True
    
    # ==================== CORS ====================
    BACKEND_CORS_ORIGINS: List[str] = Field(default_factory=list)
    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v
    
    # ==================== GOOGLE OAUTH ====================
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:9003/api/auth/google/callback"

    # ==================== APPLE OAUTH ====================
    APPLE_CLIENT_ID: Optional[str] = None
    APPLE_TEAM_ID: Optional[str] = None
    APPLE_KEY_ID: Optional[str] = None
    APPLE_PRIVATE_KEY: Optional[str] = None
    APPLE_REDIRECT_URI: str = "http://localhost:9003/api/auth/apple/callback"
    
    # ==================== STRIPE ====================
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    
    # ==================== AWS S3 ====================
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    AWS_S3_BUCKET: str = "craftora-uploads"
    AWS_S3_ENDPOINT_URL: Optional[str] = None
    
    # ==================== EMAIL ====================
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_TLS: bool = True
    SMTP_FROM_EMAIL: EmailStr = "noreply@craftora.com"
    SMTP_FROM_NAME: str = "Craftora Platform"
    
    # ==================== RATE LIMITING ====================
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_BURST: int = 20
    
    # ==================== MONITORING ====================
    SENTRY_DSN: Optional[str] = None
    PROMETHEUS_ENABLED: bool = True
    HEALTH_CHECK_ENABLED: bool = True
    
    # ==================== CACHE ====================
    CACHE_ENABLED: bool = True
    CACHE_TTL: int = 300
    CACHE_MAX_SIZE: int = 1000
    
    # ==================== FILE UPLOAD ====================
    MAX_UPLOAD_SIZE: int = 100 * 1024 * 1024
    ALLOWED_FILE_TYPES: List[str] = [
        "image/jpeg", "image/png", "image/gif", "image/webp",
        "application/pdf", "application/zip",
        "video/mp4", "video/quicktime",
        "audio/mpeg", "audio/wav"
    ]
    
    # ==================== FEATURE FLAGS ====================
    FEATURE_GOOGLE_AUTH: bool = True
    FEATURE_STRIPE_PAYMENTS: bool = True
    FEATURE_EMAIL_VERIFICATION: bool = True
    FEATURE_TWO_FACTOR_AUTH: bool = False
    FEATURE_REVIEW_SYSTEM: bool = True
    FEATURE_WISHLIST: bool = True
    
    # ==================== VALIDATION ====================
    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL must be set")
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use asyncpg driver")
        return v
    
    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if not v or len(v) < 32:
            raise ValueError("SECRET_KEY must be set in .env and be at least 32 characters")
        return v
    
    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"


# Global settings instance
settings = Settings()

# Environment-specific overrides
if settings.ENVIRONMENT == "production":
    settings.DEBUG = False
    settings.LOG_LEVEL = "WARNING"
    settings.DATABASE_POOL_SIZE = 40
    settings.DATABASE_MAX_OVERFLOW = 80
    settings.RATE_LIMIT_REQUESTS = 200
    settings.CACHE_TTL = 600  # 10 minutes
    
elif settings.ENVIRONMENT == "staging":
    settings.DEBUG = True
    settings.LOG_LEVEL = "INFO"
    settings.DATABASE_POOL_SIZE = 30
    settings.DATABASE_MAX_OVERFLOW = 60




# Ekle: Security headers
SECURITY_HEADERS: Dict[str, str] = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains"
}

# Ekle: Session management
SESSION_TIMEOUT: int = 3600  # 1 saat
SESSION_REFRESH: bool = True
MAX_SESSIONS_PER_USER: int = 5

# Ekle: Password policy
PASSWORD_MIN_LENGTH: int = 8
PASSWORD_REQUIRE_UPPERCASE: bool = True
PASSWORD_REQUIRE_NUMBERS: bool = True
PASSWORD_REQUIRE_SPECIAL: bool = True

# config.py'nin en altına şunu 
print(f"✅ TOKEN SÜRESİ: {settings.ACCESS_TOKEN_EXPIRE_MINUTES} dakika")