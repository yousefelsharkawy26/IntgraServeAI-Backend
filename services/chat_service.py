# services/chat_service.py
#
# NEW file. REST-side business logic for the chat API.
# Thin layer that delegates the cascade / AI-aware operations to AIGatewayService
# and handles everything else (list/get/create/update/rate/upload) directly.

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Set, Tuple
from uuid import UUID

import aiofiles
from fastapi import UploadFile
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.config import settings
from models.chat import (
    AgentRating,
    ChatAttachment,
    ChatConversation,
    ChatMessage,
    ResponseType,
)
from models.ticket import SenderType
from services.ai_gateway_service import AIGatewayService
from utils.exceptions import (
    AttachmentNotFoundException,
    ConversationNotFoundException,
    FileTooLargeException,
    InvalidFileTypeException,
    InvalidRatingException,
    MessageNotFoundException,
)

logger = logging.getLogger(__name__)


class ChatService:
    """REST-side service for chat conversations, messages, attachments, ratings."""

    # ------- Upload policy (override via env / settings if you want) -------
    ALLOWED_CONTENT_TYPES: Set[str] = {
        # images
        "image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp", "image/svg+xml",
        # docs
        "application/pdf",
        "text/plain", "text/csv", "text/markdown",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        # archives
        "application/zip", "application/x-zip-compressed",
    }
    MAX_FILE_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB

    def __init__(self, db: AsyncSession):
        self.db = db
        self.gateway = AIGatewayService()

    # ======================================================================
    # Conversations
    # ======================================================================

    async def list_conversations(
        self,
        page: int = 1,
        limit: int = 20,
        customer_email: Optional[str] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[ChatConversation], int]:
        offset = (page - 1) * limit

        conditions = []
        if customer_email:
            conditions.append(ChatConversation.customer_email == customer_email)
        if is_active is not None:
            conditions.append(ChatConversation.is_active == is_active)
        if search:
            term = f"%{search}%"
            conditions.append(
                or_(
                    ChatConversation.customer_name.ilike(term),
                    ChatConversation.customer_email.ilike(term),
                    ChatConversation.session_id.ilike(term),
                )
            )

        count_q = select(func.count(ChatConversation.id))
        if conditions:
            count_q = count_q.where(and_(*conditions))
        total = (await self.db.execute(count_q)).scalar() or 0

        q = (
            select(ChatConversation)
            .order_by(ChatConversation.started_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if conditions:
            q = q.where(and_(*conditions))

        result = await self.db.execute(q)
        return list(result.scalars().unique().all()), total

    async def get_conversation(
        self,
        conversation_id: UUID,
    ) -> ChatConversation:
        q = (
            select(ChatConversation)
            .where(ChatConversation.id == conversation_id)
            .options(selectinload(ChatConversation.rating))
        )
        result = await self.db.execute(q)
        conv = result.scalar_one_or_none()
        if not conv:
            raise ConversationNotFoundException(conversation_id)
        return conv

    async def create_conversation(
        self,
        session_id: str,
        customer_email: str,
        customer_name: str,
        external_customer_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> ChatConversation:
        existing = await self.db.execute(
            select(ChatConversation).where(ChatConversation.session_id == session_id)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Conversation with session_id '{session_id}' already exists")

        conv = ChatConversation(
            session_id=session_id,
            customer_email=customer_email,
            customer_name=customer_name,
            external_customer_id=external_customer_id,
            is_active=True,
            started_at=datetime.now(timezone.utc),
            ai_context=metadata or {},
        )
        self.db.add(conv)
        await self.db.commit()
        await self.db.refresh(conv)
        return conv

    async def update_conversation(
        self,
        conversation_id: UUID,
        customer_name: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> ChatConversation:
        conv = await self.get_conversation(conversation_id)
        if customer_name is not None:
            conv.customer_name = customer_name
        if is_active is not None:
            conv.is_active = is_active
            if not is_active and not conv.ended_at:
                conv.ended_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(conv)
        return conv

    async def end_conversation(self, conversation_id: UUID) -> ChatConversation:
        """Marks a conversation as inactive and stamps `ended_at`."""
        conv = await self.get_conversation(conversation_id)
        conv.is_active = False
        conv.ended_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(conv)
        return conv

    # Internal alias kept for any callers that referenced the old name.
    _end_conversation = end_conversation

    async def delete_conversation(self, conversation_id: UUID) -> None:
        await self.gateway.delete_conversation_cascade(self.db, conversation_id)

    async def get_pending_state(self, conversation_id: UUID) -> Optional[dict]:
        conv = await self.get_conversation(conversation_id)
        if not conv.pending_state:
            return None
        pause = conv.pending_state.get("pause_data") or {}
        return {
            "action_name": pause.get("action_name"),
            "params": pause.get("params", {}),
            "saved_at": conv.pending_state.get("saved_at"),
        }

    # ======================================================================
    # Messages
    # ======================================================================

    async def list_messages(
        self,
        conversation_id: Optional[UUID] = None,
        page: int = 1,
        limit: int = 50,
    ) -> Tuple[List[ChatMessage], int]:
        offset = (page - 1) * limit

        conditions = []
        if conversation_id:
            conditions.append(ChatMessage.chat_conversation_id == conversation_id)

        count_q = select(func.count(ChatMessage.id))
        if conditions:
            count_q = count_q.where(and_(*conditions))
        total = (await self.db.execute(count_q)).scalar() or 0

        q = (
            select(ChatMessage)
            .options(selectinload(ChatMessage.attachments))
            .order_by(ChatMessage.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        if conditions:
            q = q.where(and_(*conditions))

        result = await self.db.execute(q)
        return list(result.scalars().unique().all()), total

    async def get_message(self, message_id: UUID) -> ChatMessage:
        result = await self.db.execute(
            select(ChatMessage)
            .options(selectinload(ChatMessage.attachments))
            .where(ChatMessage.id == message_id)
        )
        msg = result.scalar_one_or_none()
        if not msg:
            raise MessageNotFoundException()
        return msg

    async def create_message(
        self,
        conversation_id: UUID,
        content: str,
        sender_type: SenderType = SenderType.CUSTOMER,
    ) -> ChatMessage:
        # Validate conversation exists
        await self.get_conversation(conversation_id)

        msg = ChatMessage(
            chat_conversation_id=conversation_id,
            sender_type=sender_type,
            message_text=content,
        )
        self.db.add(msg)
        await self.db.commit()
        await self.db.refresh(msg)
        return msg

    async def edit_message(
        self,
        conversation_id: UUID,
        message_id: UUID,
        new_text: str,
    ) -> None:
        await self.gateway.edit_message_cascade(self.db, conversation_id, message_id, new_text)

    async def delete_message(
        self,
        conversation_id: UUID,
        message_id: UUID,
    ) -> bool:
        return await self.gateway.delete_message_cascade(self.db, conversation_id, message_id)

    # ======================================================================
    # Attachments
    # ======================================================================

    def _upload_root(self) -> str:
        root = getattr(settings, "UPLOAD_DIR", None) or "./uploads/chat"
        os.makedirs(root, exist_ok=True)
        return root

    async def save_attachment(
        self,
        message_id: UUID,
        upload: UploadFile,
    ) -> ChatAttachment:
        if not upload.content_type or upload.content_type not in self.ALLOWED_CONTENT_TYPES:
            raise InvalidFileTypeException(upload.content_type or "<unknown>", self.ALLOWED_CONTENT_TYPES)

        content = await upload.read()
        if len(content) > self.MAX_FILE_SIZE_BYTES:
            raise FileTooLargeException(len(content), self.MAX_FILE_SIZE_BYTES)

        # Make sure the target message exists
        msg = await self.get_message(message_id)

        # Write to disk under uploads/<conversation_id>/<message_id>/<uuid>.<ext>
        ext = os.path.splitext(upload.filename or "")[1] or ""
        unique_name = f"{uuid.uuid4().hex}{ext}"
        target_dir = os.path.join(
            self._upload_root(),
            str(msg.chat_conversation_id),
            str(message_id),
        )
        os.makedirs(target_dir, exist_ok=True)
        storage_path = os.path.join(target_dir, unique_name)

        async with aiofiles.open(storage_path, "wb") as f:
            await f.write(content)

        att = ChatAttachment(
            chat_message_id=message_id,
            filename=upload.filename or unique_name,
            content_type=upload.content_type,
            size_bytes=len(content),
            storage_path=storage_path,
            storage_backend="local",
        )
        self.db.add(att)
        await self.db.commit()
        await self.db.refresh(att)
        return att

    async def list_attachments(self, message_id: UUID) -> List[ChatAttachment]:
        await self.get_message(message_id)  # 404 if missing
        result = await self.db.execute(
            select(ChatAttachment)
            .where(ChatAttachment.chat_message_id == message_id)
            .order_by(ChatAttachment.uploaded_at.asc())
        )
        return list(result.scalars().all())

    async def get_attachment(self, attachment_id: UUID) -> ChatAttachment:
        result = await self.db.execute(
            select(ChatAttachment).where(ChatAttachment.id == attachment_id)
        )
        att = result.scalar_one_or_none()
        if not att:
            raise AttachmentNotFoundException(attachment_id)
        return att

    # ======================================================================
    # Rating
    # ======================================================================

    async def rate_conversation(
        self,
        conversation_id: UUID,
        rating: int,
        feedback: Optional[str] = None,
        response_type: Optional[ResponseType] = None,
        external_customer_id: Optional[str] = None,
    ) -> AgentRating:
        if not 1 <= rating <= 5:
            raise InvalidRatingException(rating)
        conv = await self.get_conversation(conversation_id)  # 404 if missing

        existing = (await self.db.execute(
            select(AgentRating).where(AgentRating.chat_conversation_id == conversation_id)
        )).scalar_one_or_none()

        if existing:
            existing.rating = rating
            existing.feedback = feedback
            existing.response_type = response_type
            existing.external_customer_id = external_customer_id
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        r = AgentRating(
            chat_conversation_id=conv.id,
            rating=rating,
            feedback=feedback,
            response_type=response_type,
            external_customer_id=external_customer_id,
        )
        self.db.add(r)
        await self.db.commit()
        await self.db.refresh(r)
        return r

    async def get_rating(self, conversation_id: UUID) -> Optional[AgentRating]:
        result = await self.db.execute(
            select(AgentRating).where(AgentRating.chat_conversation_id == conversation_id)
        )
        return result.scalar_one_or_none()
