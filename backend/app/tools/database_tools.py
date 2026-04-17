"""
Smolagents tools for database queries.
These are the tools the AI agent can call to interact with student data.
"""
from smolagents import tool
from sqlalchemy import text
from app.database import SyncSessionLocal
from app.tools.sanitizer import sanitize_tool_output


@tool
def list_all_students(degree_type: str = "", status: str = "") -> str:
    """
    List all students in the system with basic information.
    Can optionally filter by degree type or graduation status.

    Args:
        degree_type: Optional filter - "PhD", "Master", or "" for all.
        status: Optional filter - "Ongoing", "Graduated On-time", "Graduated Delayed", "Dropped Out", or "" for all.
    """
    db = SyncSessionLocal()
    try:
        conditions = []
        params: dict = {}
        if degree_type:
            conditions.append("s.degree_type = :degree_type")
            params["degree_type"] = degree_type
        if status:
            conditions.append("go.final_status = :status")
            params["status"] = status

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        result = db.execute(text(f"""
            SELECT
                s.student_id_number, s.student_name, s.degree_type,
                s.study_method, p.program_short_desc,
                f.faculty_description, go.final_status, go.expected_end_date
            FROM student s
            LEFT JOIN program p ON s.program_id = p.program_id
            LEFT JOIN faculty f ON p.faculty_id = f.faculty_id
            LEFT JOIN graduation_outcome go ON s.student_id = go.student_id
            {where_clause}
            ORDER BY s.enrollment_date DESC
        """), params).fetchall()

        if not result:
            return "No students found."

        label = f"All students"
        if degree_type:
            label += f" ({degree_type})"
        if status:
            label += f" — status: {status}"

        output = [f"{label}: {len(result)} total\n"]
        for row in result:
            output.append(
                f"  {row[0]} | {row[1]} | {row[2]} {row[3]} | "
                f"{row[4]} | {row[5]} | Status: {row[6] or 'N/A'} | "
                f"Expected End: {row[7] or 'N/A'}"
            )
        return sanitize_tool_output("\n".join(output))
    finally:
        db.close()


@tool
def query_student(search_term: str) -> str:
    """
    Search for a student by name or student ID number.
    Returns student details including program, supervisor, and milestone status.

    Args:
        search_term: Student name or student ID number to search for.
    """
    db = SyncSessionLocal()
    try:
        result = db.execute(text("""
            SELECT
                s.student_id_number, s.student_name, s.email, s.gender,
                s.degree_type, s.study_method, s.enrollment_date,
                p.program_short_desc, f.faculty_description,
                d.discipline_name, ft.funding_name,
                c.country_name,
                go.expected_end_date, go.final_status
            FROM student s
            LEFT JOIN program p ON s.program_id = p.program_id
            LEFT JOIN faculty f ON p.faculty_id = f.faculty_id
            LEFT JOIN discipline d ON s.discipline_id = d.discipline_id
            LEFT JOIN funding_type ft ON s.funding_id = ft.funding_id
            LEFT JOIN country c ON s.country_id = c.country_id
            LEFT JOIN graduation_outcome go ON s.student_id = go.student_id
            WHERE s.student_name LIKE :term OR s.student_id_number LIKE :term
        """), {"term": f"%{search_term}%"}).fetchall()

        if not result:
            return f"No student found matching '{search_term}'."

        output = []
        for row in result:
            supervisors = db.execute(text("""
                SELECT sup.name, ss.role
                FROM student_supervisor ss
                JOIN supervisor sup ON ss.supervisor_id = sup.supervisor_id
                JOIN student s ON ss.student_id = s.student_id
                WHERE s.student_id_number = :sid
            """), {"sid": row[0]}).fetchall()

            sup_str = ", ".join([f"{s[0]} ({s[1]})" for s in supervisors]) if supervisors else "Not assigned"

            output.append(
                f"Student ID: {row[0]}\n"
                f"Name: {row[1]}\n"
                f"Email: {row[2]}\n"
                f"Gender: {row[3]}\n"
                f"Degree: {row[4]} ({row[5]})\n"
                f"Program: {row[7]}\n"
                f"Faculty: {row[8]}\n"
                f"Discipline: {row[9]}\n"
                f"Funding: {row[10]}\n"
                f"Country: {row[11]}\n"
                f"Enrolled: {row[6]}\n"
                f"Expected End: {row[12]}\n"
                f"Status: {row[13]}\n"
                f"Supervisors: {sup_str}\n"
            )
        return sanitize_tool_output("\n---\n".join(output))
    finally:
        db.close()


