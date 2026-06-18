# apis/v1/chat.py

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal
from services.ai_gateway_service import AIGatewayService
from langchain_core.messages import HumanMessage

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws")
async def chat_websocket(websocket: WebSocket):
    await websocket.accept()
    gateway = AIGatewayService()
    session_id = None

    try:
        # -------- Handshake --------
        init_msg = await websocket.receive_json()
        session_id = init_msg.get("session_id")
        customer_email = init_msg.get("customer_email")
        customer_name = init_msg.get("customer_name", "Customer")

        if not session_id or not customer_email:
            await websocket.send_json({
                "type": "error",
                "message": "session_id and customer_email are required"
            })
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        async with AsyncSessionLocal() as db:
            conversation = await gateway.get_or_create_conversation(
                db, session_id, customer_email, customer_name
            )
            messages = await gateway.load_message_history(db, conversation.id)

        await websocket.send_json({
            "type": "connected",
            "conversation_id": str(conversation.id),
            "session_id": session_id
        })

        # -------- Chat Loop --------
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")

            if msg_type == "chat":
                user_content = msg.get("content", "").strip()
                if not user_content:
                    await websocket.send_json({
                        "type": "error",
                        "message": "content is required"
                    })
                    continue

                messages.append(HumanMessage(content=user_content))

                async with AsyncSessionLocal() as db:
                    await gateway.save_message(
                        db, conversation.id, "CUSTOMER", user_content
                    )

                async with AsyncSessionLocal() as db:
                    runner = gateway.create_runner(db, customer_email, customer_name)

                paused = False
                pause_data = None

                try:
                    async for event in runner.stream_chat(messages):
                        await websocket.send_json(event)

                        if event["type"] == "pause":
                            paused = True
                            pause_data = event
                            async with AsyncSessionLocal() as db:
                                await gateway.save_pending_state(
                                    db, conversation.id, messages, pause_data
                                )
                            break
                        elif event["type"] == "done":
                            ai_text = gateway.extract_ai_text(messages)
                            async with AsyncSessionLocal() as db:
                                await gateway.save_message(
                                    db, conversation.id, "AI", ai_text
                                )
                                await gateway.clear_pending_state(db, conversation.id)
                except Exception as e:
                    logger.error(f"Stream error: {e}", exc_info=True)
                    await websocket.send_json({
                        "type": "error",
                        "message": "An error occurred while processing your message"
                    })

            elif msg_type == "confirm":
                async with AsyncSessionLocal() as db:
                    state = await gateway.load_pending_state(db, conversation.id)

                if not state:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No pending action to confirm"
                    })
                    continue

                messages = state["messages"]
                pause_data = state["pause_data"]
                approved = msg.get("approved", False)

                if approved:
                    async with AsyncSessionLocal() as db:
                        result = await gateway.execute_paused_action(
                            pause_data, db, customer_email, customer_name
                        )
                    messages.append(ToolMessage(
                        content=result,
                        tool_call_id=pause_data.get("tool_call_id", "unknown")
                    ))
                else:
                    denial = (
                        f"User denied action: {pause_data.get('action_name', 'unknown')}."
                    )
                    messages.append(ToolMessage(
                        content=denial,
                        tool_call_id=pause_data.get("tool_call_id", "unknown")
                    ))

                async with AsyncSessionLocal() as db:
                    await gateway.clear_pending_state(db, conversation.id)

                async with AsyncSessionLocal() as db:
                    runner = gateway.create_runner(db, customer_email, customer_name)

                try:
                    async for event in runner.stream_chat(messages):
                        await websocket.send_json(event)
                        if event["type"] == "done":
                            ai_text = gateway.extract_ai_text(messages)
                            async with AsyncSessionLocal() as db:
                                await gateway.save_message(
                                    db, conversation.id, "AI", ai_text
                                )
                except Exception as e:
                    logger.error(f"Resume stream error: {e}", exc_info=True)
                    await websocket.send_json({
                        "type": "error",
                        "message": "An error occurred while resuming"
                    })

            elif msg_type == "end":
                async with AsyncSessionLocal() as db:
                    await gateway.end_conversation(db, conversation.id)
                await websocket.send_json({"type": "ended"})
                await websocket.close()
                break

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}"
                })

    except WebSocketDisconnect:
        logger.info(
            f"Client disconnected: session={session_id or 'unknown'}"
        )
    except Exception as e:
        logger.error(f"WebSocket fatal error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": "Internal server error"
            })
            await websocket.close()
        except Exception:
            pass