"""
Smolagents tools for sending emails via the chatbox.

Send flow (two-phase):
  1. Agent calls send_email_to_student / send_email_to_supervisor
     → email is staged in _pending_sends, NOT sent yet
     → tool returns a draft preview asking for confirmation
  2. User replies with a confirmation word (y / yes / ok / 确认 / send / 发送)
     → chat.py detects it and calls execute_pending_sends()
     → emails are actually sent and cleared from the queue
"""
from smolagents import tool
from sqlalchemy import text
from app.database import SyncSessionLocal
from app.services.email_service import send_email
from app.config import get_settings
import asyncio
import time

settings = get_settings()

# ---------------------------------------------------------------------------
# Pending email queue  (staged, not yet sent)
# ---------------------------------------------------------------------------
_pending_sends: list[dict] = []   # each entry: {type, id, name, email, subject, body}

# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------
_email_send_log: list[float] = []
_RATE_LIMIT = 5
_RATE_WINDOW = 300   # seconds

# ---------------------------------------------------------------------------
# Content block list
# ---------------------------------------------------------------------------
_BLOCKED_BODY_PATTERNS = [
    "<script", "javascript:", "data:text/html",
    "奖学金已取消", "scholarship.*cancel",
    "密码", "password", "pwd",
]


def _check_rate_limit() -> str | None:
    now = time.time()
    recent = [t for t in _email_send_log if now - t < _RATE_WINDOW]
    _email_send_log.clear()
    _email_send_log.extend(recent)
    if len(recent) >= _RATE_LIMIT:
        return f"Rate limit reached: max {_RATE_LIMIT} emails per {_RATE_WINDOW // 60} minutes."
    return None


def _check_body_content(body: str) -> str | None:
    body_lower = body.lower()
    for pattern in _BLOCKED_BODY_PATTERNS:
        if pattern.lower() in body_lower:
            return f"Email blocked: body contains disallowed content (matched: '{pattern}')."
    return None


# ---------------------------------------------------------------------------
# Public helpers called by chat.py (not agent tools)
# ---------------------------------------------------------------------------

def has_pending_sends() -> bool:
    return bool(_pending_sends)


def get_pending_summary() -> str:
    """Return a human-readable list of staged emails."""
    lines = [f"{len(_pending_sends)} email(s) ready to send:"]
    for i, e in enumerate(_pending_sends, 1):
        lines.append(f"  {i}. To: {e['name']} <{e['email']}> — Subject: {e['subject']}")
    return "\n".join(lines)


def execute_pending_sends() -> str:
    """Actually send all staged emails. Called from chat.py on confirmation."""
    if not _pending_sends:
        return "No pending emails to send."

    results = []
    db = SyncSessionLocal()
    try:
        for entry in _pending_sends:
            # Rate limit check at send time too
            now = time.time()
            recent = [t for t in _email_send_log if now - t < _RATE_WINDOW]
            _email_send_log.clear()
            _email_send_log.extend(recent)
            if len(recent) >= _RATE_LIMIT:
                results.append(f"  ✗ {entry['name']}: rate limit reached, skipped.")
                continue
            _email_send_log.append(now)

            success = asyncio.run(send_email(entry["email"], entry["subject"], entry["body"]))
            if success:
                # Log to DB if student email
                if entry["type"] == "student" and entry.get("student_id"):
                    db.execute(text("""
                        INSERT INTO email_log
                        (student_id, recipient_type, recipient_email, subject, body,
                         trigger_type, urgency_level)
                        VALUES (:sid, 'Student', :email, :subject, :body, 'Manual', 'Normal')
                    """), {
                        "sid": entry["student_id"],
                        "email": entry["email"],
                        "subject": entry["subject"],
                        "body": entry["body"],
                    })
                    db.commit()
                results.append(f"  ✓ Sent to {entry['name']} ({entry['email']})")
            else:
                results.append(f"  ✗ Failed to send to {entry['name']}")

        _pending_sends.clear()
        return "Email send results:\n" + "\n".join(results)
    finally:
        db.close()


def clear_pending_sends() -> None:
    """Discard all staged emails (user cancelled)."""
    _pending_sends.clear()


# ---------------------------------------------------------------------------
# Agent tools
# ---------------------------------------------------------------------------

