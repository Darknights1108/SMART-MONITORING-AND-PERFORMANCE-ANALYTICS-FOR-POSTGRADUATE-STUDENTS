"""
Chart rendering tool for the AI agent.
Agent calls render_chart() → frontend renders interactive charts in chat.
"""
from smolagents import tool
from sqlalchemy import text
from app.database import SyncSessionLocal
import json


@tool
def render_chart(charts: str) -> str:
    """
    Render one or more charts directly in the chat UI.
    Call this whenever the user asks to visualise, plot, show, or compare data.
    Multiple charts can be rendered in one call.

    Args:
        charts: JSON array of chart specs. Each item must have:
            "type"        → "pie" | "bar" | "line"
            "data_source" → one of:
                "rpd"                  RPD milestone status (on time / late / overdue / pending)
                "publication"          Publication status (accepted / under review / rejected)
                "ppm"                  PPM results (Satisfactory / Unsatisfactory)
                "risk_distribution"    Risk label counts (High / Medium / Low)
                "milestone_completion" All milestones status breakdown (stacked bar)
                "enrollment_trend"     Monthly student enrollment trend (line)
                "faculty"              Students per faculty
                "discipline"           Students per discipline group
                "funding"              Students per funding type
                "country_region"       Students per region

        Example: '[{"type":"pie","data_source":"rpd"},{"type":"bar","data_source":"publication"}]'

    Returns:
        JSON with __chart_action__ flag — frontend renders this automatically.
    """
    try:
        specs = json.loads(charts)
        if not isinstance(specs, list):
            specs = [specs]
    except json.JSONDecodeError:
        return '{"error": "charts must be a valid JSON array"}'

    db = SyncSessionLocal()
    results = []
    try:
        for spec in specs:
            data = _fetch(db, spec.get("type", "bar"), spec.get("data_source", ""))
            if data:
                results.append(data)
    finally:
        db.close()

    if not results:
        return '{"error": "No data found for the requested charts"}'

    return json.dumps({"__chart_action__": True, "charts": results}, ensure_ascii=False)


# ── Data fetchers ──────────────────────────────────────────────────────────────

