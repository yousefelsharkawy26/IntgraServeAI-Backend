from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from models.base import BaseModel, TimestampMixin
import enum


class SystemType(BaseModel):
    """System Types table"""
    __tablename__ = 'system_types'
    
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    
    # Relationships
    system_actions = relationship('SystemAction', back_populates='system_type')
    
    def __repr__(self):
        return f"<SystemType {self.name}>"


class ActionProtocol(BaseModel):
    """Action Protocols table"""
    __tablename__ = 'action_protocols'
    
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    
    # Relationships
    system_actions = relationship('SystemAction', back_populates='action_protocol')
    
    def __repr__(self):
        return f"<ActionProtocol {self.name}>"


class SystemAction(BaseModel, TimestampMixin):
    """System Actions table"""
    __tablename__ = 'system_actions'
    
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    endpoint_url = Column(String(1000), nullable=False)
    request_template = Column(JSONB, nullable=True)
    response_mapping = Column(JSONB, nullable=True)
    timeout_seconds = Column(Integer, default=30, nullable=False)
    retry_count = Column(Integer, default=3, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    meta_data = Column(JSONB, nullable=True)
    
    # Foreign Keys
    system_type_id = Column(UUID(as_uuid=True), ForeignKey('system_types.id', ondelete='CASCADE'), nullable=False, index=True)
    action_protocol_id = Column(UUID(as_uuid=True), ForeignKey('action_protocols.id', ondelete='CASCADE'), nullable=False, index=True)
    api_authentication_id = Column(UUID(as_uuid=True), ForeignKey('api_authentications.id', ondelete='SET NULL'), nullable=True, index=True)
    
    # Relationships
    system_type = relationship('SystemType', back_populates='system_actions')
    action_protocol = relationship('ActionProtocol', back_populates='system_actions')
    api_authentication = relationship('ApiAuthentication', back_populates='system_actions')
    execution_logs = relationship('ActionExecutionLog', back_populates='system_action', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f"<SystemAction {self.name}>"


class ActionExecutionLog(BaseModel):
    """Action Execution Logs table"""
    __tablename__ = 'action_execution_logs'
    
    system_action_id = Column(UUID(as_uuid=True), ForeignKey('system_actions.id', ondelete='CASCADE'), nullable=False, index=True)
    external_customer_id = Column(String(255), nullable=True, index=True)
    request_payload = Column(JSONB, nullable=True)
    response_payload = Column(JSONB, nullable=True)
    status = Column(String(50), nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    
    # Foreign Key to ChatConversation (optional - can be null)
    chat_conversation_id = Column(
        UUID(as_uuid=True), 
        ForeignKey('chat_conversations.id', ondelete='CASCADE'), 
        nullable=True,  # ✅ اجعلها nullable
        index=True
    )
    
    # Relationships
    system_action = relationship('SystemAction', back_populates='execution_logs')
    # ✅ استخدم اسم مختلف - 'chat_conversation' بدلاً من 'conversation'
    chat_conversation = relationship('ChatConversation', back_populates='action_logs')
    
    def __repr__(self):
        return f"<ActionExecutionLog {self.id} - Status: {self.status}>"