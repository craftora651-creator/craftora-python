from datetime import datetime
from typing import Any, Optional
from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, declared_attr
import uuid

class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models.
    READ-ONLY models only - database already exists.
    """
    
    # Automatically generate table name from class name
    @declared_attr.directive
    def __tablename__(cls) -> str:
        return cls.__name__.lower()
    
    # Common fields for all tables
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
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
    
    def to_dict(self, exclude: Optional[set] = None) -> dict[str, Any]:
        """
        Convert model to dictionary.
        
        Args:
            exclude: Set of field names to exclude
            
        Returns:
            Dictionary representation
        """
        exclude = exclude or set()
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
            if column.name not in exclude
        }
    
    def to_json(self) -> dict[str, Any]:
        """Convert model to JSON-serializable dictionary."""
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            # Convert datetime to ISO format
            if isinstance(value, datetime):
                result[column.name] = value.isoformat()
            # Convert UUID to string
            elif hasattr(value, 'hex'):
                result[column.name] = str(value)
            else:
                result[column.name] = value
        return result
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<{self.__class__.__name__}(id={self.id})>"