from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import String, Boolean, DateTime, Text, Integer, ForeignKey, CheckConstraint, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, CITEXT  # ✅ CITEXT eklendi
import enum
import uuid
from models.base import Base
from sqlalchemy.sql import func
from sqlalchemy import Column, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


class UserRole(str, enum.Enum):
    """User roles enum - SQL'deki user_role enum'u ile tam uyumlu"""
    USER = "user"
    SELLER = "seller"
    ADMIN = "admin"
    
    def __str__(self):
        return self.value


class AuthProvider(str, enum.Enum):
    """Authentication provider enum - SQL'deki auth_provider string'leri ile uyumlu"""
    GOOGLE = "google"
    APPLE = "apple"
    EMAIL = "email"


class User(Base):
    """User model - SQL users tablosu ile TAM UYUMLU"""
    __tablename__ = "users"
    
    # ===== PRIMARY IDENTIFIER =====
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), 
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid()
    )
    plan: Mapped[str] = mapped_column(String(50), default='free', server_default='free')
    subscription_end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # ===== OAUTH IDENTITY =====
    email: Mapped[str] = mapped_column(CITEXT, unique=True, index=True, nullable=False)
    google_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    apple_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    apple_private_email: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    is_apple_provided_email: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # ✅ auth_provider string (SQL'de VARCHAR(20)) - DÜZELTİLDİ
    auth_provider: Mapped[str] = mapped_column(
        String(20),
        default="google",
        server_default="google",
        nullable=False,
        index=True
    )
    
    # ===== USER PROFILE =====
    full_name: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(String(10), default='tr_TR')
    
    # ===== SELLER SPECIFIC COLUMNS =====
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True)
    stripe_account_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True)
    seller_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    shop_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # ===== YENİ SÜTUNLAR (SQL MIGRATION'DAN) =====
    seller_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    phone_number: Mapped[Optional[str]] = mapped_column(String(20))
    business_name: Mapped[Optional[str]] = mapped_column(String(255))
    
    cj_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cj_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cj_api_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cj_connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cj_last_sync: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # ===== PLATFORM ROLE & STATUS =====
    role: Mapped[UserRole] = mapped_column(
        SQLEnum('user', 'seller', 'admin', name='user_role', create_type=False),
        default=UserRole.USER,
        nullable=False,
        index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    
    # ===== SECURITY =====

    # hashed_password BURADA DA YOK - SİLİNDİ
    
    # ===== PREFERENCES & METADATA =====
    preferences: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        default=lambda: {
            "notifications": {"email": True, "push": True, "marketing": True},
            "appearance": {"theme": "light", "language": "tr", "timezone": "Europe/Istanbul"},
            "privacy": {"show_email": False, "show_last_active": True}
        },
        nullable=False
    )
    user_metadata: Mapped[Dict[str, Any]] = mapped_column(
    JSONB,
    default=lambda: {
        "source": "google_oauth",
        "campaign": None,
        "device_info": {},
        "signup_ip": None
    },
    nullable=False,
    name="user_metadata"  # SQL'deki yeni sütun adı
    )
    
    # ===== TIMESTAMPS =====
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_active_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        default=None,
        index=True
    )
    
    # ===== RELATIONSHIPS =====
    # 1. Sessions
    sessions: Mapped[List["UserSession"]] = relationship(
        "UserSession",
        back_populates="user",
        foreign_keys="[UserSession.user_id]",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    # 2. Audit Logs - USER olarak
    audit_logs: Mapped[List["UserAuditLog"]] = relationship(
        "UserAuditLog",
        back_populates="user",
        foreign_keys="[UserAuditLog.user_id]",
        primaryjoin="User.id == UserAuditLog.user_id",
        viewonly=True
    )
    
    # 3. Email History
    email_history: Mapped[List["UserEmailHistory"]] = relationship(
        "UserEmailHistory", 
        back_populates="user",
        foreign_keys="[UserEmailHistory.user_id]",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    # 4. Actions performed BY this user (changed_by)
    actions_performed: Mapped[List["UserAuditLog"]] = relationship(
        "UserAuditLog",
        back_populates="changer",
        foreign_keys="[UserAuditLog.changed_by]",
        primaryjoin="User.id == UserAuditLog.changed_by",
        viewonly=True
    )
    
    # ===== TABLE CONSTRAINTS =====
    __table_args__ = (
        CheckConstraint('shop_count >= 0', name='chk_shop_count_non_negative'),
        CheckConstraint(
            "phone_number IS NULL OR phone_number ~ '^\\+?[0-9\\s\\-\\(\\)]{10,20}$'",
            name='chk_phone_format'
        )
    )
    
    # ===== HELPER PROPERTIES =====
    @property
    def is_seller(self) -> bool:
        return self.role == UserRole.SELLER
    
    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN
    
    @property
    def is_apple_user(self) -> bool:
        return self.auth_provider == "apple"
    
    @property
    def is_google_user(self) -> bool:
        return self.auth_provider == "google"
    
    @property
    def display_name(self) -> str:
        return self.full_name or self.email.split('@')[0]
    
    @property
    def masked_email(self) -> str:
        if self.is_apple_user and self.is_apple_provided_email:
            return "Private Apple Email"
        return self.email
    
    @property
    def account_age_days(self) -> int:
        if not self.created_at:
            return 0
        now = datetime.now(timezone.utc)
        return (now - self.created_at).days
    
    @property
    def is_cj_connected(self) -> bool:
        """CJ hesabı bağlı mı?"""
        return self.cj_api_key is not None
    def update_cj_sync(self):
        """Son senkronizasyon zamanını güncelle"""
        self.cj_last_sync = datetime.now(timezone.utc)
    
    
    
    # models/user.py'ye EKLE:
    @property
    def total_orders(self) -> int:
        """For backward compatibility - default 0."""
        return 0
    
    @property 
    def total_spent(self) -> int:
        """For backward compatibility - default 0."""
        return 0
    @property
    def last_order_at(self) -> Optional[datetime]:
        """For backward compatibility."""
        return None
    
    # ===== METHODS =====
    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        base = {
            "id": str(self.id),
            "email": self.masked_email,
            "full_name": self.full_name,
            "avatar_url": self.avatar_url,
            "role": self.role if isinstance(self.role, str) else self.role.value,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "auth_provider": self.auth_provider,
            "locale": self.locale,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_active_at": self.last_active_at.isoformat() if self.last_active_at else None,
            "shop_count": self.shop_count,
        }
        
        if include_sensitive or self.is_admin:
            base.update({
                "seller_verified": self.seller_verified,
                "verified_at": self.verified_at.isoformat() if self.verified_at else None,
                "phone_number": self.phone_number,
                "business_name": self.business_name,
                "seller_since": self.seller_since.isoformat() if self.seller_since else None,
                "google_id": self.google_id,
                "apple_id": self.apple_id,
                "stripe_account_id": self.stripe_account_id,
            })
        
        return base
    
    def to_public_dict(self) -> Dict[str, Any]:
        """Public API için dönüşüm (API'de kullanılan)"""
        return {
            "id": str(self.id),
            "email": self.masked_email,
            "full_name": self.full_name,
            "avatar_url": self.avatar_url,
            "role": self.role if isinstance(self.role, str) else self.role.value,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "auth_provider": self.auth_provider,
            "is_seller": self.is_seller,
            "is_admin": self.is_admin,
            "shop_count": self.shop_count,
            "seller_since": self.seller_since.isoformat() if self.seller_since else None,
            "created_at": self.created_at.isoformat(),
            "last_active_at": self.last_active_at.isoformat() if self.last_active_at else None,
            "locale": self.locale,
            "phone": self.phone_number,
            "seller_verified": self.seller_verified,
            "is_apple_user": self.is_apple_user,
            "is_google_user": self.is_google_user
        }
    
    def increment_login_attempts(self):
        pass
    
    def reset_login_attempts(self):
        pass
    
    def update_last_activity(self):
        self.last_active_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
    
    def convert_to_seller(self, stripe_account_id: Optional[str] = None):
        if not self.is_seller:
            self.role = UserRole.SELLER
            self.seller_since = datetime.now(timezone.utc)
            if stripe_account_id:
                self.stripe_account_id = stripe_account_id
    
    def verify_seller(self, documents: Dict[str, Any]):
        if self.is_seller:
            self.seller_verified = True
            self.verified_at = datetime.now(timezone.utc)
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role.value}, auth_provider={self.auth_provider})>"

