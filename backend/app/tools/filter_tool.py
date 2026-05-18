from smolagents import tool
from sqlalchemy import text
from app.database import SyncSessionLocal
import json


@tool
def filter_students(criteria: str) -> str:
    """
    Find students matching complex, multi-field filter criteria.
    Returns a formatted list of matching students.

    Args:
        criteria: JSON string with one or more filter keys. Supported keys:
            - risk_label: "High" | "Medium" | "Low"
            - is_part_time: true/false
            - degree_type: "PhD" | "Masters"
            - ppm_unsatisfactory: true — has cumulative_us >= 1
            - rpd_overdue: true — RPD milestone past expected_date with no actual_date
            - rpd_due_30d: true — RPD due within 30 days
            - pub_deficit: true — accepted publications < required
            - has_external_work: true/false
            - is_cross_discipline: true/false
            - supervisor_name: string — supervisor name LIKE match
            - months_enrolled_min: int — enrolled for at least N months
            - months_enrolled_max: int — enrolled for at most N months
    """
    try:
        filters: dict = json.loads(criteria)
    except json.JSONDecodeError:
        return f"Invalid JSON for criteria: {criteria}"

    if not filters:
        return "No filter criteria provided."

    joins: list[str] = []
    wheres: list[str] = []
    params: dict = {}

    added_joins: set[str] = set()

    def add_join(alias: str, clause: str):
        if alias not in added_joins:
            joins.append(clause)
            added_joins.add(alias)

    if "risk_label" in filters:
        add_join("rp", "LEFT JOIN student_risk_prediction rp ON s.student_id = rp.student_id")
        wheres.append("rp.risk_label = :risk_label")
        params["risk_label"] = filters["risk_label"]

    if "is_part_time" in filters:
        wheres.append("s.is_part_time = :is_part_time")
        params["is_part_time"] = 1 if filters["is_part_time"] else 0

    if "degree_type" in filters:
        wheres.append("s.degree_type = :degree_type")
        params["degree_type"] = filters["degree_type"]

    if filters.get("ppm_unsatisfactory"):
        add_join("ppm_us", "LEFT JOIN v_ppm_us_count ppm_us ON s.student_id = ppm_us.student_id")
        wheres.append("ppm_us.cumulative_us >= 1")

    if filters.get("rpd_overdue"):
        add_join("sm_rpd_ov", """
            LEFT JOIN (
                SELECT sm.student_id FROM student_milestone sm
                JOIN milestone m ON sm.milestone_id = m.milestone_id
                WHERE m.milestone_name LIKE '%RPD%'
                  AND sm.actual_date IS NULL AND sm.expected_date < CURDATE()
            ) rpd_ov ON s.student_id = rpd_ov.student_id
        """)
        wheres.append("rpd_ov.student_id IS NOT NULL")

    if filters.get("rpd_due_30d"):
        add_join("sm_rpd_30", """
            LEFT JOIN (
                SELECT sm.student_id FROM student_milestone sm
                JOIN milestone m ON sm.milestone_id = m.milestone_id
                WHERE m.milestone_name LIKE '%RPD%'
                  AND sm.actual_date IS NULL
                  AND sm.expected_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)
            ) rpd_30 ON s.student_id = rpd_30.student_id
        """)
        wheres.append("rpd_30.student_id IS NOT NULL")

    if filters.get("pub_deficit"):
        add_join("pub_def", """
            LEFT JOIN (
                SELECT student_id FROM publication_requirement
                WHERE accepted_count < required_count
            ) pub_def ON s.student_id = pub_def.student_id
        """)
        wheres.append("pub_def.student_id IS NOT NULL")

    if "has_external_work" in filters:
        wheres.append("s.has_external_work = :has_external_work")
        params["has_external_work"] = 1 if filters["has_external_work"] else 0

    if "is_cross_discipline" in filters:
        wheres.append("s.is_cross_discipline = :is_cross_discipline")
        params["is_cross_discipline"] = 1 if filters["is_cross_discipline"] else 0

    if "supervisor_name" in filters:
        add_join("sv", "LEFT JOIN supervisor sv ON s.main_supervisor_id = sv.supervisor_id")
        wheres.append("sv.name LIKE :supervisor_name")
        params["supervisor_name"] = f"%{filters['supervisor_name']}%"

    if "months_enrolled_min" in filters:
        wheres.append("TIMESTAMPDIFF(MONTH, s.commencement_date, CURDATE()) >= :months_min")
        params["months_min"] = int(filters["months_enrolled_min"])

    if "months_enrolled_max" in filters:
        wheres.append("TIMESTAMPDIFF(MONTH, s.commencement_date, CURDATE()) <= :months_max")
        params["months_max"] = int(filters["months_enrolled_max"])

    if not wheres:
        return "No recognised filter keys in criteria."

    select_cols = (
        "s.student_id, s.student_name, s.student_id_number, "
        "COALESCE(s.degree_type, '') AS degree_type, "
        "COALESCE(rp2.risk_label, 'N/A') AS risk_label, "
        "s.is_part_time, s.has_external_work, s.is_cross_discipline"
    )

    extra_joins = (
        "LEFT JOIN student_risk_prediction rp2 ON s.student_id = rp2.student_id"
    )

    join_str = " ".join(joins)
    where_str = " AND ".join(wheres)

    sql = f"""
        SELECT DISTINCT {select_cols}
        FROM student s
        {join_str}
        {extra_joins}
        WHERE {where_str}
        ORDER BY s.student_name
        LIMIT 100
    """

    db = SyncSessionLocal()
    try:
        rows = db.execute(text(sql), params).fetchall()
    finally:
        db.close()

    if not rows:
        return f"No students found matching the given criteria: {criteria}"

    lines = [f"Found {len(rows)} student(s) matching criteria:\n"]
    for sid, name, id_num, degree, risk, part_time, ext_work, cross_disc in rows:
        flags = []
        if part_time:
            flags.append("Part-time")
        if ext_work:
            flags.append("External work")
        if cross_disc:
            flags.append("Cross-discipline")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        lines.append(f"  • {name} ({id_num}) | {degree} | Risk: {risk}{flag_str}")

    return "\n".join(lines)
