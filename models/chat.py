from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer, Numeric, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from models.base import BaseModel
from models.ticket import SenderType
import enum


class ResponseType(str, enum.Enum):
    """Response Type Enum"""
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"
    NEUTRAL = "neutral"


class ChatConversation(BaseModel):
    """Chat Conversations table"""
    __tablename__ = 'chat_conversations'
    
    external_customer_id = Column(String(255), nullable=True, index=True)
    customer_email = Column(String(255), nullable=False, index=True)
    customer_name = Column(String(255), nullable=False)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    messages = relationship('ChatMessage', back_populates='conversation', cascade='all, delete-orphan')
    rating = relationship('AgentRating', back_populates='conversation', uselist=False, cascade='all, delete-orphan')
    # ✅ أضف relationship للـ ActionExecutionLog
    action_logs = relationship('ActionExecutionLog', back_populates='chat_conversation', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f"<ChatConversation {self.session_id}>"


class ChatMessage(BaseModel):
    """Chat Messages table"""
    __tablename__ = 'chat_messages'
    
    chat_conversation_id = Column(UUID(as_uuid=True), ForeignKey('chat_conversations.id', ondelete='CASCADE'), nullable=False, index=True)
    sender_type = Column(SQLEnum(SenderType), nullable=False)
    message_text = Column(Text, nullable=False)
    confidence_score = Column(Numeric(5, 2), nullable=True)
    intent_detected = Column(String(255), nullable=True)
    entities_extracted = Column(JSONB, nullable=True)
    
    # Relationships
    conversation = relationship('ChatConversation', back_populates='messages')
    
    def __repr__(self):
        return f"<ChatMessage {self.id} in Conversation {self.chat_conversation_id}>"


class AgentRating(BaseModel):
    """Agent Ratings table"""
    __tablename__ = 'agent_ratings'
    
    chat_conversation_id = Column(UUID(as_uuid=True), ForeignKey('chat_conversations.id', ondelete='CASCADE'), unique=True, nullable=False, index=True)
    external_customer_id = Column(String(255), nullable=True, index=True)
    rating = Column(Integer, nullable=False)
    feedback = Column(Text, nullable=True)
    response_type = Column(SQLEnum(ResponseType), nullable=True)
    
    # Relationships
    conversation = relationship('ChatConversation', back_populates='rating')
    
    def __repr__(self):
        return f"<AgentRating {self.rating} for Conversation {self.chat_conversation_id}>"