# ====================== RELATED MODELS ======================

class UserSession(Base):
    """SQL'deki user_sessions tablosu ile uyumlu"""
    __tablename__ = "user_sessions"
    
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # JWT Tokens
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    token_family: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),  # ✅ PG_UUID!
        nullable=False
    )
    
    # Device info
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50))
    device_id: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Security
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Expiry
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sessions")


class UserAuditLog(Base):
    """SQL'deki user_audit_log tablosu ile uyumlu"""
    __tablename__ = "user_audit_log"
    
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    table_name: Mapped[str] = mapped_column(String(50), nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),  # ✅ PG_UUID!
        nullable=False
    )
    
    old_values: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    new_values: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True
    )
    
    ip_address: Mapped[Optional[str]] = mapped_column(String(50))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    # ===== RELATIONSHIPS =====
    # 1. USER için (user_id FK)
    user: Mapped["User"] = relationship(
        "User", 
        back_populates="audit_logs",
        foreign_keys=[user_id]
    )
    
    # 2. CHANGER için (changed_by FK) - TEK BİR TANE OLMALI
    changer: Mapped[Optional["User"]] = relationship(
        "User", 
        back_populates="actions_performed",
        foreign_keys=[changed_by]
    )


class UserEmailHistory(Base):
    """SQL'deki user_email_history tablosu ile uyumlu"""
    __tablename__ = "user_email_history"
    
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    
    old_email: Mapped[str] = mapped_column(String(255), nullable=False)
    new_email: Mapped[str] = mapped_column(String(255), nullable=False)
    
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True
    )
    
    reason: Mapped[Optional[str]] = mapped_column(String(100))
    
    # ===== RELATIONSHIPS =====
    user: Mapped["User"] = relationship(
        "User", 
        back_populates="email_history",
        foreign_keys=[user_id]
    )