def _fetch(db, chart_type: str, source: str) -> dict | None:

    if source == "rpd":
        rows = db.execute(text("""
            SELECT
                CASE
                    WHEN sm.actual_date IS NOT NULL AND sm.actual_date <= sm.expected_date THEN 'On Time'
                    WHEN sm.actual_date IS NOT NULL AND sm.actual_date >  sm.expected_date THEN 'Submitted Late'
                    WHEN sm.expected_date IS NOT NULL AND sm.expected_date < CURDATE()     THEN 'Overdue'
                    WHEN sm.expected_date IS NOT NULL                                      THEN 'Pending'
                    ELSE 'Not Scheduled'
                END AS status,
                COUNT(*) AS cnt
            FROM student_milestone sm
            WHERE sm.milestone_id = 1
            GROUP BY status
            ORDER BY cnt DESC
        """)).fetchall()
        title = "RPD Milestone Status"
        return _format(chart_type, title, rows, colors=["#22c55e","#f59e0b","#ef4444","#94a3b8","#e2e8f0"])

    if source == "publication":
        rows = db.execute(text("""
            SELECT
                CASE
                    WHEN sp.status IN ('Accepted','Published')      THEN 'Accepted / Published'
                    WHEN sp.status IN ('Submitted','Under Review')  THEN 'Under Review'
                    WHEN sp.status = 'Rejected'                     THEN 'Rejected'
                    ELSE sp.status
                END AS bucket,
                COUNT(*) AS cnt
            FROM student_publication sp
            GROUP BY bucket
            ORDER BY cnt DESC
        """)).fetchall()
        title = "Publication Status"
        return _format(chart_type, title, rows, colors=["#6366f1","#f59e0b","#ef4444"])

    if source == "ppm":
        rows = db.execute(text("""
            SELECT result, COUNT(*) AS cnt
            FROM ppm_record
            GROUP BY result
            ORDER BY cnt DESC
        """)).fetchall()
        title = "PPM Results"
        return _format(chart_type, title, rows, colors=["#22c55e","#ef4444","#94a3b8"])

    if source == "risk_distribution":
        rows = db.execute(text("""
            SELECT risk_label, COUNT(*) AS cnt
            FROM student_risk_prediction
            GROUP BY risk_label
            ORDER BY FIELD(risk_label,'High','Medium','Low')
        """)).fetchall()
        title = "Risk Distribution"
        return _format(chart_type, title, rows, colors=["#ef4444","#f59e0b","#22c55e"])

    if source == "milestone_completion":
        rows = db.execute(text("""
            SELECT
                m.milestone_name,
                SUM(CASE WHEN sm.actual_date IS NOT NULL AND sm.actual_date <= sm.expected_date THEN 1 ELSE 0 END) AS on_time,
                SUM(CASE WHEN sm.actual_date IS NOT NULL AND sm.actual_date >  sm.expected_date THEN 1 ELSE 0 END) AS late,
                SUM(CASE WHEN sm.actual_date IS NULL     AND sm.expected_date >= CURDATE()      THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN sm.actual_date IS NULL     AND sm.expected_date <  CURDATE()      THEN 1 ELSE 0 END) AS overdue
            FROM student_milestone sm
            JOIN milestone m ON sm.milestone_id = m.milestone_id
            GROUP BY m.milestone_id, m.milestone_name
            ORDER BY m.milestone_order
        """)).fetchall()
        return {
            "type": "stacked_bar",
            "title": "Milestone Completion Status",
            "categories": [r[0] for r in rows],
            "series": [
                {"name": "On Time",  "data": [r[1] for r in rows], "color": "#22c55e"},
                {"name": "Late",     "data": [r[2] for r in rows], "color": "#f59e0b"},
                {"name": "Pending",  "data": [r[3] for r in rows], "color": "#94a3b8"},
                {"name": "Overdue",  "data": [r[4] for r in rows], "color": "#ef4444"},
            ],
        }

    if source == "enrollment_trend":
        rows = db.execute(text("""
            SELECT DATE_FORMAT(enrollment_date,'%Y-%m') AS month, COUNT(*) AS cnt
            FROM student
            GROUP BY month
            ORDER BY month
        """)).fetchall()
        return {
            "type": "line",
            "title": "Monthly Enrollment Trend",
            "categories": [r[0] for r in rows],
            "values":     [r[1] for r in rows],
        }

    if source == "faculty":
        rows = db.execute(text("""
            SELECT f.faculty_description, COUNT(*) AS cnt
            FROM student s
            JOIN program p   ON s.program_id  = p.program_id
            JOIN faculty f   ON p.faculty_id  = f.faculty_id
            GROUP BY f.faculty_id, f.faculty_description
            ORDER BY cnt DESC
        """)).fetchall()
        return _format(chart_type, "Students by Faculty", rows)

    if source == "discipline":
        rows = db.execute(text("""
            SELECT d.discipline_group, COUNT(*) AS cnt
            FROM student s
            JOIN discipline d ON s.discipline_id = d.discipline_id
            GROUP BY d.discipline_group
            ORDER BY cnt DESC
        """)).fetchall()
        return _format(chart_type, "Students by Discipline", rows)

    if source == "funding":
        rows = db.execute(text("""
            SELECT ft.funding_name, COUNT(*) AS cnt
            FROM student s
            JOIN funding_type ft ON s.funding_id = ft.funding_id
            GROUP BY ft.funding_id, ft.funding_name
            ORDER BY cnt DESC
        """)).fetchall()
        return _format(chart_type, "Students by Funding Type", rows)

    if source == "country_region":
        rows = db.execute(text("""
            SELECT cr.region_name, COUNT(*) AS cnt
            FROM student s
            JOIN country c        ON s.country_id = c.country_id
            JOIN country_region cr ON c.region_id  = cr.region_id
            GROUP BY cr.region_id, cr.region_name
            ORDER BY cnt DESC
        """)).fetchall()
        return _format(chart_type, "Students by Region", rows)

    return None


def _format(chart_type: str, title: str, rows, colors: list | None = None) -> dict:
    """Convert (label, count) rows → pie or bar payload."""
    if chart_type == "pie":
        data = [{"name": r[0], "value": int(r[1])} for r in rows]
        result: dict = {"type": "pie", "title": title, "data": data}
        if colors:
            result["colors"] = colors[:len(data)]
        return result
    # default: bar
    result = {
        "type": "bar",
        "title": title,
        "categories": [r[0] for r in rows],
        "values":     [int(r[1]) for r in rows],
    }
    if colors:
        result["colors"] = colors[:len(rows)]
    return result
