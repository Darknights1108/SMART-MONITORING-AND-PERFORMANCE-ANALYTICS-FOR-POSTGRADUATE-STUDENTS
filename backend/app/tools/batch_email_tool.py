from smolagents import tool
from sqlalchemy import text
from app.database import SyncSessionLocal
from app.tools.email_tools import _pending, clear_pending_sends, _check_body_content

_FILTER_QUERIES: dict[str, str] = {
    "rpd_due_7d": """
        SELECT DISTINCT s.student_id, s.student_name, s.email
        FROM student s
        JOIN student_milestone sm ON s.student_id = sm.student_id
        JOIN milestone m ON sm.milestone_id = m.milestone_id
        WHERE m.milestone_name LIKE '%RPD%'
          AND sm.actual_date IS NULL
          AND sm.expected_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)
    """,
    "rpd_due_30d": """
        SELECT DISTINCT s.student_id, s.student_name, s.email
        FROM student s
        JOIN student_milestone sm ON s.student_id = sm.student_id
        JOIN milestone m ON sm.milestone_id = m.milestone_id
        WHERE m.milestone_name LIKE '%RPD%'
          AND sm.actual_date IS NULL
          AND sm.expected_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)
    """,
    "rpd_overdue": """
        SELECT DISTINCT s.student_id, s.student_name, s.email
        FROM student s
        JOIN student_milestone sm ON s.student_id = sm.student_id
        JOIN milestone m ON sm.milestone_id = m.milestone_id
        WHERE m.milestone_name LIKE '%RPD%'
          AND sm.actual_date IS NULL
          AND sm.expected_date < CURDATE()
    """,
    "high_risk": """
        SELECT DISTINCT s.student_id, s.student_name, s.email
        FROM student s
        JOIN student_risk_prediction rp ON s.student_id = rp.student_id
        WHERE rp.risk_label = 'High'
    """,
    "medium_risk": """
        SELECT DISTINCT s.student_id, s.student_name, s.email
        FROM student s
        JOIN student_risk_prediction rp ON s.student_id = rp.student_id
        WHERE rp.risk_label = 'Medium'
    """,
    "ppm_unsatisfactory": """
        SELECT DISTINCT s.student_id, s.student_name, s.email
        FROM student s
        JOIN v_ppm_us_count v ON s.student_id = v.student_id
        WHERE v.cumulative_us >= 1
    """,
    "pub_due_30d": """
        SELECT DISTINCT s.student_id, s.student_name, s.email
        FROM student s
        JOIN student_milestone sm ON s.student_id = sm.student_id
        JOIN milestone m ON sm.milestone_id = m.milestone_id
        WHERE m.milestone_name LIKE '%Publication%'
          AND sm.actual_date IS NULL
          AND sm.expected_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)
    """,
    "all_active": """
        SELECT DISTINCT s.student_id, s.student_name, s.email
        FROM student s
        WHERE s.email IS NOT NULL AND s.email != ''
    """,
}


@tool
def send_batch_email(filter_criteria: str, subject: str, body_template: str) -> str:
    """
    Stage a batch email to multiple students matching a filter, for user confirmation before sending.
    Emails are NOT sent immediately — they are queued and the user must confirm.

    Args:
        filter_criteria: One of: 'rpd_due_7d', 'rpd_due_30d', 'rpd_overdue',
                         'high_risk', 'medium_risk', 'ppm_unsatisfactory',
                         'pub_due_30d', 'all_active'.
        subject: Email subject line (same for all recipients).
        body_template: Email body. Supports {name} and {student_id} placeholders per student.
    """
    if filter_criteria not in _FILTER_QUERIES:
        valid = ", ".join(_FILTER_QUERIES.keys())
        return f"Unknown filter_criteria '{filter_criteria}'. Valid options: {valid}"

    body_err = _check_body_content(body_template)
    if body_err:
        return body_err

    db = SyncSessionLocal()
    try:
        rows = db.execute(text(_FILTER_QUERIES[filter_criteria])).fetchall()
    finally:
        db.close()

    if not rows:
        return f"No students found matching filter '{filter_criteria}'. No emails staged."

    clear_pending_sends()
    for student_id, student_name, email in rows:
        body = body_template.replace("{name}", student_name or "").replace(
            "{student_id}", str(student_id) if student_id else ""
        )
        # Strip any remaining unresolved {placeholder} variables so they
        # don't appear literally in the sent email (e.g. {risk_score})
        import re as _re
        body = _re.sub(r'\{[^}]+\}', '', body)
        _pending().append({
            "type": "student",
            "student_id": student_id,
            "name": student_name,
            "email": email,
            "subject": subject,
            "body": body,
        })

    lines = [f"Batch email staged for {len(_pending_sends)} recipient(s) (filter: {filter_criteria}):\n"]
    for i, e in enumerate(_pending_sends, 1):
        lines.append(f"  {i}. {e['name']} <{e['email']}>")
    lines.append(f"\nSubject: {subject}")
    lines.append("\nReply 'send' to confirm and send all, 'cancel' to discard.")
    return "\n".join(lines)