@tool
def send_email_to_student(student_search: str, subject: str, body: str) -> str:
    """
    Stage an email to a specific student for user confirmation before sending.
    The email is NOT sent immediately — it is queued and the user must confirm.

    Args:
        student_search: Student name or ID number to find.
        subject: Email subject line.
        body: Full email body content.
    """
    body_err = _check_body_content(body)
    if body_err:
        return body_err

    db = SyncSessionLocal()
    try:
        student = db.execute(text("""
            SELECT student_id, student_name, email
            FROM student
            WHERE student_name LIKE :term OR student_id_number LIKE :term
            LIMIT 1
        """), {"term": f"%{student_search}%"}).fetchone()

        if not student:
            return f"Student '{student_search}' not found."

        student_id, student_name, student_email = student

        _pending_sends.append({
            "type": "student",
            "student_id": student_id,
            "name": student_name,
            "email": student_email,
            "subject": subject,
            "body": body,
        })

        return (
            f"📧 Email staged (NOT sent yet):\n"
            f"  To: {student_name} <{student_email}>\n"
            f"  Subject: {subject}\n"
            f"  Body:\n{body}\n\n"
            f"Reply with y / yes / ok / 确认 to send, or cancel to discard."
        )
    finally:
        db.close()


@tool
def send_email_to_supervisor(supervisor_search: str, subject: str, body: str) -> str:
    """
    Stage an email to a supervisor for user confirmation before sending.
    The email is NOT sent immediately — it is queued and the user must confirm.

    Args:
        supervisor_search: Supervisor name or staff ID to find.
        subject: Email subject line.
        body: Full email body content.
    """
    body_err = _check_body_content(body)
    if body_err:
        return body_err

    db = SyncSessionLocal()
    try:
        supervisor = db.execute(text("""
            SELECT supervisor_id, name, email
            FROM supervisor
            WHERE name LIKE :term OR staff_id LIKE :term
            LIMIT 1
        """), {"term": f"%{supervisor_search}%"}).fetchone()

        if not supervisor:
            return f"Supervisor '{supervisor_search}' not found."

        sup_id, sup_name, sup_email = supervisor

        _pending_sends.append({
            "type": "supervisor",
            "supervisor_id": sup_id,
            "name": sup_name,
            "email": sup_email,
            "subject": subject,
            "body": body,
        })

        return (
            f"📧 Email staged (NOT sent yet):\n"
            f"  To: {sup_name} <{sup_email}>\n"
            f"  Subject: {subject}\n"
            f"  Body:\n{body}\n\n"
            f"Reply with y / yes / ok / 确认 to send, or cancel to discard."
        )
    finally:
        db.close()


@tool
def draft_reminder_email(student_search: str, milestone_name: str, tone: str) -> str:
    """
    Draft a reminder email for a student without sending it.
    Returns the draft for review. To send, call send_email_to_student afterwards.

    Args:
        student_search: Student name or ID number.
        milestone_name: The milestone to remind about (e.g., "RPD", "Publication", "Thesis").
        tone: The tone of the email - "gentle", "firm", or "urgent".
    """
    db = SyncSessionLocal()
    try:
        student = db.execute(text("""
            SELECT s.student_name, s.student_id_number, s.email,
                   m.milestone_name, sm.expected_date,
                   DATEDIFF(sm.expected_date, CURDATE()) AS days_left
            FROM student s
            JOIN student_milestone sm ON s.student_id = sm.student_id
            JOIN milestone m ON sm.milestone_id = m.milestone_id
            WHERE (s.student_name LIKE :term OR s.student_id_number LIKE :term)
            AND m.milestone_name LIKE :milestone
            LIMIT 1
        """), {"term": f"%{student_search}%", "milestone": f"%{milestone_name}%"}).fetchone()

        if not student:
            return f"No matching student/milestone found for '{student_search}' / '{milestone_name}'."

        name, sid, email, ms_name, exp_date, days_left = student

        overdue_note = ""
        if days_left is not None and days_left < 0:
            overdue_note = f" (OVERDUE by {abs(days_left)} days)"
        elif days_left == 0:
            overdue_note = " (DUE TODAY)"

        return (
            f"DRAFT — {tone.upper()} reminder for {name} ({sid})\n"
            f"To: {email}\n"
            f"Milestone: {ms_name} | Due: {exp_date}{overdue_note}\n\n"
            f"Use this information to compose the email body, then call "
            f"send_email_to_student to stage it for confirmation."
        )
    finally:
        db.close()
