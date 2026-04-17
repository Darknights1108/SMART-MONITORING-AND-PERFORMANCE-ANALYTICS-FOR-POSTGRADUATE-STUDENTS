"""
Scheduler service - checks deadlines daily and sends reminders
"""
from datetime import date, timedelta
from sqlalchemy import text
from app.database import SyncSessionLocal
from app.services.email_service import (
    send_email, render_student_reminder, render_supervisor_notification
)
from app.config import get_settings
import asyncio

settings = get_settings()


def check_and_send_reminders():
    """
    Main scheduled job: check all pending milestones and send reminders
    based on reminder_rule table.
    """
    db = SyncSessionLocal()
    today = date.today()

    try:
        # Get active reminder rules
        rules = db.execute(text(
            "SELECT days_before, notify_student, notify_supervisor, notify_admin, urgency_level "
            "FROM reminder_rule WHERE is_active = 1 ORDER BY days_before DESC"
        )).fetchall()

        for rule in rules:
            days_before = rule[0]
            notify_student = rule[1]
            notify_supervisor = rule[2]
            notify_admin = rule[3]
            urgency_level = rule[4]

            if days_before > 0:
                # Upcoming: expected_date is exactly N days from now
                # We check a range to avoid missing days
                target_date = today + timedelta(days=days_before)
                condition = "sm.expected_date = :target_date AND sm.status = 'Pending'"
                params = {"target_date": target_date}
            else:
                # Overdue: expected_date has passed
                condition = "sm.expected_date < :today AND sm.status != 'Completed'"
                params = {"today": today}

            # Find students matching this rule
            query = text(f"""
                SELECT
                    s.student_id, s.student_name, s.email, s.student_id_number,
                    m.milestone_name, m.milestone_id,
                    sm.expected_date,
                    DATEDIFF(sm.expected_date, :check_date) AS days_left
                FROM student_milestone sm
                JOIN student s ON sm.student_id = s.student_id
                JOIN milestone m ON sm.milestone_id = m.milestone_id
                WHERE {condition}
                AND NOT EXISTS (
                    SELECT 1 FROM email_log el
                    WHERE el.student_id = s.student_id
                    AND el.milestone_id = m.milestone_id
                    AND el.trigger_type = 'Auto'
                    AND el.urgency_level = :urgency
                    AND DATE(el.sent_at) = :check_date
                )
            """)

            results = db.execute(
                query,
                {**params, "check_date": today, "urgency": urgency_level}
            ).fetchall()

            for row in results:
                student_id = row[0]
                student_name = row[1]
                student_email = row[2]
                student_id_number = row[3]
                milestone_name = row[4]
                milestone_id = row[5]
                expected_date = row[6]
                days_left = row[7] if row[7] else 0

                # Send to student
                if notify_student:
                    subject, body = render_student_reminder(
                        student_name, milestone_name, days_left, str(expected_date)
                    )
                    asyncio.run(send_email(student_email, subject, body, is_html=True))
                    _log_email(db, student_id, "Student", student_email,
                               subject, body, "Auto", urgency_level, milestone_id)

                # Send to supervisor(s)
                if notify_supervisor:
                    supervisors = db.execute(text("""
                        SELECT sup.name, sup.email
                        FROM student_supervisor ss
                        JOIN supervisor sup ON ss.supervisor_id = sup.supervisor_id
                        WHERE ss.student_id = :sid
                    """), {"sid": student_id}).fetchall()

                    for sup in supervisors:
                        sup_subject, sup_body = render_supervisor_notification(
                            sup[0], student_name, student_id_number,
                            milestone_name, days_left, str(expected_date)
                        )
                        asyncio.run(send_email(sup[1], sup_subject, sup_body, is_html=True))
                        _log_email(db, student_id, "Supervisor", sup[1],
                                   sup_subject, sup_body, "Auto", urgency_level, milestone_id)

                # Send to admins
                if notify_admin:
                    admins = db.execute(text("""
                        SELECT name, email FROM supervisor
                        WHERE role IN ('Admin', 'Both') AND is_active = 1
                    """)).fetchall()

                    for admin in admins:
                        adm_subject, adm_body = render_supervisor_notification(
                            admin[0], student_name, student_id_number,
                            milestone_name, days_left, str(expected_date)
                        )
                        asyncio.run(send_email(admin[1], adm_subject, adm_body, is_html=True))
                        _log_email(db, student_id, "Admin", admin[1],
                                   adm_subject, adm_body, "Auto", urgency_level, milestone_id)

        # Also check PPM at-risk students
        _check_ppm_alerts(db, today)

        db.commit()
        print(f"[SCHEDULER] Reminder check completed at {today}")

    except Exception as e:
        db.rollback()
        print(f"[SCHEDULER ERROR] {e}")
    finally:
        db.close()


def _check_ppm_alerts(db, today):
    """Check for PPM at-risk and terminated students."""
    at_risk = db.execute(text("""
        SELECT s.student_id, s.student_name, s.email, s.student_id_number,
               v.cumulative_us, v.ppm_status
        FROM v_ppm_us_count v
        JOIN student s ON v.student_id = s.student_id
        WHERE v.ppm_status IN ('AT RISK', 'TERMINATED')
        AND NOT EXISTS (
            SELECT 1 FROM email_log el
            WHERE el.student_id = s.student_id
            AND el.trigger_type = 'Auto'
            AND el.subject LIKE '%PPM%'
            AND DATE(el.sent_at) = :today
        )
    """), {"today": today}).fetchall()

    for row in at_risk:
        student_id, student_name, student_email, student_id_number, us_count, status = row

        # Notify supervisors
        supervisors = db.execute(text("""
            SELECT sup.name, sup.email
            FROM student_supervisor ss
            JOIN supervisor sup ON ss.supervisor_id = sup.supervisor_id
            WHERE ss.student_id = :sid
        """), {"sid": student_id}).fetchall()

        subject = f"PPM Alert: {student_name} ({student_id_number}) - Status: {status}"
        body = (
            f"Student {student_name} ({student_id_number}) has received "
            f"{us_count} Unsatisfactory PPM result(s). Current status: {status}.\n\n"
            f"Please take immediate action."
        )

        for sup in supervisors:
            asyncio.run(send_email(sup[1], subject, body))
            _log_email(db, student_id, "Supervisor", sup[1],
                       subject, body, "Auto", "Critical", None)

        # If TERMINATED, also notify admins
        if status == "TERMINATED":
            admins = db.execute(text("""
                SELECT name, email FROM supervisor
                WHERE role IN ('Admin', 'Both') AND is_active = 1
            """)).fetchall()
            for admin in admins:
                asyncio.run(send_email(admin[1], subject, body))
                _log_email(db, student_id, "Admin", admin[1],
                           subject, body, "Auto", "Critical", None)


def _log_email(db, student_id, recipient_type, email, subject, body,
               trigger_type, urgency, milestone_id):
    """Insert email log record."""
    db.execute(text("""
        INSERT INTO email_log
        (student_id, recipient_type, recipient_email, subject, body,
         trigger_type, urgency_level, milestone_id)
        VALUES (:sid, :rtype, :email, :subject, :body, :trigger, :urgency, :mid)
    """), {
        "sid": student_id, "rtype": recipient_type, "email": email,
        "subject": subject, "body": body, "trigger": trigger_type,
        "urgency": urgency, "mid": milestone_id,
    })
