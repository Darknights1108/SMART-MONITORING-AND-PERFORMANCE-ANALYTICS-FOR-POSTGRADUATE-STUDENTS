"""
Dashboard API - REST endpoints for charts and analytics data.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from app.database import SyncSessionLocal
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def get_summary(user: dict = Depends(get_current_user)):
    """Get high-level dashboard summary numbers."""
    db = SyncSessionLocal()
    try:
        total = db.execute(text("SELECT COUNT(*) FROM student")).scalar()

        status_counts = db.execute(text("""
            SELECT final_status, COUNT(*) FROM graduation_outcome GROUP BY final_status
        """)).fetchall()

        overdue = db.execute(text("""
            SELECT COUNT(DISTINCT student_id) FROM student_milestone
            WHERE status = 'Overdue' OR (expected_date < CURDATE() AND status = 'Pending')
        """)).scalar()

        upcoming_7 = db.execute(text("""
            SELECT COUNT(DISTINCT student_id) FROM student_milestone
            WHERE status = 'Pending'
            AND expected_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)
        """)).scalar()

        upcoming_30 = db.execute(text("""
            SELECT COUNT(DISTINCT student_id) FROM student_milestone
            WHERE status = 'Pending'
            AND expected_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)
        """)).scalar()

        at_risk = db.execute(text("""
            SELECT COUNT(*) FROM v_ppm_us_count WHERE ppm_status = 'AT RISK'
        """)).scalar()

        return {
            "total_students": total,
            "status_breakdown": {r[0]: r[1] for r in status_counts},
            "overdue_students": overdue,
            "upcoming_7_days": upcoming_7,
            "upcoming_30_days": upcoming_30,
            "ppm_at_risk": at_risk,
        }
    finally:
        db.close()


@router.get("/charts/{chart_type}")
def get_chart(chart_type: str, user: dict = Depends(get_current_user)):
    """Get chart data for frontend ECharts rendering."""
    from app.tools.analytics_tools import get_chart_data
    import json

    result = get_chart_data(chart_type)
    try:
        return json.loads(result)
    except Exception:
        return {"error": result}


@router.get("/upcoming-deadlines")
def get_upcoming_deadlines(days: int = 30, user: dict = Depends(get_current_user)):
    """Get list of students with upcoming deadlines."""
    db = SyncSessionLocal()
    try:
        result = db.execute(text("""
            SELECT
                s.student_id_number, s.student_name, s.email,
                m.milestone_name, sm.expected_date,
                DATEDIFF(sm.expected_date, CURDATE()) AS days_left,
                sup.name AS supervisor_name
            FROM student_milestone sm
            JOIN student s ON sm.student_id = s.student_id
            JOIN milestone m ON sm.milestone_id = m.milestone_id
            LEFT JOIN student_supervisor ss ON s.student_id = ss.student_id AND ss.role = 'Main'
            LEFT JOIN supervisor sup ON ss.supervisor_id = sup.supervisor_id
            WHERE sm.status = 'Pending'
            AND sm.expected_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL :days DAY)
            ORDER BY sm.expected_date ASC
        """), {"days": days}).fetchall()

        return [
            {
                "student_id": r[0],
                "student_name": r[1],
                "email": r[2],
                "milestone": r[3],
                "expected_date": str(r[4]),
                "days_left": r[5],
                "supervisor": r[6],
            }
            for r in result
        ]
    finally:
        db.close()


@router.get("/overdue")
def get_overdue_students(user: dict = Depends(get_current_user)):
    """Get list of students with overdue milestones."""
    db = SyncSessionLocal()
    try:
        result = db.execute(text("""
            SELECT
                s.student_id_number, s.student_name,
                m.milestone_name, sm.expected_date,
                DATEDIFF(CURDATE(), sm.expected_date) AS days_overdue,
                sup.name AS supervisor_name
            FROM student_milestone sm
            JOIN student s ON sm.student_id = s.student_id
            JOIN milestone m ON sm.milestone_id = m.milestone_id
            LEFT JOIN student_supervisor ss ON s.student_id = ss.student_id AND ss.role = 'Main'
            LEFT JOIN supervisor sup ON ss.supervisor_id = sup.supervisor_id
            WHERE sm.status = 'Overdue'
            OR (sm.expected_date < CURDATE() AND sm.status = 'Pending')
            ORDER BY sm.expected_date ASC
        """)).fetchall()

        return [
            {
                "student_id": r[0],
                "student_name": r[1],
                "milestone": r[2],
                "expected_date": str(r[3]),
                "days_overdue": r[4],
                "supervisor": r[5],
            }
            for r in result
        ]
    finally:
        db.close()


@router.get("/email-log")
def get_email_log(limit: int = 50, user: dict = Depends(get_current_user)):
    """Get recent email log entries."""
    db = SyncSessionLocal()
    try:
        result = db.execute(text("""
            SELECT
                el.sent_at, el.recipient_type, el.recipient_email,
                el.subject, el.trigger_type, el.urgency_level,
                s.student_name
            FROM email_log el
            JOIN student s ON el.student_id = s.student_id
            ORDER BY el.sent_at DESC
            LIMIT :lim
        """), {"lim": limit}).fetchall()

        return [
            {
                "sent_at": str(r[0]),
                "recipient_type": r[1],
                "recipient_email": r[2],
                "subject": r[3],
                "trigger_type": r[4],
                "urgency_level": r[5],
                "student_name": r[6],
            }
            for r in result
        ]
    finally:
        db.close()
