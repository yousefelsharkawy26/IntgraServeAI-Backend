# models/chat.py
#
# CHANGES vs. original:
#   * Added `ChatAttachment` model (for `/chat/upload` + `/chat/messages/{id}/attachments`).
#   * Added `attachments` relationship on `ChatMessage` (back-populates on attachment).

from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Boolean, DateTime, Text, Integer, Numeric,
    ForeignKey, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import Uuid as UUID
from models.base import BaseModel, JSONVariant
from models.ticket import SenderType
import enum


class ResponseType(str, enum.Enum):
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"
    NEUTRAL = "neutral"


class ChatConversation(BaseModel):
    __tablename__ = 'chat_conversations'

    external_customer_id = Column(String(255), nullable=True, index=True)
    customer_email = Column(String(255), nullable=False, index=True)
    customer_name = Column(String(255), nullable=False)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    pending_state = Column(JSONVariant, nullable=True)  # Stores serialized messages + pause metadata
    ai_context = Column(JSONVariant, nullable=True)     # Optional metadata for the AI session

    messages = relationship('ChatMessage', back_populates='conversation', cascade='all, delete-orphan')
    rating = relationship('AgentRating', back_populates='conversation', uselist=False, cascade='all, delete-orphan')
    action_logs = relationship('ActionExecutionLog', back_populates='chat_conversation', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<ChatConversation {self.session_id}>"


class ChatMessage(BaseModel):
    __tablename__ = 'chat_messages'

    chat_conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey('chat_conversations.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    sender_type = Column(SQLEnum(SenderType), nullable=False)
    message_text = Column(Text, nullable=False)
    confidence_score = Column(Numeric(5, 2), nullable=True)
    intent_detected = Column(String(255), nullable=True)
    entities_extracted = Column(JSONVariant, nullable=True)

    conversation = relationship('ChatConversation', back_populates='messages')
    # NEW: attachments relationship
    attachments = relationship(
        'ChatAttachment',
        back_populates='message',
        cascade='all, delete-orphan',
    )

    def __repr__(self):
        return f"<ChatMessage {self.id} in Conversation {self.chat_conversation_id}>"


class AgentRating(BaseModel):
    __tablename__ = 'agent_ratings'

    chat_conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey('chat_conversations.id', ondelete='CASCADE'),
        unique=True,
        nullable=False,
        index=True,
    )
    external_customer_id = Column(String(255), nullable=True, index=True)
    rating = Column(Integer, nullable=False)
    feedback = Column(Text, nullable=True)
    response_type = Column(SQLEnum(ResponseType), nullable=True)

    conversation = relationship('ChatConversation', back_populates='rating')

    def __repr__(self):
        return f"<AgentRating {self.rating} for Conversation {self.chat_conversation_id}>"


# NEW: ChatAttachment model ----------------------------------------------------
class ChatAttachment(BaseModel):
    __tablename__ = 'chat_attachments'

    chat_message_id = Column(
        UUID(as_uuid=True),
        ForeignKey('chat_messages.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    filename = Column(String(500), nullable=False)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    storage_path = Column(String(1000), nullable=False)        # absolute path or remote URI
    storage_backend = Column(String(50), nullable=False, default='local')  # local | s3 | gcs ...
    uploaded_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    message = relationship('ChatMessage', back_populates='attachments')

    def __repr__(self):
        return f"<ChatAttachment {self.filename} ({self.size_bytes}B)>"