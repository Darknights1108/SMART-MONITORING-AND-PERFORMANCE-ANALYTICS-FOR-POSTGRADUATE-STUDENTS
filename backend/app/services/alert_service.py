from datetime import datetime
from sqlalchemy import text
from app.database import SyncSessionLocal
from app.services.connection_manager import manager


async def check_and_push_alerts():
    db = SyncSessionLocal()
    try:
        alerts: list[dict] = []

        # Upcoming deadlines in next 3 days
        upcoming = db.execute(text("""
            SELECT s.student_name, m.milestone_name,
                   DATEDIFF(sm.expected_date, CURDATE()) AS days_left
            FROM student_milestone sm
            JOIN student s ON sm.student_id = s.student_id
            JOIN milestone m ON sm.milestone_id = m.milestone_id
            WHERE sm.actual_date IS NULL
              AND sm.expected_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 3 DAY)
            ORDER BY sm.expected_date
        """)).fetchall()

        for name, milestone, days_left in upcoming:
            due_str = "today" if days_left == 0 else f"in {days_left} day(s)"
            alerts.append({
                "level": "warning",
                "message": f"{name} has '{milestone}' due {due_str}.",
                "student_name": name,
            })

        # High risk students
        high_risk = db.execute(text("""
            SELECT s.student_name
            FROM student_risk_prediction rp
            JOIN student s ON rp.student_id = s.student_id
            WHERE rp.risk_label = 'High'
        """)).fetchall()

        for (name,) in high_risk:
            alerts.append({
                "level": "high",
                "message": f"{name} is flagged as High risk.",
                "student_name": name,
            })

        if alerts:
            await manager.broadcast({
                "type": "push_alert",
                "alerts": alerts,
                "timestamp": datetime.now().isoformat(),
            })
    finally:
        db.close()
