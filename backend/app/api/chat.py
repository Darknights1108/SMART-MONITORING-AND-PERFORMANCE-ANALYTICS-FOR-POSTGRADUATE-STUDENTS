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
from app.tools.chart_tool import render_chart
from app.services.connection_manager import manager
import uuid
import json
import re
import asyncio
import traceback

_CONFIRM_WORDS = {"y", "yes", "ok", "okay", "confirm", "确认", "发送", "send", "是", "好", "correct", "看起来不错", "没问题"}
_CANCEL_WORDS  = {"n", "no", "cancel", "取消", "不", "算了", "discard"}

_EMAIL_RE      = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
_SEND_INTENT_RE = re.compile(r'\b(send|email|邮件|发送|发邮件)\b', re.IGNORECASE)

# ── Chart intent detection ─────────────────────────────────────────────────────
# Maps regex patterns to (chart_type, data_source)
_CHART_SOURCES = [
    (re.compile(r'\brisk[\s_-]?distrib\w*|风险分布', re.I), 'risk_distribution'),
    (re.compile(r'\brpd\b',                                re.I), 'rpd'),
    (re.compile(r'\bpublication\b|\bpub\b',                re.I), 'publication'),
    (re.compile(r'\bppm\b',                                re.I), 'ppm'),
    (re.compile(r'\bmilestone[\s_-]?completion|milestones?\b', re.I), 'milestone_completion'),
    (re.compile(r'\benrollment[\s_-]?trend|\benrollment\b', re.I), 'enrollment_trend'),
    (re.compile(r'\bfaculty\b',                             re.I), 'faculty'),
    (re.compile(r'\bdiscipline\b',                          re.I), 'discipline'),
    (re.compile(r'\bfunding\b',                             re.I), 'funding'),
    (re.compile(r'\b(country|region)\b',                    re.I), 'country_region'),
]

_CHART_TRIGGER = re.compile(
    r'\b(show|plot|visuali[sz]e|chart|graph|display|render|draw|展示|图表|可视化|'
    r'pie|bar|histogram|line chart|折线|饼图|柱状|条形)\b',
    re.I,
)
_CHART_TYPE_MAP = [
    (re.compile(r'\bpie\b|饼图', re.I),                 'pie'),
    (re.compile(r'\bbar\b|\bhistogram\b|柱状|条形', re.I), 'bar'),
    (re.compile(r'\bline\b|\btrend\b|折线',  re.I),       'line'),
]


def _detect_chart_intent(message: str) -> list[dict] | None:
    """
    Return a list of chart specs if the message is clearly a chart request,
    otherwise None (hand off to the agent).
    """
    if not _CHART_TRIGGER.search(message):
        return None

    # Determine chart type (default: bar)
    chart_type = 'bar'
    for pattern, ctype in _CHART_TYPE_MAP:
        if pattern.search(message):
            chart_type = ctype
            break

    # Find matching data sources
    specs = []
    for pattern, source in _CHART_SOURCES:
        if pattern.search(message):
            specs.append({"type": chart_type, "data_source": source})

    # Multi-source: allow per-segment type override
    # e.g. "RPD in pie and publication in bar"
    if len(specs) > 1:
        refined = []
        for spec in specs:
            seg_type = chart_type
            for pattern, ctype in _CHART_TYPE_MAP:
                if pattern.search(message):
                    seg_type = ctype
                    break
            refined.append({**spec, "type": seg_type})
        specs = refined

    return specs if specs else None


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
        manager.register(supervisor_id, websocket)
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

            # ── Fast-path: chart requests bypass the LLM entirely ─────────────
            chart_specs = _detect_chart_intent(user_message)
            if chart_specs:
                await websocket.send_json({"type": "thinking"})
                try:
                    result_str = await asyncio.to_thread(
                        render_chart, json.dumps(chart_specs)
                    )
                    payload = json.loads(result_str)
                    if payload.get("__chart_action__"):
                        await websocket.send_json({
                            "type": "chart_action",
                            "message": result_str,
                            "timestamp": datetime.now().isoformat(),
                        })
                    else:
                        await websocket.send_json({
                            "type": "message",
                            "message": payload.get("error", "No chart data found."),
                            "timestamp": datetime.now().isoformat(),
                        })
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Chart error: {e}",
                    })
                continue
            # ──────────────────────────────────────────────────────────────────

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
                        # Forward chart/nav actions immediately as a real message
                        try:
                            obs_parsed = json.loads(obs)
                            if isinstance(obs_parsed, dict) and obs_parsed.get("__chart_action__"):
                                loop.call_soon_threadsafe(step_queue.put_nowait, {
                                    "type": "chart_action",
                                    "message": obs,
                                })
                                return
                            if isinstance(obs_parsed, dict) and obs_parsed.get("__nav_action__"):
                                loop.call_soon_threadsafe(step_queue.put_nowait, {
                                    "type": "nav_action",
                                    "message": obs,
                                })
                                return
                        except (json.JSONDecodeError, TypeError):
                            pass
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

                # Detect chart / nav action payloads
                msg_type = "message"
                try:
                    parsed = json.loads(response_str)
                    if isinstance(parsed, dict) and parsed.get("__chart_action__"):
                        msg_type = "chart_action"
                    elif isinstance(parsed, dict) and parsed.get("__nav_action__"):
                        msg_type = "nav_action"
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
        manager.unregister(supervisor_id, websocket)
        db.close()