@tool
def get_student_milestones(search_term: str) -> str:
    """
    Get all milestone progress for a student.
    Shows expected dates, actual dates, and status for each milestone.

    Args:
        search_term: Student name or student ID number.
    """
    db = SyncSessionLocal()
    try:
        result = db.execute(text("""
            SELECT
                s.student_name, s.student_id_number,
                m.milestone_name, sm.expected_date, sm.actual_date,
                sm.status, sm.remarks,
                DATEDIFF(sm.expected_date, CURDATE()) AS days_left
            FROM student_milestone sm
            JOIN student s ON sm.student_id = s.student_id
            JOIN milestone m ON sm.milestone_id = m.milestone_id
            WHERE s.student_name LIKE :term OR s.student_id_number LIKE :term
            ORDER BY m.milestone_order
        """), {"term": f"%{search_term}%"}).fetchall()

        if not result:
            return f"No milestone data found for '{search_term}'."

        student_name = result[0][0]
        student_id = result[0][1]
        output = [f"Milestones for {student_name} ({student_id}):\n"]

        for row in result:
            status_icon = {"Completed": "Done", "Pending": "Pending", "Overdue": "OVERDUE"}
            days_info = ""
            if row[5] == "Pending" and row[7] is not None:
                if row[7] > 0:
                    days_info = f" ({row[7]} days remaining)"
                elif row[7] == 0:
                    days_info = " (DUE TODAY)"
                else:
                    days_info = f" ({abs(row[7])} days overdue)"

            output.append(
                f"  [{status_icon.get(row[5], row[5])}] {row[2]}\n"
                f"    Expected: {row[3]} | Actual: {row[4] or 'N/A'}{days_info}\n"
                f"    {f'Remarks: {row[6]}' if row[6] else ''}"
            )
        return sanitize_tool_output("\n".join(output))
    finally:
        db.close()


@tool
def list_upcoming_deadlines(days: int) -> str:
    """
    List all students with milestone deadlines within the next N days.
    Useful for getting an overview of upcoming deadlines.

    Args:
        days: Number of days to look ahead (e.g., 7, 15, 30).
    """
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

        if not result:
            return f"No pending deadlines within the next {days} days."

        output = [f"Upcoming deadlines (next {days} days): {len(result)} found\n"]
        for row in result:
            output.append(
                f"  {row[1]} ({row[0]}) - {row[3]}\n"
                f"    Due: {row[4]} ({row[5]} days left)\n"
                f"    Supervisor: {row[6] or 'Not assigned'}\n"
            )
        return sanitize_tool_output("\n".join(output))
    finally:
        db.close()


