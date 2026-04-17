"""
Smolagents tools for data analytics.
Agent can use these to answer analytical questions and generate chart data.
"""
from smolagents import tool
from sqlalchemy import text
from app.database import SyncSessionLocal
import json
from app.tools.sanitizer import sanitize_tool_output


@tool
def analyze_by_faculty() -> str:
    """
    Analyze student distribution and performance by faculty.
    Returns counts, overdue rates, and average time-to-degree per faculty.
    """
    db = SyncSessionLocal()
    try:
        result = db.execute(text("""
            SELECT
                f.faculty_description,
                COUNT(DISTINCT s.student_id) AS total_students,
                SUM(CASE WHEN go.final_status = 'Graduated On-time' THEN 1 ELSE 0 END) AS on_time,
                SUM(CASE WHEN go.final_status = 'Graduated Delayed' THEN 1 ELSE 0 END) AS delayed,
                SUM(CASE WHEN go.final_status = 'Dropped Out' THEN 1 ELSE 0 END) AS dropped,
                SUM(CASE WHEN go.final_status = 'Ongoing' THEN 1 ELSE 0 END) AS ongoing,
                ROUND(AVG(go.time_to_degree_months), 1) AS avg_months
            FROM student s
            JOIN program p ON s.program_id = p.program_id
            JOIN faculty f ON p.faculty_id = f.faculty_id
            LEFT JOIN graduation_outcome go ON s.student_id = go.student_id
            GROUP BY f.faculty_id, f.faculty_description
            ORDER BY total_students DESC
        """)).fetchall()

        output = ["=== Faculty Analysis ===\n"]
        for row in result:
            total = row[1]
            delay_rate = round((row[3] / total * 100), 1) if total > 0 else 0
            output.append(
                f"{row[0]}:\n"
                f"  Total: {total} | On-time: {row[2]} | Delayed: {row[3]} | "
                f"Dropped: {row[4]} | Ongoing: {row[5]}\n"
                f"  Delay Rate: {delay_rate}% | Avg Time-to-Degree: {row[6] or 'N/A'} months\n"
            )
        return "\n".join(output)
    finally:
        db.close()


@tool
def analyze_by_discipline() -> str:
    """
    Analyze student distribution and performance by discipline group.
    Returns counts, overdue rates per discipline group (STEM, Social Science, etc.).
    """
    db = SyncSessionLocal()
    try:
        result = db.execute(text("""
            SELECT
                d.discipline_group,
                COUNT(DISTINCT s.student_id) AS total,
                SUM(CASE WHEN go.is_delayed = 1 THEN 1 ELSE 0 END) AS delayed,
                ROUND(AVG(go.time_to_degree_months), 1) AS avg_months
            FROM student s
            JOIN discipline d ON s.discipline_id = d.discipline_id
            LEFT JOIN graduation_outcome go ON s.student_id = go.student_id
            GROUP BY d.discipline_group
            ORDER BY total DESC
        """)).fetchall()

        output = ["=== Discipline Group Analysis ===\n"]
        for row in result:
            delay_rate = round((row[2] / row[1] * 100), 1) if row[1] > 0 else 0
            output.append(
                f"{row[0]}: {row[1]} students | "
                f"Delayed: {row[2]} ({delay_rate}%) | "
                f"Avg Duration: {row[3] or 'N/A'} months"
            )
        return "\n".join(output)
    finally:
        db.close()


