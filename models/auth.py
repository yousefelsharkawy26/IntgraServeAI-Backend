from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from models.base import BaseModel, TimestampMixin
from sqlalchemy import ForeignKey


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
    encrypted_primary_secret = Column(Text, nullable=False)  # Encrypted API key/token
    encrypted_secondary_secret = Column(Text, nullable=True)  # For OAuth or additional secrets
    meta_data = Column(JSONB, nullable=True)  # Additional auth data
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    # Foreign Keys
    api_auth_type_id = Column(UUID(as_uuid=True), ForeignKey('api_auth_types.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Relationships
    auth_type = relationship('ApiAuthType', back_populates='api_authentications')
    system_actions = relationship('SystemAction', back_populates='api_authentication')
    
    def __repr__(self):
        return f"<ApiAuthentication {self.name}>"