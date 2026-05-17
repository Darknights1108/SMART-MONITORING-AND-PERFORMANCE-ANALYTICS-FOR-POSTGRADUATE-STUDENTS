"""
Analytics API — comprehensive dataset for the frontend analytics dashboard.

  GET /api/analytics/data        — enriched student rows for client-side charts
  GET /api/analytics/milestones  — milestone status matrix (student × milestone)
"""
import json
from fastapi import APIRouter, Depends
from sqlalchemy import text
from app.database import SyncSessionLocal
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _scope_filter(user: dict) -> tuple[str, dict]:
    """Return (WHERE fragment, params) scoped to the user's access."""
    if user.get("role") in ("Admin", "Both"):
        return "", {}
    return (
        " AND s.student_id IN (SELECT student_id FROM student_supervisor WHERE supervisor_id = :sup_id)",
        {"sup_id": int(user["sub"])},
    )


@router.get("/data")
def analytics_data(user: dict = Depends(get_current_user)):
    """
    Returns one row per student with all attributes needed to build every
    analytics chart client-side: demographics, risk, PPM, RPD delay, faculty.
    Respects role-based access (lecturers see only their students).
    """
    scope, params = _scope_filter(user)
    db = SyncSessionLocal()
    try:
        rows = db.execute(text(f"""
            SELECT
                s.student_id,
                s.student_name,
                s.student_id_number,
                s.degree_type,
                s.study_method,
                s.gender,
                YEAR(s.enrollment_date)   AS enrollment_year,
                s.is_cross_discipline,
                s.in_research_group,
                s.weekly_work_hours,
                s.has_external_work,
                s.family_support,
                s.entry_gpa,
                pr.program_short_desc     AS program,
                f.faculty_description     AS faculty,
                c.country_name            AS country,
                ft.funding_name           AS funding,
                sup.supervisor_id         AS supervisor_id,
                sup.name                  AS supervisor_name,
                rp.risk_score,
                rp.risk_label,
                rp.key_risk_factors,
                -- RPD delay in days
                CASE
                    WHEN sm.actual_date IS NOT NULL
                        THEN DATEDIFF(sm.actual_date, sm.expected_date)
                    WHEN sm.expected_date IS NOT NULL
                        THEN DATEDIFF(CURDATE(), sm.expected_date)
                    ELSE 0
                END AS rpd_delay_days,
                COALESCE(ppm.cumulative_us, 0) AS ppm_us_count,
                COALESCE(ppm.total_ppm,    0) AS ppm_total,
                ppm.ppm_status
            FROM student s
            JOIN  program pr ON s.program_id    = pr.program_id
            JOIN  faculty  f ON pr.faculty_id   = f.faculty_id
            LEFT JOIN country      c   ON s.country_id  = c.country_id
            LEFT JOIN funding_type ft  ON s.funding_id  = ft.funding_id
            LEFT JOIN student_risk_prediction rp ON s.student_id = rp.student_id
            LEFT JOIN student_milestone sm
                   ON s.student_id = sm.student_id AND sm.milestone_id = 1
            LEFT JOIN v_ppm_us_count ppm ON s.student_id = ppm.student_id
            LEFT JOIN student_supervisor ss2
                   ON s.student_id = ss2.student_id AND ss2.role = 'Main'
            LEFT JOIN supervisor sup ON ss2.supervisor_id = sup.supervisor_id
            WHERE 1=1 {scope}
            ORDER BY s.student_name
        """), params).fetchall()

        students = []
        for r in rows:
            factors = json.loads(r.key_risk_factors or "[]") if r.key_risk_factors else []
            students.append({
                "student_id":        r.student_id,
                "student_name":      r.student_name,
                "student_id_number": r.student_id_number,
                "degree_type":       r.degree_type,
                "study_method":      r.study_method,
                "gender":            r.gender,
                "enrollment_year":   r.enrollment_year,
                "is_cross_discipline": bool(r.is_cross_discipline),
                "in_research_group":   bool(r.in_research_group),
                "weekly_work_hours":   float(r.weekly_work_hours or 0),
                "has_external_work":   bool(r.has_external_work),
                "family_support":      r.family_support,
                "entry_gpa":          float(r.entry_gpa) if r.entry_gpa else None,
                "program":            r.program,
                "faculty":            r.faculty,
                "country":            r.country,
                "funding":            r.funding,
                "risk_score":         float(r.risk_score) if r.risk_score is not None else None,
                "risk_label":         r.risk_label,
                "key_risk_factors":   factors,
                "rpd_delay_days":     int(r.rpd_delay_days or 0),
                "ppm_us_count":       int(r.ppm_us_count or 0),
                "ppm_total":          int(r.ppm_total or 0),
                "ppm_status":         r.ppm_status,
                "supervisor_id":      r.supervisor_id,
                "supervisor_name":    r.supervisor_name,
            })

        return {"students": students, "total": len(students)}
    finally:
        db.close()


@router.get("/milestones")
def milestone_matrix(user: dict = Depends(get_current_user)):
    """
    Returns milestone status for every student.
    Used for the milestone completion heatmap / stacked bar.
    """
    scope, params = _scope_filter(user)
    db = SyncSessionLocal()
    try:
        rows = db.execute(text(f"""
            SELECT
                s.student_id,
                s.student_name,
                m.milestone_name,
                m.milestone_order,
                sm.status,
                sm.expected_date,
                sm.actual_date
            FROM student_milestone sm
            JOIN student s   ON sm.student_id   = s.student_id
            JOIN milestone m ON sm.milestone_id = m.milestone_id
            WHERE 1=1 {scope.replace('s.student_id', 'sm.student_id')}
            ORDER BY m.milestone_order, s.student_name
        """), params).fetchall()

        return [
            {
                "student_id":    r.student_id,
                "student_name":  r.student_name,
                "milestone":     r.milestone_name,
                "order":         r.milestone_order,
                "status":        r.status,
                "expected_date": str(r.expected_date) if r.expected_date else None,
                "actual_date":   str(r.actual_date)   if r.actual_date   else None,
            }
            for r in rows
        ]
    finally:
        db.close()
