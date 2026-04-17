"""
Email service - sends emails via SMTP
"""
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from app.config import get_settings

settings = get_settings()

template_dir = Path(__file__).parent.parent.parent / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(template_dir)))


async def send_email(
    to_email: str,
    subject: str,
    body: str,
    is_html: bool = False,
) -> bool:
    """Send an email via SMTP."""
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email
    msg["Subject"] = subject

    content_type = "html" if is_html else "plain"
    msg.attach(MIMEText(body, content_type, "utf-8"))

    try:
        use_tls = bool(settings.SMTP_USER and settings.SMTP_PASSWORD)
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            start_tls=use_tls,
        )
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send to {to_email}: {e}")
        return False


def render_student_reminder(
    student_name: str,
    milestone_name: str,
    days_left: int,
    expected_date: str,
) -> tuple[str, str]:
    """Render student reminder email. Returns (subject, body)."""
    if days_left > 0:
        subject = f"Reminder: {milestone_name} due in {days_left} days"
    else:
        subject = f"OVERDUE: {milestone_name} was due on {expected_date}"

    try:
        template = jinja_env.get_template("student_reminder.html")
        body = template.render(
            student_name=student_name,
            milestone_name=milestone_name,
            days_left=days_left,
            expected_date=expected_date,
        )
        return subject, body
    except Exception:
        # Fallback plain text
        body = (
            f"Dear {student_name},\n\n"
            f"This is a reminder that your '{milestone_name}' "
            f"is due on {expected_date} ({days_left} days remaining).\n\n"
            f"Please ensure timely submission.\n\n"
            f"Best regards,\n{settings.SMTP_FROM_NAME}"
        )
        return subject, body


def render_supervisor_notification(
    supervisor_name: str,
    student_name: str,
    student_id_number: str,
    milestone_name: str,
    days_left: int,
    expected_date: str,
) -> tuple[str, str]:
    """Render supervisor notification email. Returns (subject, body)."""
    if days_left > 0:
        subject = f"Student Alert: {student_name} - {milestone_name} due in {days_left} days"
    else:
        subject = f"OVERDUE Alert: {student_name} - {milestone_name}"

    try:
        template = jinja_env.get_template("supervisor_notification.html")
        body = template.render(
            supervisor_name=supervisor_name,
            student_name=student_name,
            student_id_number=student_id_number,
            milestone_name=milestone_name,
            days_left=days_left,
            expected_date=expected_date,
        )
        return subject, body
    except Exception:
        body = (
            f"Dear {supervisor_name},\n\n"
            f"This is to inform you that your student {student_name} ({student_id_number}) "
            f"has an upcoming milestone '{milestone_name}' due on {expected_date} "
            f"({days_left} days remaining).\n\n"
            f"Please follow up accordingly.\n\n"
            f"Best regards,\n{settings.SMTP_FROM_NAME}"
        )
        return subject, body
