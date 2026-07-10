# apis/v1/chat.py
#
# AUTHENTICATION APPLIED:
#   • All REST endpoints now require authentication (either JWT for staff or session for customers)
#   • WebSocket /ws remains session-based (unchanged)
#   • Access control enforced per-endpoint based on user type
#
# AUTH LEVELS:
#   - Admin: full CRUD on all conversations
#   - Agent (Support/Tech): read all, modify active conversations
#   - Customer: access only their own conversations via session_id + customer_email

import asyncio
import json
import logging
import os
from typing import List, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.orm import selectinload
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal, get_db
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from models.chat import ChatConversation, ChatMessage, ResponseType
from services.ai_gateway_service import AIGatewayService
from services.chat_service import ChatService
from utils.schemas.chat_schemas import (
    AttachmentOut,
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationUpdate,
    MessageCreate,
    MessageEdit,
    MessageOut,
    Page,
    PageMeta,
    PendingStateOut,
    RatingCreate,
    RatingOut,
    UploadResponse,
)
from utils.dependencies import (
    require_admin,
    get_current_active_user,
    get_chat_access,
    ChatAccess,
    CustomerSession,
    verify_customer_session,
    verify_customer_session_for_conversation,
)
from utils.token_helper import TokenHelper
from models.user import User
from utils.exceptions import UnauthorizedException, NotFoundException, BadRequestException

router = APIRouter()
logger = logging.getLogger(__name__)


# ===========================================================================
# Helpers
# ===========================================================================

def _conv_to_out(conv: ChatConversation, message_count: int = 0) -> ConversationOut:
    return ConversationOut(
        id=conv.id,
        session_id=conv.session_id,
        customer_email=conv.customer_email,
        customer_name=conv.customer_name,
        title=(conv.ai_context or {}).get("title") if isinstance(conv.ai_context, dict) else None,
        external_customer_id=conv.external_customer_id,
        is_active=conv.is_active,
        started_at=conv.started_at,
        ended_at=conv.ended_at,
        has_pending_state=bool(conv.pending_state),
        message_count=message_count,
    )


async def _count_messages(db: AsyncSession, conversation_id: UUID) -> int:
    res = await db.execute(
        select(func.count(ChatMessage.id)).where(ChatMessage.chat_conversation_id == conversation_id)
    )
    return res.scalar() or 0


async def _get_conversation_or_404(db: AsyncSession, conversation_id: UUID) -> ChatConversation:
    """Helper to fetch conversation with 404 handling."""
    service = ChatService(db)
    try:
        return await service.get_conversation(conversation_id)
    except Exception:
        raise NotFoundException("Conversation not found")


def _enforce_access(access: ChatAccess, conv: ChatConversation, require_modify: bool = False, require_delete: bool = False):
    """Enforce access control on a conversation."""
    if require_delete:
        if not access.can_delete_conversation():
            raise UnauthorizedException("Admin access required to delete conversations")
        return

    if require_modify:
        if not access.can_modify_conversation(conv):
            raise UnauthorizedException("You do not have permission to modify this conversation")
        return

    if not access.can_access_conversation(conv):
        raise UnauthorizedException("You do not have access to this conversation")


# ===========================================================================
# WebSocket  (unchanged - session-based auth)
# ===========================================================================

async def _verify_ws_staff_user(token: str) -> Optional[User]:
    """Verify a JWT token for WebSocket staff authentication."""
    try:
        payload = TokenHelper.verify_token(token, token_type="access")
        user_id = payload.get("user_id")
        if not user_id:
            return None
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User)
                .options(selectinload(User.roles))
                .where(User.id == UUID(user_id))
            )
            user = result.scalar_one_or_none()
            if user and user.is_active:
                return user
    except Exception:
        pass
    return None


