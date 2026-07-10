# utils/schemas/chat_schemas.py
#
# Pydantic v2 schemas for the Chat REST API.
# Used by apis/v1/chat.py for request/response bodies.

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from models.chat import ResponseType
from models.ticket import SenderType


T = TypeVar("T")


# ----------------------------------------------------------------------------
# Pagination helpers
# ----------------------------------------------------------------------------

class PageMeta(BaseModel):
    page: int
    limit: int
    total: int
    has_more: bool


class Page(BaseModel, Generic[T]):
    items: List[T]
    meta: PageMeta


# ----------------------------------------------------------------------------
# Conversations
# ----------------------------------------------------------------------------

class ConversationCreate(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=255)
    customer_email: str = Field(..., min_length=1, max_length=255)
    customer_name: str = Field(..., min_length=1, max_length=255)
    external_customer_id: Optional[str] = Field(default=None, max_length=255)
    metadata: Optional[Dict[str, Any]] = None


class ConversationUpdate(BaseModel):
    customer_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    is_active: Optional[bool] = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: str
    customer_email: str
    customer_name: str
    external_customer_id: Optional[str] = None
    is_active: bool
    started_at: datetime
    ended_at: Optional[datetime] = None
    has_pending_state: bool = False
    message_count: int = 0


class ConversationDetail(ConversationOut):
    messages: List["MessageOut"] = []
    messages_meta: Optional[PageMeta] = None
    rating: Optional["RatingOut"] = None


# ----------------------------------------------------------------------------
# Messages
# ----------------------------------------------------------------------------

class MessageCreate(BaseModel):
    conversation_id: UUID
    content: str = Field(..., min_length=1)
    sender_type: SenderType = Field(default=SenderType.CUSTOMER)


class MessageEdit(BaseModel):
    content: str = Field(..., min_length=1)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chat_conversation_id: UUID
    sender_type: str
    message_text: str
    confidence_score: Optional[float] = None
    intent_detected: Optional[str] = None
    entities_extracted: Optional[Dict[str, Any]] = None
    created_at: datetime
    attachments: List["AttachmentOut"] = []


# ----------------------------------------------------------------------------
# Attachments
# ----------------------------------------------------------------------------

class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chat_message_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime


class UploadResponse(BaseModel):
    attachment: AttachmentOut
    download_url: str


# ----------------------------------------------------------------------------
# Rating
# ----------------------------------------------------------------------------

class RatingCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    feedback: Optional[str] = None
    response_type: Optional[ResponseType] = None
    external_customer_id: Optional[str] = Field(default=None, max_length=255)


class RatingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chat_conversation_id: UUID
    external_customer_id: Optional[str] = None
    rating: int
    feedback: Optional[str] = None
    response_type: Optional[str] = None
    created_at: datetime


# ----------------------------------------------------------------------------
# Pause / pending state
# ----------------------------------------------------------------------------

class PendingStateOut(BaseModel):
    action_name: str
    params: Dict[str, Any] = Field(default_factory=dict)
    saved_at: Optional[datetime] = None


# Resolve forward refs
ConversationDetail.model_rebuild()
MessageOut.model_rebuild()
