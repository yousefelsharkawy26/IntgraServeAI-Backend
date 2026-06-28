# services/ai_gateway_service.py

import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from core.config import settings
from core.database import AsyncSessionLocal
from models.chat import ChatConversation, ChatMessage, SenderType
from models.ticket import TicketPriority, TicketType
from services.ticket_service import TicketService
from utils.schemas.ticket_schemas import ExternalTicketCreate
from utils.ai_config_adapter import AIConfigAdapter
from utils.exceptions import MessageNotEditableException, MessageNotFoundException

from ai_engine.action_engine import ActionEngine
from ai_engine.agent_runner import AgentRunner
from langchain_core.tools import ToolException
from langchain_core.messages import (
    HumanMessage, AIMessage, messages_from_dict, message_to_dict
)

logger = logging.getLogger(__name__)


class AIGatewayService:
    """Bridge between the FastAPI backend and the AI Engine."""

    _engine_cache: Optional[ActionEngine] = None

    @classmethod
    def get_engine(cls) -> ActionEngine:
        if cls._engine_cache is None:
            cls.reload_engine()
        return cls._engine_cache

    @classmethod
    def reload_engine(cls) -> None:
        agent_config_path = settings.AGENT_CONFIG_FILE_FULL_PATH
        actions_file_path = settings.ACTIONS_FILE_FULL_PATH

        actions_list = AIConfigAdapter.load_actions_for_engine(str(actions_file_path))
        
        logger.info("Reloading ActionEngine configuration into memory cache.")
        cls._engine_cache = ActionEngine(
            agent_config_path=str(agent_config_path),
            actions_list=actions_list
        )

    async def get_or_create_conversation(
        self,
        db: AsyncSession,
        session_id: str,
        customer_email: str,
        customer_name: str
    ) -> ChatConversation:
        result = await db.execute(
            select(ChatConversation).where(ChatConversation.session_id == session_id)
        )
        conv = result.scalar_one_or_none()

        if conv:
            if conv.customer_email != customer_email:
                conv.customer_email = customer_email
            if conv.customer_name != customer_name:
                conv.customer_name = customer_name
            if not conv.is_active:
                conv.is_active = True
            await db.commit()
            return conv

        conv = ChatConversation(
            session_id=session_id,
            customer_email=customer_email,
            customer_name=customer_name,
            is_active=True,
            started_at=datetime.now(timezone.utc)
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)
        return conv

    async def end_conversation(self, db: AsyncSession, conversation_id: UUID) -> None:
        result = await db.execute(
            select(ChatConversation).where(ChatConversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if conv:
            conv.is_active = False
            conv.ended_at = datetime.now(timezone.utc)
            await db.commit()

    async def delete_conversation_cascade(self, db: AsyncSession, conversation_id: UUID) -> None:
        """Hard deletes a conversation and all its associated messages and states."""
        await db.execute(delete(ChatMessage).where(ChatMessage.chat_conversation_id == conversation_id))
        await db.execute(delete(ChatConversation).where(ChatConversation.id == conversation_id))
        await db.commit()

    async def delete_message_cascade(self, db: AsyncSession, conversation_id: UUID, message_id: UUID) -> bool:
        """
        Deletes a message and all subsequent messages.
        Returns True if the entire chat was deleted (because it was the first message), False otherwise.
        """
        result = await db.execute(
            select(ChatMessage).where(ChatMessage.id == message_id, ChatMessage.chat_conversation_id == conversation_id)
        )
        target = result.scalar_one_or_none()
        if not target:
            raise MessageNotFoundException()
        if target.sender_type != SenderType.CUSTOMER:
            raise MessageNotEditableException("Only user messages can be deleted.")

        # Check if it is the very first message
        first_msg = await db.execute(
            select(ChatMessage).where(ChatMessage.chat_conversation_id == conversation_id).order_by(ChatMessage.created_at.asc()).limit(1)
        )
        first = first_msg.scalar_one_or_none()

        if first and first.id == target.id:
            await self.delete_conversation_cascade(db, conversation_id)
            return True

        # Cascade delete target and everything after it
        await db.execute(
            delete(ChatMessage)
            .where(ChatMessage.chat_conversation_id == conversation_id, ChatMessage.created_at >= target.created_at)
        )
        await db.commit()
        return False

    async def edit_message_cascade(self, db: AsyncSession, conversation_id: UUID, message_id: UUID, new_text: str) -> None:
        """Edits a message and deletes all subsequent messages to reset the context."""
        result = await db.execute(
            select(ChatMessage).where(ChatMessage.id == message_id, ChatMessage.chat_conversation_id == conversation_id)
        )
        target = result.scalar_one_or_none()
        if not target:
            raise MessageNotFoundException()
        if target.sender_type != SenderType.CUSTOMER:
            raise MessageNotEditableException("Only user messages can be edited.")

        # Delete everything strictly AFTER the edited message
        await db.execute(
            delete(ChatMessage)
            .where(ChatMessage.chat_conversation_id == conversation_id, ChatMessage.created_at > target.created_at)
        )
        target.message_text = new_text
        await db.commit()

    # ==================== Message Persistence ====================

    async def save_message(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        sender_type: str,
        text: str,
        intent_detected: Optional[str] = None,
        entities_extracted: Optional[dict] = None
    ) -> None:
        msg = ChatMessage(
            chat_conversation_id=conversation_id,
            sender_type=SenderType(sender_type),
            message_text=text,
            intent_detected=intent_detected,
            entities_extracted=entities_extracted
        )
        db.add(msg)
        await db.commit()

    async def load_message_history(
        self,
        db: AsyncSession,
        conversation_id: UUID
    ) -> List[Any]:
        """Load customer and AI messages only. System/tool messages are ephemeral."""
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.chat_conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.asc())
        )
        rows = result.scalars().all()

        messages = []
        for row in rows:
            if row.sender_type == SenderType.CUSTOMER:
                messages.append(HumanMessage(content=row.message_text))
            elif row.sender_type == SenderType.AI:
                messages.append(AIMessage(content=row.message_text))
        return messages

    def extract_ai_text(self, messages: List[Any]) -> str:
        """Extract the last AI message content."""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                if isinstance(msg.content, str):
                    return msg.content
                elif isinstance(msg.content, list):
                    return " ".join(str(c) for c in msg.content)
        return ""

    # ==================== Pause / Resume State ====================

    async def save_pending_state(
        self,
        db: AsyncSession,
        conversation_id: UUID,
        messages: List[Any],
        pause_data: Dict[str, Any]
    ) -> None:
        result = await db.execute(
            select(ChatConversation).where(ChatConversation.id == conversation_id)
        )
        conv = result.scalar_one()
        conv.pending_state = {
            "messages": [message_to_dict(m) for m in messages],
            "pause_data": pause_data,
            "saved_at": datetime.now(timezone.utc).isoformat()
        }
        await db.commit()

    async def load_pending_state(
        self,
        db: AsyncSession,
        conversation_id: UUID
    ) -> Optional[Dict[str, Any]]:
        result = await db.execute(
            select(ChatConversation).where(ChatConversation.id == conversation_id)
        )
        conv = result.scalar_one()
        if not conv.pending_state:
            return None

        state = conv.pending_state
        return {
            "messages": messages_from_dict(state["messages"]),
            "pause_data": state["pause_data"]
        }

    async def clear_pending_state(self, db: AsyncSession, conversation_id: UUID) -> None:
        result = await db.execute(
            select(ChatConversation).where(ChatConversation.id == conversation_id)
        )
        conv = result.scalar_one()
        conv.pending_state = None
        await db.commit()

    # ==================== Agent Runner Factory ====================

    def create_runner(
        self,
        customer_email: str,
        customer_name: str
    ) -> AgentRunner:
        engine = self.get_engine()

        async def internal_handler(action_name: str, params: dict) -> str:
            async with AsyncSessionLocal() as db:
                return await self.handle_internal_action(
                    action_name, params, db, customer_email, customer_name
                )

        return AgentRunner(engine, internal_handler=internal_handler)

    # ==================== Internal Action Bridge ====================

    async def handle_internal_action(
        self,
        action_name: str,
        params: dict,
        db: AsyncSession,
        customer_email: str,
        customer_name: str
    ) -> str:
        ticket_service = TicketService(db)

        # --- INTERNAL ACTION HANDLERS ---
        async def _create_support_ticket():
            ticket_data = ExternalTicketCreate(
                customer_email=customer_email,
                customer_name=customer_name,
                title=params.get("title", "Support Request from Chat"),
                description=params.get("description", "No description provided."),
                priority=TicketPriority.MEDIUM
            )
            ticket = await ticket_service.create_external_ticket(ticket_data)
            return f"Support ticket created successfully. Ticket ID: {ticket.id}"

        async def _create_technical_ticket():
            ticket_data = ExternalTicketCreate(
                customer_email=customer_email,
                customer_name=customer_name,
                title=params.get("title", "Technical Issue from Chat"),
                description=params.get("description", "No description provided."),
                priority=TicketPriority.HIGH
            )
            ticket = await ticket_service.create_external_ticket(ticket_data)
            return f"Technical ticket created successfully. Ticket ID: {ticket.id}"

        async def _check_ticket_status():
            tickets, total = await ticket_service.get_external_customer_tickets(
                customer_email=customer_email, page=1, limit=10
            )
            if not tickets:
                return "You don't have any active tickets at the moment."
            status_lines = [f"{t['title']}: {t['status']}" for t in tickets]
            return "Your tickets: " + "; ".join(status_lines)

        async def _search_tickets():
            tickets, total = await ticket_service.get_external_customer_tickets(
                customer_email=customer_email, page=1, limit=10
            )
            query = params.get("query", "").lower()
            matching = [t for t in tickets if query in t["title"].lower()]
            if not matching:
                return f"No tickets found matching '{params.get('query', '')}'."
            return "Matching tickets: " + "; ".join(
                [f"{t['title']} ({t['status']})" for t in matching]
            )

        async def _escalate_to_human():
            ticket_data = ExternalTicketCreate(
                customer_email=customer_email,
                customer_name=customer_name,
                title="Escalation from AI Agent",
                description=params.get("reason", "Customer requested human agent."),
                priority=TicketPriority.URGENT
            )
            ticket = await ticket_service.create_external_ticket(ticket_data)
            return (
                f"I've transferred you to a human agent. "
                f"Your escalation ticket ID is {ticket.id}. "
                f"An agent will contact you shortly."
            )

        async def _request_confirmation():
            return "Please confirm to proceed."

        # --- DISPATCHER ---
        handlers = {
            "create_support_ticket": _create_support_ticket,
            "create_technical_ticket": _create_technical_ticket,
            "check_ticket_status": _check_ticket_status,
            "search_tickets": _search_tickets,
            "escalate_to_human": _escalate_to_human,
            "request_confirmation": _request_confirmation
        }

        handler = handlers.get(action_name)
        if not handler:
            return f"Internal action '{action_name}' executed (No handler defined). Params: {params}"

        try:
            result = await handler()
            await db.commit()  # Ensure successful completion is saved
            return result
        except Exception as e:
            await db.rollback()  # Instantly rollback any partial DB inserts
            logger.error(f"Internal action '{action_name}' failed: {e}", exc_info=True)
            raise ToolException(f"Action '{action_name}' encountered a system error: {str(e)}")

    # ==================== Paused Action Execution ====================

    async def execute_paused_action(
        self,
        pause_data: Dict[str, Any],
        customer_email: str,
        customer_name: str
    ) -> str:
        action_name = pause_data["action_name"]
        params = pause_data["params"]

        engine = self.get_engine()
        act = next((a for a in engine.actions if a.name == action_name), None)

        if act and act.type == "internal":
            async with AsyncSessionLocal() as db:
                return await self.handle_internal_action(
                    action_name, params, db, customer_email, customer_name
                )
        else:
            return await engine.execute_action_directly(action_name, params)