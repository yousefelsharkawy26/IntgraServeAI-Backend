# models/base.py
from sqlalchemy import Column, DateTime, func, JSON
from sqlalchemy.types import Uuid as UUID
from sqlalchemy.dialects.postgresql import JSONB
from core.database import Base
import uuid

# Define a JSON type that degrades gracefully to standard JSON on non-Postgres databases
JSONVariant = JSON().with_variant(JSONB, 'postgresql')


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