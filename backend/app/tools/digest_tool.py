from smolagents import tool
from sqlalchemy import text
from app.database import SyncSessionLocal


@tool
def get_weekly_digest() -> str:
    """
    Return a formatted weekly digest covering upcoming deadlines, high-risk students,
    overdue milestones, and PPM alerts. No parameters required.
    """
    db = SyncSessionLocal()
    try:
        sections: list[str] = ["📋 **Weekly Digest**\n"]

        # 1. Upcoming deadlines (next 7 days)
        upcoming = db.execute(text("""
            SELECT s.student_name, m.milestone_name,
                   DATEDIFF(sm.expected_date, CURDATE()) AS days_left,
                   sm.expected_date
            FROM student_milestone sm
            JOIN student s ON sm.student_id = s.student_id
            JOIN milestone m ON sm.milestone_id = m.milestone_id
            WHERE sm.actual_date IS NULL
              AND sm.expected_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)
            ORDER BY sm.expected_date
        """)).fetchall()

        sections.append("📅 **Upcoming Deadlines (Next 7 Days)**")
        if upcoming:
            for name, milestone, days_left, exp_date in upcoming:
                due_str = "today" if days_left == 0 else f"in {days_left} day(s)"
                sections.append(f"  • {name} — {milestone} due {due_str} ({exp_date})")
        else:
            sections.append("  No deadlines in the next 7 days.")

        # 2. High-risk students
        high_risk = db.execute(text("""
            SELECT s.student_name, s.student_id_number, rp.risk_score
            FROM risk_prediction rp
            JOIN student s ON rp.student_id = s.student_id
            WHERE rp.risk_label = 'High'
            ORDER BY rp.risk_score DESC
        """)).fetchall()

        sections.append("\n📊 **High Risk Students**")
        if high_risk:
            for name, sid, score in high_risk:
                score_str = f"{score:.2f}" if score is not None else "N/A"
                sections.append(f"  • {name} ({sid}) — risk score: {score_str}")
        else:
            sections.append("  No high-risk students currently.")

        # 3. Overdue milestones
        overdue = db.execute(text("""
            SELECT s.student_name, m.milestone_name,
                   DATEDIFF(CURDATE(), sm.expected_date) AS days_overdue,
                   sm.expected_date
            FROM student_milestone sm
            JOIN student s ON sm.student_id = s.student_id
            JOIN milestone m ON sm.milestone_id = m.milestone_id
            WHERE sm.actual_date IS NULL
              AND sm.expected_date < CURDATE()
            ORDER BY sm.expected_date
        """)).fetchall()

        sections.append("\n⚠️ **Overdue Milestones**")
        if overdue:
            for name, milestone, days_overdue, exp_date in overdue:
                sections.append(f"  • {name} — {milestone} overdue by {days_overdue} day(s) (was due {exp_date})")
        else:
            sections.append("  No overdue milestones.")

        # 4. PPM alerts (AT RISK / TERMINATED)
        ppm_alerts = db.execute(text("""
            SELECT s.student_name, s.student_id_number, v.ppm_status, v.cumulative_us
            FROM v_ppm_us_count v
            JOIN student s ON v.student_id = s.student_id
            WHERE v.ppm_status IN ('AT RISK', 'TERMINATED')
            ORDER BY v.cumulative_us DESC
        """)).fetchall()

        sections.append("\n🔴 **PPM Alerts (AT RISK / TERMINATED)**")
        if ppm_alerts:
            for name, sid, status, us_count in ppm_alerts:
                sections.append(f"  • {name} ({sid}) — {status} ({us_count} unsatisfactory PPM(s))")
        else:
            sections.append("  No PPM alerts.")

        return "\n".join(sections)
    finally:
        db.close()
