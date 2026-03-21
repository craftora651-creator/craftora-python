from datetime import datetime
from typing import Optional, Generic, TypeVar, List, Any
from pydantic import BaseModel, Field, ConfigDict
from pydantic.generics import GenericModel

# Type variable for generic responses
T = TypeVar('T')


class BaseSchema(BaseModel):
    """Base schema with common configurations."""
    model_config = ConfigDict(
        from_attributes=True,  # Allows ORM mode (from_orm)
        populate_by_name=True,  # Allows alias population
        arbitrary_types_allowed=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )


class TimestampSchema(BaseSchema):
    """Base schema with timestamp fields."""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class IDSchema(BaseSchema):
    """Schema with ID field."""
    id: str = Field(..., description="Unique identifier")


class PaginationParams(BaseSchema):
    """Pagination parameters for list endpoints."""
    page: int = Field(1, ge=1, description="Page number")
    limit: int = Field(20, ge=1, le=100, description="Items per page")
    sort_by: Optional[str] = Field(None, description="Sort field")
    sort_order: Optional[str] = Field(None, pattern="^(asc|desc)$", description="Sort order")


class PaginatedResponse(GenericModel, Generic[T]):
    """Generic paginated response."""
    items: List[T]
    total: int
    page: int
    limit: int
    total_pages: int
    has_next: bool
    has_prev: bool


class SuccessResponse(BaseSchema):
    """Standard success response."""
    success: bool = True
    message: str
    data: Optional[Any] = None


class ErrorResponse(BaseSchema):
    """Standard error response."""
    success: bool = False
    error: str
    code: Optional[str] = None
    details: Optional[Any] = None


class ValidationError(BaseSchema):
    """Validation error detail."""
    field: str
    message: str
    type: Optional[str] = None