@router.websocket("/ws")
async def chat_websocket(websocket: WebSocket):
    """WebSocket endpoint - supports JWT (staff) or session-based (customer) auth."""
    gateway = AIGatewayService()

    # -------- Pre-accept JWT verification from query params --------
    staff_user: Optional[User] = None
    query_token = websocket.query_params.get("token")
    if query_token:
        staff_user = await _verify_ws_staff_user(query_token)
        if not staff_user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await websocket.accept()

    session_id = customer_email = customer_name = conversation_id = None
    active_generation_task = None
    cancel_token = asyncio.Event()

    try:
        # -------- Handshake --------
        init_msg = await websocket.receive_json()
        session_id = init_msg.get("session_id")
        customer_email = init_msg.get("customer_email")
        customer_name = init_msg.get("customer_name", "Customer")
        handshake_token = init_msg.get("token")

        # If not already authenticated via query params, check handshake token
        if not staff_user and handshake_token:
            staff_user = await _verify_ws_staff_user(handshake_token)
            if not staff_user:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

        # Customers must provide session_id + customer_email
        if not staff_user and (not session_id or not customer_email):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        async with AsyncSessionLocal() as db:
            conversation = await gateway.get_or_create_conversation(
                db,
                session_id,
                customer_email,
                customer_name,
                allow_existing_identity_mismatch=bool(staff_user),
            )
            conversation_id = conversation.id

        await websocket.send_json({"type": "connected", "conversation_id": str(conversation_id)})

        # --- STATE RESTORATION ---
        # If there's a pending state (e.g., from a previous disconnect or page refresh),
        # send it to the frontend so it can restore the approval card or tool UI.
        async with AsyncSessionLocal() as db:
            pending = await gateway.load_pending_state(db, conversation_id)

        if pending:
            p_data = pending["pause_data"]
            # Determine what phase the pending state is in:
            # - If it has tool_input_required info → restore tool UI
            # - Otherwise → restore approval card
            # We check if the pending state was saved after a confirm(approved)
            # by looking for a "_confirmed" flag we set in the confirm handler.
            if p_data.get("_awaiting_tool_result"):
                await websocket.send_json({
                    "type": "restore_tool_input",
                    "action_name": p_data.get("action_name"),
                    "tool_call_id": p_data.get("tool_call_id", "unknown"),
                    "params": p_data.get("params", {}),
                })
            else:
                await websocket.send_json({
                    "type": "restore_approval",
                    "action_name": p_data.get("action_name"),
                    "tool_call_id": p_data.get("tool_call_id", "unknown"),
                    "params": p_data.get("params", {}),
                })
            logger.info(f"Restored pending state for conversation {conversation_id}")

        # --- BACKGROUND GENERATION WORKER ---
        async def run_ai_stream(messages_state):
            runner = gateway.create_runner(customer_email, customer_name)
            ai_text_chunks: list[str] = []
            try:
                async for event in runner.stream_chat(messages_state, cancel_token=cancel_token):
                    ws_event = {k: v for k, v in event.items() if k != "_resume_state"}
                    await websocket.send_json(ws_event)

                    if event["type"] == "token":
                        ai_text_chunks.append(str(event.get("content", "")))
                    elif event["type"] == "pause":
                        async with AsyncSessionLocal() as db:
                            await gateway.save_pending_state(db, conversation_id, messages_state, event)
                        break
                    elif event["type"] == "done":
                        ai_text = "".join(ai_text_chunks).strip() or gateway.extract_ai_text(messages_state)
                        async with AsyncSessionLocal() as db:
                            if ai_text:
                                await gateway.save_message(db, conversation_id, "AI", ai_text)
                            await gateway.clear_pending_state(db, conversation_id)
            except Exception as e:
                logger.error(f"Stream task error: {e}", exc_info=True)
                await websocket.send_json({"type": "error", "message": "Generation error."})

        # -------- Non-Blocking Chat Loop --------
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")

            if msg_type == "chat" or msg_type == "generate":
                if active_generation_task and not active_generation_task.done():
                    cancel_token.set()
                cancel_token.clear()

                user_content = msg.get("content", "").strip()
                async with AsyncSessionLocal() as db:
                    if user_content:
                        await gateway.save_message(db, conversation_id, "CUSTOMER", user_content)
                    messages = await gateway.load_message_history(db, conversation_id)

                active_generation_task = asyncio.create_task(run_ai_stream(messages))

            elif msg_type == "stop":
                if active_generation_task and not active_generation_task.done():
                    cancel_token.set()
                await websocket.send_json({"type": "stopped"})

            elif msg_type == "edit":
                if active_generation_task and not active_generation_task.done():
                    cancel_token.set()
                cancel_token.clear()

                msg_id = msg.get("message_id")
                new_content = msg.get("content")

                async with AsyncSessionLocal() as db:
                    await gateway.edit_message_cascade(db, conversation_id, UUID(msg_id), new_content)
                    messages = await gateway.load_message_history(db, conversation_id)

                await websocket.send_json({"type": "edit_successful"})
                active_generation_task = asyncio.create_task(run_ai_stream(messages))

            elif msg_type == "confirm":
                async with AsyncSessionLocal() as db:
                    state = await gateway.load_pending_state(db, conversation_id)

                if not state:
                    await websocket.send_json({"type": "error", "message": "No pending action"})
                    continue

                cancel_token.clear()
                msgs, p_data, approved = state["messages"], state["pause_data"], msg.get("approved", False)

                resume_state = p_data.get("_resume_state", {})
                if resume_state:
                    ast_msg = resume_state.get("assistant_message", {})
                    if isinstance(ast_msg, dict):
                        msgs.append(AIMessage(
                            content=ast_msg.get("content", ""),
                            tool_calls=ast_msg.get("tool_calls", []),
                        ))
                    for tr in resume_state.get("completed_tool_results", []):
                        msgs.append(ToolMessage(content=tr["content"], tool_call_id=tr["tool_call_id"]))

                tool_call_id = p_data.get("tool_call_id", "unknown")

                if approved:
                    # Check if this action requires human input after approval
                    # (metadata-driven, not hardcoded)
                    engine = gateway.get_engine()
                    act = next((a for a in engine.actions if a.name == p_data.get("action_name")), None)
                    
                    if act and act.requires_human_input:
                        # Mark pending state as awaiting tool_result (for restore on reconnect)
                        p_data["_awaiting_tool_result"] = True
                        async with AsyncSessionLocal() as db:
                            await gateway.save_pending_state(db, conversation_id, msgs, p_data)

                        await websocket.send_json({
                            "type": "tool_input_required",
                            "action_name": p_data.get("action_name"),
                            "tool_call_id": tool_call_id,
                            "params": p_data.get("params", {}),
                        })
                        continue

                    # Non-interactive tools: execute immediately
                    try:
                        result = await gateway.execute_paused_action(p_data, customer_email, customer_name)
                        msgs.append(ToolMessage(content=result, tool_call_id=tool_call_id))
                    except Exception as e:
                        msgs.append(ToolMessage(content=f"Action failed: {str(e)}", tool_call_id=tool_call_id))
                else:
                    msgs.append(ToolMessage(
                        content="Action aborted by user. Do not call this tool again. Please acknowledge the user's decision.",
                        tool_call_id=tool_call_id,
                    ))

                async with AsyncSessionLocal() as db:
                    await gateway.clear_pending_state(db, conversation_id)

                active_generation_task = asyncio.create_task(run_ai_stream(msgs))

            # =============================================================
            # GENERIC tool_result handler
            # =============================================================
            # The frontend sends this after the user interacts with a tool UI
            # (fills a form, picks a product, selects a date, etc.).
            #
            # Payload:
            #   { "type": "tool_result", "tool_call_id": "...", "result": { ... } }
            #
            # The result is passed back into the LLM as a ToolMessage so the
            # agent can continue reasoning with the human's input.
            # =============================================================
            elif msg_type == "tool_result":
                async with AsyncSessionLocal() as db:
                    state = await gateway.load_pending_state(db, conversation_id)

                if not state:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No pending action for tool_result",
                    })
                    continue

                cancel_token.clear()
                msgs = state["messages"]
                p_data = state["pause_data"]

                # Reconstruct conversation history from resume state
                resume_state = p_data.get("_resume_state", {})
                if resume_state:
                    ast_msg = resume_state.get("assistant_message", {})
                    if isinstance(ast_msg, dict):
                        msgs.append(AIMessage(
                            content=ast_msg.get("content", ""),
                            tool_calls=ast_msg.get("tool_calls", []),
                        ))
                    for tr in resume_state.get("completed_tool_results", []):
                        msgs.append(ToolMessage(
                            content=tr["content"],
                            tool_call_id=tr["tool_call_id"],
                        ))

                tool_call_id = msg.get("tool_call_id") or p_data.get("tool_call_id", "unknown")
                result_data = msg.get("result", {})

                # Check if the result indicates cancellation or failure.
                # If so, do NOT execute the action — just inform the LLM.
                is_cancelled = (
                    isinstance(result_data, dict)
                    and result_data.get("cancelled") is True
                )
                is_failed = (
                    isinstance(result_data, dict)
                    and "error" in result_data
                    and not result_data.get("cancelled")
                )

                if is_cancelled:
                    msgs.append(ToolMessage(
                        content="Action cancelled by user. Do not call this tool again. Please acknowledge the user's decision.",
                        tool_call_id=tool_call_id,
                    ))
                elif is_failed:
                    error_msg = result_data.get("error", "Unknown error")
                    msgs.append(ToolMessage(
                        content=f"Tool execution failed on the client side: {error_msg}",
                        tool_call_id=tool_call_id,
                    ))
                else:
                    # Merge user's input into the original params and execute the action.
                    if isinstance(result_data, dict):
                        p_data["params"] = {**p_data.get("params", {}), **result_data}

                    try:
                        execution_result = await gateway.execute_paused_action(
                            p_data, customer_email, customer_name
                        )
                        msgs.append(ToolMessage(content=execution_result, tool_call_id=tool_call_id))
                    except Exception as e:
                        logger.error(f"Tool execution failed after tool_result: {e}")
                        msgs.append(ToolMessage(
                            content=f"Action failed: {str(e)}",
                            tool_call_id=tool_call_id,
                        ))

                # Clear pending state — execution resumes
                async with AsyncSessionLocal() as db:
                    await gateway.clear_pending_state(db, conversation_id)

                # Resume the AI stream — the LLM will see the result and continue
                active_generation_task = asyncio.create_task(run_ai_stream(msgs))

            elif msg_type == "end":
                if active_generation_task and not active_generation_task.done():
                    cancel_token.set()
                async with AsyncSessionLocal() as db:
                    await gateway.end_conversation(db, conversation_id)
                await websocket.send_json({"type": "ended"})
                await websocket.close()
                break

            else:
                await websocket.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})

    except WebSocketDisconnect:
        if active_generation_task and not active_generation_task.done():
            cancel_token.set()


