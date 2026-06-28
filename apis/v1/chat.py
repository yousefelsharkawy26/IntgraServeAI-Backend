# apis/v1/chat.py

import logging
import asyncio
from uuid import UUID
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status, Depends, HTTPException

from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal, get_db
from services.ai_gateway_service import AIGatewayService
from langchain_core.messages import HumanMessage, ToolMessage
from utils.exceptions import MessageNotFoundException, MessageNotEditableException

router = APIRouter()
logger = logging.getLogger(__name__)

@router.delete("/{conversation_id}")
async def delete_chat(conversation_id: UUID, db: AsyncSession = Depends(get_db)):
    gateway = AIGatewayService()
    await gateway.delete_conversation_cascade(db, conversation_id)
    return {"message": "Chat deleted"}

@router.delete("/{conversation_id}/messages/{message_id}")
async def delete_message(conversation_id: UUID, message_id: UUID, db: AsyncSession = Depends(get_db)):
    gateway = AIGatewayService()
    chat_deleted = await gateway.delete_message_cascade(db, conversation_id, message_id)
    return {"message": "Message deleted", "chat_deleted": chat_deleted}


@router.websocket("/ws")
async def chat_websocket(websocket: WebSocket):
    await websocket.accept()
    gateway = AIGatewayService()
    
    session_id, customer_email, customer_name, conversation_id = None, None, None, None
    active_generation_task = None
    cancel_token = asyncio.Event()

    try:
        # -------- Handshake --------
        init_msg = await websocket.receive_json()
        session_id = init_msg.get("session_id")
        customer_email = init_msg.get("customer_email")
        customer_name = init_msg.get("customer_name", "Customer")

        if not session_id or not customer_email:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        async with AsyncSessionLocal() as db:
            conversation = await gateway.get_or_create_conversation(db, session_id, customer_email, customer_name)
            conversation_id = conversation.id

        await websocket.send_json({"type": "connected", "conversation_id": str(conversation_id)})

        # --- BACKGROUND GENERATION WORKER ---
        async def run_ai_stream(messages_state):
            runner = gateway.create_runner(customer_email, customer_name)
            try:
                async for event in runner.stream_chat(messages_state, cancel_token=cancel_token):
                    await websocket.send_json(event)
                    
                    if event["type"] == "pause":
                        async with AsyncSessionLocal() as db:
                            await gateway.save_pending_state(db, conversation_id, messages_state, event)
                        break

                    elif event["type"] == "done":
                        ai_text = gateway.extract_ai_text(messages_state)
                        async with AsyncSessionLocal() as db:
                            await gateway.save_message(db, conversation_id, "AI", ai_text)
                            await gateway.clear_pending_state(db, conversation_id)
                            
            except Exception as e:
                logger.error(f"Stream task error: {e}")
                await websocket.send_json({"type": "error", "message": "Generation error."})

        # -------- Non-Blocking Chat Loop --------
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")

            if msg_type == "chat" or msg_type == "generate":
                # Cancel existing stream if user types while AI is generating
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
                # Edit triggers cascade delete + text update + auto generation resume
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

                if approved:
                    result = await gateway.execute_paused_action(p_data, customer_email, customer_name)
                    msgs.append(ToolMessage(content=result, tool_call_id=p_data.get("tool_call_id", "unknown")))
                else:
                    msgs.append(ToolMessage(content=f"User denied action.", tool_call_id=p_data.get("tool_call_id", "unknown")))

                async with AsyncSessionLocal() as db:
                    await gateway.clear_pending_state(db, conversation_id)

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
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}"
                })

    except WebSocketDisconnect:
        if active_generation_task and not active_generation_task.done():
            cancel_token.set()