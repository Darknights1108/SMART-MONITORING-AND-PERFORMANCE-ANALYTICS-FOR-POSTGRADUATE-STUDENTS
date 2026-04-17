"""
Chat API - WebSocket endpoint for real-time agent interaction.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime
from sqlalchemy import text
from app.database import SyncSessionLocal
from app.services.agent_service import get_agent
from app.services.auth_service import decode_token
from app.tools.sanitizer import sanitize_user_input
from app.tools.email_tools import has_pending_sends, execute_pending_sends, clear_pending_sends
import uuid
import json
import traceback

_CONFIRM_WORDS = {"y", "yes", "ok", "okay", "confirm", "确认", "发送", "send", "是", "好"}
_CANCEL_WORDS  = {"n", "no", "cancel", "取消", "不", "算了", "discard"}

router = APIRouter(tags=["chat"])


@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket):
    await websocket.accept()

    # Authenticate via first message
    try:
        auth_msg = await websocket.receive_text()
        auth_data = json.loads(auth_msg)
        token = auth_data.get("token")
        if not token:
            await websocket.send_json({"type": "error", "message": "Token required"})
            await websocket.close()
            return

        user = decode_token(token)
        supervisor_id = int(user["sub"])
        session_id = str(uuid.uuid4())

        await websocket.send_json({
            "type": "auth_success",
            "session_id": session_id,
            "user": {
                "staff_id": user["staff_id"],
                "role": user["role"],
            }
        })
    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        await websocket.close()
        return

    agent = get_agent()
    db = SyncSessionLocal()

    try:
        while True:
            data = await websocket.receive_text()
            msg_data = json.loads(data)
            user_message = msg_data.get("message", "")

            if not user_message.strip():
                continue

            # Hard input sanitization (obfuscation / injection check)
            blocked, reason = sanitize_user_input(user_message)
            if blocked:
                await websocket.send_json({
                    "type": "error",
                    "message": reason,
                    "timestamp": datetime.now().isoformat(),
                })
                continue

            # Email confirmation intercept — handle before agent
            word = user_message.strip().lower()
            if has_pending_sends():
                if word in _CONFIRM_WORDS:
                    result = execute_pending_sends()
                    await websocket.send_json({
                        "type": "message",
                        "message": result,
                        "timestamp": datetime.now().isoformat(),
                    })
                    continue
                elif word in _CANCEL_WORDS:
                    clear_pending_sends()
                    await websocket.send_json({
                        "type": "message",
                        "message": "Email cancelled. No emails were sent.",
                        "timestamp": datetime.now().isoformat(),
                    })
                    continue

            # Save user message
            db.execute(text("""
                INSERT INTO chat_history (supervisor_id, session_id, message, role)
                VALUES (:sid, :sess, :msg, 'user')
            """), {"sid": supervisor_id, "sess": session_id, "msg": user_message})
            db.commit()

            # Send "thinking" indicator
            await websocket.send_json({"type": "thinking"})

            try:
                # Run agent
                response = agent.run(user_message)
                response_str = str(response)

                # Check if response contains chart data (JSON)
                msg_type = "message"
                try:
                    parsed = json.loads(response_str)
                    if isinstance(parsed, dict) and "type" in parsed:
                        msg_type = "chart"
                except (json.JSONDecodeError, TypeError):
                    pass

                # Save assistant response
                db.execute(text("""
                    INSERT INTO chat_history (supervisor_id, session_id, message, role)
                    VALUES (:sid, :sess, :msg, 'assistant')
                """), {"sid": supervisor_id, "sess": session_id, "msg": response_str})
                db.commit()

                await websocket.send_json({
                    "type": msg_type,
                    "message": response_str,
                    "timestamp": datetime.now().isoformat(),
                })

            except Exception as e:
                error_msg = f"Agent error: {str(e)}"
                traceback.print_exc()
                await websocket.send_json({
                    "type": "error",
                    "message": error_msg,
                })

    except WebSocketDisconnect:
        print(f"[CHAT] User {user['staff_id']} disconnected")
    except Exception as e:
        print(f"[CHAT ERROR] {e}")
    finally:
        db.close()
