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
from app.tools.email_tools import (
    has_pending_sends, execute_pending_sends, clear_pending_sends,
    stage_email_draft, get_pending_display,
)
import uuid
import json
import re
import asyncio
import traceback

_CONFIRM_WORDS = {"y", "yes", "ok", "okay", "confirm", "确认", "发送", "send", "是", "好", "correct", "看起来不错", "没问题"}
_CANCEL_WORDS  = {"n", "no", "cancel", "取消", "不", "算了", "discard"}

_EMAIL_RE      = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
_SEND_INTENT_RE = re.compile(r'\b(send|email|邮件|发送|发邮件)\b', re.IGNORECASE)


def _matches_words(message: str, word_set: set) -> bool:
    """Return True if any word in word_set appears as a whole word in message."""
    msg = message.strip().lower()
    if msg in word_set:
        return True
    for w in word_set:
        if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", msg):
            return True
    return False




def _try_stage_text_draft(user_message: str, response: str) -> bool:
    """Fallback: model drafted email as plain text instead of calling a tool.
    Parse subject/body out of the response, stage the email, return True on success."""
    if not _SEND_INTENT_RE.search(user_message):
        return False

    email_match = _EMAIL_RE.search(user_message)
    if not email_match:
        return False
    to_email = email_match.group(0)

    # Match **Subject:** ... **Body:** (handles bold markdown, optional colons)
    subj_match = re.search(
        r'\*{0,2}(?:Subject|主题)\*{0,2}\s*:+\s*\*{0,2}(.+?)\*{0,2}\s*'
        r'(?=\*{0,2}(?:Body|正文)\*{0,2})',
        response, re.IGNORECASE | re.DOTALL,
    )
    body_match = re.search(
        r'\*{0,2}(?:Body|正文)\*{0,2}\s*:+\s*\*{0,2}([\s\S]+?)(?:---|Let me know|如果您|$)',
        response, re.IGNORECASE,
    )

    if not subj_match or not body_match:
        return False

    subject = subj_match.group(1).strip()
    body = body_match.group(1).strip().strip('*').strip()

    if not subject or not body:
        return False

    recipient_name = to_email.split('@')[0]
    stage_email_draft(to_email, recipient_name, subject, body)
    return True

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

    # Each connection gets its own agent — enables true multi-turn memory
    # via reset=False without sharing state across users.
    agent = get_agent()
    db = SyncSessionLocal()
    _first_message = True   # track whether to use reset=True on first call

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
            if has_pending_sends():
                if _matches_words(user_message, _CONFIRM_WORDS):
                    try:
                        result = await execute_pending_sends()
                    except Exception as e:
                        result = f"Failed to send email: {e}"
                        clear_pending_sends()
                    await websocket.send_json({
                        "type": "message",
                        "message": result,
                        "timestamp": datetime.now().isoformat(),
                    })
                    continue
                elif _matches_words(user_message, _CANCEL_WORDS):
                    clear_pending_sends()
                    await websocket.send_json({
                        "type": "message",
                        "message": "Email cancelled. No emails were sent.",
                        "timestamp": datetime.now().isoformat(),
                    })
                    continue
                else:
                    # User wants to revise the draft — discard old draft and let agent re-draft
                    clear_pending_sends()

            # Save user message
            db.execute(text("""
                INSERT INTO chat_history (supervisor_id, session_id, message, role)
                VALUES (:sid, :sess, :msg, 'user')
            """), {"sid": supervisor_id, "sess": session_id, "msg": user_message})
            db.commit()

            # Send "thinking" indicator
            await websocket.send_json({"type": "thinking"})

            try:
                # reset=True on first message (clean slate),
                # reset=False on all subsequent messages (agent remembers the conversation).
                should_reset = _first_message
                _first_message = False

                # Stream intermediate steps via a thread-safe queue
                loop = asyncio.get_event_loop()
                step_queue: asyncio.Queue = asyncio.Queue()

                def _step_callback(step_log):
                    from smolagents.agents import ActionStep
                    if not isinstance(step_log, ActionStep):
                        return
                    if step_log.llm_output:
                        loop.call_soon_threadsafe(step_queue.put_nowait, {
                            "type": "agent_thinking",
                            "content": step_log.llm_output,
                        })
                    if step_log.tool_calls:
                        for tc in step_log.tool_calls:
                            loop.call_soon_threadsafe(step_queue.put_nowait, {
                                "type": "tool_call",
                                "tool": tc.name,
                                "args": str(tc.arguments),
                            })
                    if step_log.observations:
                        obs = str(step_log.observations)
                        loop.call_soon_threadsafe(step_queue.put_nowait, {
                            "type": "tool_result",
                            "content": obs[:800] + ("…" if len(obs) > 800 else ""),
                        })

                agent.step_callbacks.append(_step_callback)

                async def _run_agent():
                    try:
                        return await asyncio.to_thread(
                            agent.run,
                            user_message,
                            reset=should_reset,
                        )
                    finally:
                        loop.call_soon_threadsafe(step_queue.put_nowait, None)

                agent_task = asyncio.create_task(_run_agent())

                try:
                    while True:
                        step_data = await step_queue.get()
                        if step_data is None:
                            break
                        await websocket.send_json({
                            **step_data,
                            "timestamp": datetime.now().isoformat(),
                        })
                    response = await agent_task
                finally:
                    try:
                        agent.step_callbacks.remove(_step_callback)
                    except ValueError:
                        pass

                response_str = str(response)

                # If the agent staged an email via a tool call, show the actual draft
                # content instead of the agent's generic summary message.
                if has_pending_sends():
                    response_str = get_pending_display()
                # Fallback: model drafted email as plain text without calling a tool —
                # parse and stage it, then show the draft.
                elif _try_stage_text_draft(user_message, response_str):
                    response_str = get_pending_display()

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