@tool
def analyze_milestone_completion() -> str:
    """
    Analyze milestone completion rates and average delays across all students.
    Shows how many students completed each milestone on time vs late.
    """
    db = SyncSessionLocal()
    try:
        result = db.execute(text("""
            SELECT
                m.milestone_name,
                COUNT(*) AS total,
                SUM(CASE WHEN sm.status = 'Completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN sm.status = 'Pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN sm.status = 'Overdue' THEN 1 ELSE 0 END) AS overdue,
                ROUND(AVG(
                    CASE WHEN sm.actual_date IS NOT NULL AND sm.expected_date IS NOT NULL
                    THEN DATEDIFF(sm.actual_date, sm.expected_date) END
                ), 1) AS avg_delay_days
            FROM student_milestone sm
            JOIN milestone m ON sm.milestone_id = m.milestone_id
            GROUP BY m.milestone_id, m.milestone_name
            ORDER BY m.milestone_order
        """)).fetchall()

        output = ["=== Milestone Completion Analysis ===\n"]
        for row in result:
            completion_rate = round((row[2] / row[1] * 100), 1) if row[1] > 0 else 0
            output.append(
                f"{row[0]}:\n"
                f"  Total: {row[1]} | Completed: {row[2]} ({completion_rate}%) | "
                f"Pending: {row[3]} | Overdue: {row[4]}\n"
                f"  Avg Delay: {row[5] or 0} days\n"
            )
        return "\n".join(output)
    finally:
        db.close()


@tool
def analyze_funding_impact() -> str:
    """
    Analyze how different funding types affect graduation outcomes.
    Compares delay rates and time-to-degree across funding types.
    """
    db = SyncSessionLocal()
    try:
        result = db.execute(text("""
            SELECT
                ft.funding_name,
                COUNT(DISTINCT s.student_id) AS total,
                SUM(CASE WHEN go.is_delayed = 1 THEN 1 ELSE 0 END) AS delayed,
                ROUND(AVG(go.time_to_degree_months), 1) AS avg_months
            FROM student s
            JOIN funding_type ft ON s.funding_id = ft.funding_id
            LEFT JOIN graduation_outcome go ON s.student_id = go.student_id
            GROUP BY ft.funding_id, ft.funding_name
            ORDER BY total DESC
        """)).fetchall()

        output = ["=== Funding Impact Analysis ===\n"]
        for row in result:
            delay_rate = round((row[2] / row[1] * 100), 1) if row[1] > 0 else 0
            output.append(
                f"{row[0]}: {row[1]} students | "
                f"Delayed: {row[2]} ({delay_rate}%) | "
                f"Avg Duration: {row[3] or 'N/A'} months"
            )
        return "\n".join(output)
    finally:
        db.close()


