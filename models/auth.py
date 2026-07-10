# models/auth.py
from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.types import Uuid as UUID
from models.base import BaseModel, TimestampMixin, JSONVariant
from sqlalchemy import ForeignKey
from utils.encrypted_type import EncryptedText


class ApiAuthType(BaseModel):
    """API Authentication Types table"""
    __tablename__ = 'api_auth_types'
    
    name = Column(String(100), unique=True, nullable=False, index=True)  # API Key, OAuth2, Bearer, Basic, etc.
    description = Column(Text, nullable=True)
    
    # Relationships
    api_authentications = relationship('ApiAuthentication', back_populates='auth_type')
    
    def __repr__(self):
        return f"<ApiAuthType {self.name}>"


class ApiAuthentication(BaseModel, TimestampMixin):
    """API Authentication table"""
    __tablename__ = 'api_authentications'
    
    name = Column(String(255), nullable=False, index=True)
    primary_secret = Column(EncryptedText, nullable=False)  # Encrypted at rest via EncryptedText
    secondary_secret = Column(EncryptedText, nullable=True)  # For OAuth or additional secrets
    meta_data = Column(JSONVariant, nullable=True)  # Additional auth data
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    # Foreign Keys
    api_auth_type_id = Column(UUID(as_uuid=True), ForeignKey('api_auth_types.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Relationships
    auth_type = relationship('ApiAuthType', back_populates='api_authentications')
    system_actions = relationship('SystemAction', back_populates='api_authentication')
    
    def __repr__(self):
        return f"<ApiAuthentication {self.name}>"


class TokenBlacklist(BaseModel):
    """Revoked token blacklist"""
    __tablename__ = 'token_blacklist'
    
    token_hash = Column(String(255), nullable=False, index=True)
    token_type = Column(String(50), nullable=False)  # "refresh" or "access"
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    def __repr__(self):
        return f"<TokenBlacklist {self.token_type}:{self.token_hash[:16]}...>"