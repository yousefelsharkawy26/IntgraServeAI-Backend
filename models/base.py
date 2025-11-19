from sqlalchemy import Column, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from core.database import Base
import uuid


class BaseModel(Base):
    """Base model with common fields"""
    __abstract__ = True
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False,
        index=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TimestampMixin:
    """Mixin for created_at and updated_at"""
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)