# ===========================================================================
# Conversations  (/conversations, /conversations/{id})
# ===========================================================================

@router.get("/conversations", response_model=Page[ConversationOut])
async def list_conversations(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    customer_email: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    search: Optional[str] = Query(None, description="Matches name/email/session_id"),
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    List conversations.

    **Auth:** Staff (JWT) see all conversations. Customers (session) see only their own.
    """
    service = ChatService(db)

    # Customers can only filter by their own email
    if access.customer_session and not access.is_staff:
        customer_email = access.customer_session.customer_email

    items, total = await service.list_conversations(
        page=page, limit=limit,
        customer_email=customer_email, is_active=is_active, search=search,
    )

    # Filter results for customers
    if access.customer_session and not access.is_staff:
        items = [
            conv for conv in items
            if conv.customer_email == access.customer_session.customer_email
        ]
        total = len(items)

    return Page[ConversationOut](
        items=[_conv_to_out(c) for c in items],
        meta=PageMeta(
            page=page, limit=limit, total=total,
            has_more=(page * limit) < total,
        ),
    )


@router.post("/conversations", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    Create a new conversation.

    **Auth:** Staff can create for any customer. Customers can only create for themselves.
    """
    # Customers can only create conversations for themselves
    if access.customer_session and not access.is_staff:
        if payload.customer_email != access.customer_session.customer_email:
            raise UnauthorizedException("You can only create conversations for your own email")

    service = ChatService(db)
    try:
        conv = await service.create_conversation(
            session_id=payload.session_id,
            customer_email=payload.customer_email,
            customer_name=payload.customer_name,
            external_customer_id=payload.external_customer_id,
            metadata=payload.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return ConversationDetail(**_conv_to_out(conv, message_count=0).model_dump(), messages=[], rating=None)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID,
    messages_page: int = Query(1, ge=1),
    messages_limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    Get conversation details with paginated messages and rating.

    **Auth:** Staff can view any. Customers can only view their own.
    """
    service = ChatService(db)
    conv = await _get_conversation_or_404(db, conversation_id)

    # Enforce access control
    _enforce_access(access, conv)

    count = await _count_messages(db, conversation_id)
    msg_items, msg_total = await service.list_messages(
        conversation_id=conversation_id, page=messages_page, limit=messages_limit
    )
    return ConversationDetail(
        **_conv_to_out(conv, message_count=count).model_dump(),
        messages=[MessageOut.model_validate(m) for m in msg_items],
        messages_meta=PageMeta(
            page=messages_page,
            limit=messages_limit,
            total=msg_total,
            has_more=(messages_page * messages_limit) < msg_total,
        ),
        rating=RatingOut.model_validate(conv.rating) if conv.rating else None,
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    Update conversation (name, active status).

    **Auth:** Staff can update any. Customers can only update their own active conversations.
    """
    service = ChatService(db)
    conv = await service.get_conversation(conversation_id)

    _enforce_access(access, conv, require_modify=True)

    conv = await service.update_conversation(
        conversation_id,
        customer_name=payload.customer_name,
        is_active=payload.is_active,
    )
    return _conv_to_out(conv, message_count=await _count_messages(db, conversation_id))


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    Delete a conversation and all its messages.

    **Auth:** Admin only.
    """
    service = ChatService(db)
    conv = await service.get_conversation(conversation_id)

    _enforce_access(access, conv, require_delete=True)

    await service.delete_conversation(conversation_id)
    return {"message": "Chat deleted", "conversation_id": str(conversation_id)}


@router.post("/conversations/{conversation_id}/end", response_model=ConversationOut)
async def end_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    End an active conversation.

    **Auth:** Staff can end any. Customers can only end their own.
    """
    service = ChatService(db)
    conv = await service.get_conversation(conversation_id)

    _enforce_access(access, conv, require_modify=True)

    conv = await service.end_conversation(conversation_id)
    return _conv_to_out(conv, message_count=await _count_messages(db, conversation_id))


@router.get("/conversations/{conversation_id}/messages", response_model=Page[MessageOut])
async def list_conversation_messages(
    conversation_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    List messages in a conversation.

    **Auth:** Staff can view any. Customers can only view their own.
    """
    service = ChatService(db)
    conv = await service.get_conversation(conversation_id)  # 404 guard

    _enforce_access(access, conv)

    items, total = await service.list_messages(conversation_id=conversation_id, page=page, limit=limit)
    return Page[MessageOut](
        items=[MessageOut.model_validate(m) for m in items],
        meta=PageMeta(page=page, limit=limit, total=total, has_more=(page * limit) < total),
    )


@router.get("/conversations/{conversation_id}/state", response_model=Optional[PendingStateOut])
async def get_conversation_state(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    Get AI pending state for a conversation.

    **Auth:** Staff only (internal AI state).
    """
    if not access.is_staff:
        raise UnauthorizedException("Staff access required")

    service = ChatService(db)
    conv = await service.get_conversation(conversation_id)
    _enforce_access(access, conv)

    return await service.get_pending_state(conversation_id)


@router.post("/conversations/{conversation_id}/rate", response_model=RatingOut, status_code=status.HTTP_201_CREATED)
async def rate_conversation(
    conversation_id: UUID,
    payload: RatingCreate,
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    Rate a conversation.

    **Auth:** Customers can only rate their own conversations. Staff cannot rate.
    """
    service = ChatService(db)
    conv = await service.get_conversation(conversation_id)

    # Only customers can rate, and only their own conversations
    if access.is_staff:
        raise UnauthorizedException("Only customers can rate conversations")

    if access.customer_session:
        if conv.customer_email != access.customer_session.customer_email:
            raise UnauthorizedException("You can only rate your own conversations")

    r = await service.rate_conversation(
        conversation_id,
        rating=payload.rating,
        feedback=payload.feedback,
        response_type=payload.response_type,
        external_customer_id=payload.external_customer_id,
    )
    return RatingOut.model_validate(r)


@router.get("/conversations/{conversation_id}/rating", response_model=Optional[RatingOut])
async def get_conversation_rating(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    Get rating for a conversation.

    **Auth:** Staff can view any. Customers can only view their own.
    """
    service = ChatService(db)
    conv = await service.get_conversation(conversation_id)

    _enforce_access(access, conv)

    r = await service.get_rating(conversation_id)
    return RatingOut.model_validate(r) if r else None


# ===========================================================================
# Messages  (/messages, /messages/{id})
# ===========================================================================

@router.get("/messages", response_model=Page[MessageOut])
async def list_messages(
    conversation_id: Optional[UUID] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    List messages (global or filtered by conversation).

    **Auth:** Staff can view all. Customers can only view messages from their own conversations.
    """
    service = ChatService(db)

    # If customer, enforce they can only see their own conversation's messages
    if access.customer_session and not access.is_staff and conversation_id:
        conv = await service.get_conversation(conversation_id)
        _enforce_access(access, conv)
    elif access.customer_session and not access.is_staff and not conversation_id:
        raise UnauthorizedException("Customers must specify a conversation_id")

    items, total = await service.list_messages(
        conversation_id=conversation_id, page=page, limit=limit,
    )

    # Additional filter for customers
    if access.customer_session and not access.is_staff:
        # Verify all messages belong to customer's conversations
        valid_conv_ids = set()
        for msg in items:
            if msg.chat_conversation_id not in valid_conv_ids:
                conv = await service.get_conversation(msg.chat_conversation_id)
                if access.can_access_conversation(conv):
                    valid_conv_ids.add(msg.chat_conversation_id)
        items = [m for m in items if m.chat_conversation_id in valid_conv_ids]
        total = len(items)

    return Page[MessageOut](
        items=[MessageOut.model_validate(m) for m in items],
        meta=PageMeta(page=page, limit=limit, total=total, has_more=(page * limit) < total),
    )


@router.post("/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def create_message(
    payload: MessageCreate,
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    Create a new message in a conversation.

    **Auth:** Staff can message any conversation. Customers can only message their own.
    """
    service = ChatService(db)
    conv = await service.get_conversation(payload.conversation_id)

    _enforce_access(access, conv, require_modify=True)

    msg = await service.create_message(
        conversation_id=payload.conversation_id,
        content=payload.content,
        sender_type=payload.sender_type,
    )
    return MessageOut.model_validate(msg)


@router.get("/messages/{message_id}", response_model=MessageOut)
async def get_message(
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    Get a single message.

    **Auth:** Staff can view any. Customers can only view their own.
    """
    service = ChatService(db)
    msg = await service.get_message(message_id)

    conv = await service.get_conversation(msg.chat_conversation_id)
    _enforce_access(access, conv)

    return MessageOut.model_validate(msg)


@router.patch("/messages/{message_id}", response_model=MessageOut)
async def edit_message(
    message_id: UUID,
    payload: MessageEdit,
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    Edit a message (cascade deletes subsequent messages).

    **Auth:** Staff can edit any. Customers can only edit their own messages in active conversations.
    """
    service = ChatService(db)
    msg = await service.get_message(message_id)

    conv = await service.get_conversation(msg.chat_conversation_id)
    _enforce_access(access, conv, require_modify=True)

    # Customers can only edit their own (CUSTOMER) messages
    if access.customer_session and not access.is_staff:
        from models.ticket import SenderType
        if msg.sender_type != SenderType.CUSTOMER:
            raise UnauthorizedException("You can only edit your own messages")

    await service.edit_message(msg.chat_conversation_id, message_id, payload.content)
    refreshed = await service.get_message(message_id)
    return MessageOut.model_validate(refreshed)


@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    Delete a message (cascade deletes subsequent messages).

    **Auth:** Admin can delete any. Customers can only delete their own messages.
    """
    service = ChatService(db)
    msg = await service.get_message(message_id)

    conv = await service.get_conversation(msg.chat_conversation_id)

    # Admin can delete any; customers can delete their own
    if access.is_admin:
        pass  # Allow
    elif access.customer_session and not access.is_staff:
        if conv.customer_email != access.customer_session.customer_email:
            raise UnauthorizedException("You can only delete messages from your own conversations")
        from models.ticket import SenderType
        if msg.sender_type != SenderType.CUSTOMER:
            raise UnauthorizedException("You can only delete your own messages")
    else:
        _enforce_access(access, conv, require_modify=True)

    chat_deleted = await service.delete_message(msg.chat_conversation_id, message_id)
    return {"message": "Message deleted", "message_id": str(message_id), "chat_deleted": chat_deleted}


# ===========================================================================
# Attachments  (/upload, /messages/{id}/attachments, /attachments/{id})
# ===========================================================================

@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    message_id: UUID = Form(..., description="ID of the message this file belongs to"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    Upload a file attachment to a message.

    **Auth:** Staff can upload to any message. Customers can only upload to their own messages.
    """
    service = ChatService(db)
    msg = await service.get_message(message_id)

    conv = await service.get_conversation(msg.chat_conversation_id)
    _enforce_access(access, conv, require_modify=True)

    att = await service.save_attachment(message_id, file)
    return UploadResponse(
        attachment=AttachmentOut.model_validate(att),
        download_url=f"/chat/attachments/{att.id}/download",
    )


@router.get("/messages/{message_id}/attachments", response_model=List[AttachmentOut])
async def list_message_attachments(
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    List attachments for a message.

    **Auth:** Staff can view any. Customers can only view their own.
    """
    service = ChatService(db)
    msg = await service.get_message(message_id)

    conv = await service.get_conversation(msg.chat_conversation_id)
    _enforce_access(access, conv)

    items = await service.list_attachments(message_id)
    return [AttachmentOut.model_validate(a) for a in items]


@router.get("/attachments/{attachment_id}", response_model=AttachmentOut)
async def get_attachment(
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    Get attachment metadata.

    **Auth:** Staff can view any. Customers can only view their own.
    """
    service = ChatService(db)
    att = await service.get_attachment(attachment_id)

    msg = await service.get_message(att.chat_message_id)
    conv = await service.get_conversation(msg.chat_conversation_id)
    _enforce_access(access, conv)

    return AttachmentOut.model_validate(att)


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    access: ChatAccess = Depends(get_chat_access),
):
    """
    Download an attachment file.

    **Auth:** Staff can download any. Customers can only download their own.
    """
    service = ChatService(db)
    att = await service.get_attachment(attachment_id)

    msg = await service.get_message(att.chat_message_id)
    conv = await service.get_conversation(msg.chat_conversation_id)
    _enforce_access(access, conv)

    if att.storage_backend != "local" or not os.path.exists(att.storage_path):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="File no longer available")
    return FileResponse(
        path=att.storage_path,
        media_type=att.content_type,
        filename=att.filename,
    )