@tool
def get_chart_data(chart_type: str) -> str:
    """
    Get data formatted for frontend charts (ECharts).
    Returns JSON data that the frontend can directly use for visualization.

    Args:
        chart_type: Type of chart data to generate. Options:
            - "status_pie": Graduation status distribution pie chart
            - "faculty_bar": Students per faculty bar chart
            - "milestone_bar": Milestone completion rates bar chart
            - "monthly_trend": Monthly enrollment trend line chart
            - "funding_comparison": Funding type vs delay rate bar chart
            - "country_region": Students by region pie chart
    """
    db = SyncSessionLocal()
    try:
        if chart_type == "status_pie":
            data = db.execute(text("""
                SELECT final_status, COUNT(*) as count
                FROM graduation_outcome
                GROUP BY final_status
            """)).fetchall()
            chart_data = {
                "type": "pie",
                "title": "Graduation Status Distribution",
                "data": [{"name": r[0], "value": r[1]} for r in data]
            }

        elif chart_type == "faculty_bar":
            data = db.execute(text("""
                SELECT f.faculty_description, COUNT(*) as count
                FROM student s
                JOIN program p ON s.program_id = p.program_id
                JOIN faculty f ON p.faculty_id = f.faculty_id
                GROUP BY f.faculty_id, f.faculty_description
                ORDER BY count DESC
            """)).fetchall()
            chart_data = {
                "type": "bar",
                "title": "Students by Faculty",
                "categories": [r[0] for r in data],
                "values": [r[1] for r in data]
            }

        elif chart_type == "milestone_bar":
            data = db.execute(text("""
                SELECT m.milestone_name,
                    SUM(CASE WHEN sm.status = 'Completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN sm.status = 'Pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN sm.status = 'Overdue' THEN 1 ELSE 0 END) as overdue
                FROM student_milestone sm
                JOIN milestone m ON sm.milestone_id = m.milestone_id
                GROUP BY m.milestone_id, m.milestone_name
                ORDER BY m.milestone_order
            """)).fetchall()
            chart_data = {
                "type": "stacked_bar",
                "title": "Milestone Completion Status",
                "categories": [r[0] for r in data],
                "series": [
                    {"name": "Completed", "data": [r[1] for r in data]},
                    {"name": "Pending", "data": [r[2] for r in data]},
                    {"name": "Overdue", "data": [r[3] for r in data]},
                ]
            }

        elif chart_type == "monthly_trend":
            data = db.execute(text("""
                SELECT DATE_FORMAT(enrollment_date, '%Y-%m') as month, COUNT(*) as count
                FROM student
                GROUP BY month
                ORDER BY month
            """)).fetchall()
            chart_data = {
                "type": "line",
                "title": "Monthly Enrollment Trend",
                "categories": [r[0] for r in data],
                "values": [r[1] for r in data]
            }

        elif chart_type == "funding_comparison":
            data = db.execute(text("""
                SELECT ft.funding_name,
                    COUNT(*) as total,
                    SUM(CASE WHEN go.is_delayed = 1 THEN 1 ELSE 0 END) as delayed
                FROM student s
                JOIN funding_type ft ON s.funding_id = ft.funding_id
                LEFT JOIN graduation_outcome go ON s.student_id = go.student_id
                GROUP BY ft.funding_id, ft.funding_name
            """)).fetchall()
            chart_data = {
                "type": "bar",
                "title": "Funding Type vs Delay Rate",
                "categories": [r[0] for r in data],
                "values": [round(r[2]/r[1]*100, 1) if r[1] > 0 else 0 for r in data]
            }

        elif chart_type == "country_region":
            data = db.execute(text("""
                SELECT cr.region_name, COUNT(*) as count
                FROM student s
                JOIN country c ON s.country_id = c.country_id
                JOIN country_region cr ON c.region_id = cr.region_id
                GROUP BY cr.region_id, cr.region_name
                ORDER BY count DESC
            """)).fetchall()
            chart_data = {
                "type": "pie",
                "title": "Students by Region",
                "data": [{"name": r[0], "value": r[1]} for r in data]
            }

        else:
            return f"Unknown chart type: {chart_type}. Available: status_pie, faculty_bar, milestone_bar, monthly_trend, funding_comparison, country_region"

        return json.dumps(chart_data, ensure_ascii=False)
    finally:
        db.close()


@tool
def custom_sql_query(sql: str) -> str:
    """
    Execute a custom SQL SELECT query against the database and return results.
    Only SELECT queries are allowed - no INSERT, UPDATE, DELETE, or DROP.

    Args:
        sql: A valid SQL SELECT query string to execute, e.g.,
            "SELECT faculty_description, COUNT(*) FROM student s JOIN program p ON s.program_id=p.program_id JOIN faculty f ON p.faculty_id=f.faculty_id GROUP BY f.faculty_id"
    """
    sql_stripped = sql.strip().upper()
    if not sql_stripped.startswith("SELECT"):
        return "Error: Only SELECT queries are allowed."

    db = SyncSessionLocal()
    try:
        result = db.execute(text(sql)).fetchall()
        if not result:
            return "Query returned no results."
        # Format results as a readable table
        columns = db.execute(text(sql)).keys() if hasattr(db.execute(text(sql)), 'keys') else []
        rows = [str(dict(zip(row._fields, row))) if hasattr(row, '_fields') else str(tuple(row)) for row in result]
        return sanitize_tool_output(f"Results ({len(result)} rows):\n" + "\n".join(rows))
    except Exception as e:
        return f"SQL Error: {str(e)}"
    finally:
        db.close()