@tool
def list_overdue_students() -> str:
    """
    List all students who have overdue milestones.
    Returns students whose milestone expected_date has passed but status is not Completed.
    """
    db = SyncSessionLocal()
    try:
        result = db.execute(text("""
            SELECT
                s.student_id_number, s.student_name, s.email,
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

        if not result:
            return "No overdue milestones found."

        output = [f"Overdue milestones: {len(result)} found\n"]
        for row in result:
            output.append(
                f"  {row[1]} ({row[0]}) - {row[3]}\n"
                f"    Was due: {row[4]} ({row[5]} days overdue)\n"
                f"    Supervisor: {row[6] or 'Not assigned'}\n"
            )
        return sanitize_tool_output("\n".join(output))
    finally:
        db.close()


@tool
def get_ppm_status(search_term: str) -> str:
    """
    Get PPM (Postgraduate Progress Monitoring) records for a student.
    Shows all PPM results and cumulative unsatisfactory count.

    Args:
        search_term: Student name or student ID number.
    """
    db = SyncSessionLocal()
    try:
        records = db.execute(text("""
            SELECT
                s.student_name, s.student_id_number,
                pr.ppm_year, pr.ppm_cycle, pr.result,
                pr.verify_status, pr.verified_by_name, pr.remarks
            FROM ppm_record pr
            JOIN student s ON pr.student_id = s.student_id
            WHERE s.student_name LIKE :term OR s.student_id_number LIKE :term
            ORDER BY pr.ppm_year, pr.ppm_cycle
        """), {"term": f"%{search_term}%"}).fetchall()

        if not records:
            return f"No PPM records found for '{search_term}'."

        student_name = records[0][0]
        student_id = records[0][1]

        # Get cumulative status
        status = db.execute(text("""
            SELECT cumulative_us, ppm_status
            FROM v_ppm_us_count v
            JOIN student s ON v.student_id = s.student_id
            WHERE s.student_name LIKE :term OR s.student_id_number LIKE :term
        """), {"term": f"%{search_term}%"}).fetchone()

        output = [f"PPM Records for {student_name} ({student_id}):"]
        if status:
            output.append(f"Overall Status: {status[1]} (Cumulative US: {status[0]})\n")

        for r in records:
            cycle_name = "First Half" if r[3] == 1 else "Second Half"
            output.append(
                f"  {r[2]} {cycle_name}: {r[4] or 'Pending'}"
                f" | Verified: {r[5]} by {r[6] or 'N/A'}"
                f"{f' | Note: {r[7]}' if r[7] else ''}"
            )
        return sanitize_tool_output("\n".join(output))
    finally:
        db.close()


@tool
def get_students_by_supervisor(supervisor_name: str) -> str:
    """
    Get all students supervised by a specific supervisor.
    Shows student details and their current milestone status.

    Args:
        supervisor_name: Name of the supervisor to search for.
    """
    db = SyncSessionLocal()
    try:
        result = db.execute(text("""
            SELECT
                s.student_id_number, s.student_name, s.degree_type,
                s.study_method, ss.role AS sup_role,
                go.final_status, go.expected_end_date
            FROM student_supervisor ss
            JOIN supervisor sup ON ss.supervisor_id = sup.supervisor_id
            JOIN student s ON ss.student_id = s.student_id
            LEFT JOIN graduation_outcome go ON s.student_id = go.student_id
            WHERE sup.name LIKE :name
            ORDER BY s.enrollment_date
        """), {"name": f"%{supervisor_name}%"}).fetchall()

        if not result:
            return f"No students found for supervisor '{supervisor_name}'."

        output = [f"Students supervised by '{supervisor_name}': {len(result)} found\n"]
        for row in result:
            output.append(
                f"  {row[1]} ({row[0]}) - {row[2]} {row[3]}\n"
                f"    Role: {row[4]} Supervisor | Status: {row[5] or 'N/A'}\n"
                f"    Expected End: {row[6] or 'N/A'}\n"
            )
        return sanitize_tool_output("\n".join(output))
    finally:
        db.close()


@tool
def get_analytics_summary() -> str:
    """
    Get a high-level summary of all students for dashboard overview.
    Includes total counts, status breakdown, overdue counts, and at-risk students.
    """
    db = SyncSessionLocal()
    try:
        # Total students
        total = db.execute(text("SELECT COUNT(*) FROM student")).scalar()

        # Status breakdown
        status_breakdown = db.execute(text("""
            SELECT final_status, COUNT(*) as cnt
            FROM graduation_outcome
            GROUP BY final_status
        """)).fetchall()

        # Overdue milestones count
        overdue_count = db.execute(text("""
            SELECT COUNT(DISTINCT student_id) FROM student_milestone
            WHERE status = 'Overdue'
            OR (expected_date < CURDATE() AND status = 'Pending')
        """)).scalar()

        # PPM at risk
        at_risk = db.execute(text("""
            SELECT COUNT(*) FROM v_ppm_us_count WHERE ppm_status = 'AT RISK'
        """)).scalar()

        terminated = db.execute(text("""
            SELECT COUNT(*) FROM v_ppm_us_count WHERE ppm_status = 'TERMINATED'
        """)).scalar()

        # Upcoming deadlines (next 30 days)
        upcoming = db.execute(text("""
            SELECT COUNT(DISTINCT student_id) FROM student_milestone
            WHERE status = 'Pending'
            AND expected_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)
        """)).scalar()

        # Degree breakdown
        degree_breakdown = db.execute(text("""
            SELECT degree_type, COUNT(*) FROM student GROUP BY degree_type
        """)).fetchall()

        output = [
            f"=== Student Analytics Summary ===\n",
            f"Total Students: {total}",
            f"Degree Breakdown: {', '.join([f'{r[0]}: {r[1]}' for r in degree_breakdown])}",
            f"\nGraduation Status:",
        ]
        for s in status_breakdown:
            output.append(f"  {s[0]}: {s[1]}")

        output.extend([
            f"\nAlerts:",
            f"  Overdue milestones: {overdue_count} students",
            f"  PPM At Risk: {at_risk} students",
            f"  PPM Terminated: {terminated} students",
            f"  Upcoming deadlines (30 days): {upcoming} students",
        ])

        return sanitize_tool_output("\n".join(output))
    finally:
        db.close()
