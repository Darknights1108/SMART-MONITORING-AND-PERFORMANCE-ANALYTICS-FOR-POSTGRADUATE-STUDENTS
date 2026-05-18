"""
Students API — role-aware student and supervisor endpoints.

  GET  /api/students/                  — list (admin=all, lecturer=own)
  GET  /api/students/{student_id}      — full student detail
  POST /api/students/                  — create student (admin only)
  GET  /api/supervisors/               — all supervisors (admin only)
  POST /api/supervisors/               — create supervisor/lecturer (admin only)
  GET  /api/lookups/programs           — program list for dropdowns
  GET  /api/lookups/faculties          — faculty list
  GET  /api/lookups/countries          — country list
  GET  /api/lookups/disciplines        — discipline list
  GET  /api/lookups/funding-types      — funding type list
  GET  /api/lookups/campuses           — campus list
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import date
from sqlalchemy import text
from app.database import SyncSessionLocal
from app.services.auth_service import get_current_user, require_admin
from passlib.context import CryptContext
import json
import math

router = APIRouter(tags=["students"])
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Helpers ────────────────────────────────────────────────────────────────────

def _is_admin(user: dict) -> bool:
    return user.get("role") in ("Admin", "Both")


def _supervisor_id(user: dict) -> int:
    return int(user["sub"])


# ── Student list ───────────────────────────────────────────────────────────────

@router.get("/api/students/")
def list_students(user: dict = Depends(get_current_user)):
    """
    Admin / Both  → all students.
    Supervisor    → only students linked to them in student_supervisor.
    """
    db = SyncSessionLocal()
    try:
        if _is_admin(user):
            where = ""
            params: dict = {}
        else:
            where = """
                AND s.student_id IN (
                    SELECT student_id FROM student_supervisor
                    WHERE supervisor_id = :sup_id
                )
            """
            params = {"sup_id": _supervisor_id(user)}

        rows = db.execute(text(f"""
            SELECT
                s.student_id,
                s.student_id_number,
                s.student_name,
                s.email,
                s.degree_type,
                s.study_method,
                s.enrollment_date,
                pr.program_short_desc,
                f.faculty_description,
                rp.risk_score,
                rp.risk_label,
                rp.predicted_at,
                sup.name      AS supervisor_name,
                sup.staff_id  AS supervisor_staff_id
            FROM student s
            JOIN program pr ON s.program_id = pr.program_id
            JOIN faculty f  ON pr.faculty_id = f.faculty_id
            LEFT JOIN student_risk_prediction rp ON s.student_id = rp.student_id
            LEFT JOIN student_supervisor ss ON s.student_id = ss.student_id AND ss.role = 'Main'
            LEFT JOIN supervisor sup ON ss.supervisor_id = sup.supervisor_id
            WHERE 1=1 {where}
            ORDER BY s.student_name ASC
        """), params).fetchall()

        return [
            {
                "student_id":           r.student_id,
                "student_id_number":    r.student_id_number,
                "student_name":         r.student_name,
                "email":                r.email,
                "degree_type":          r.degree_type,
                "study_method":         r.study_method,
                "enrollment_date":      str(r.enrollment_date) if r.enrollment_date else None,
                "program":              r.program_short_desc,
                "faculty":              r.faculty_description,
                "risk_score":           float(r.risk_score) if r.risk_score is not None else None,
                "risk_label":           r.risk_label,
                "predicted_at":         str(r.predicted_at) if r.predicted_at else None,
                "supervisor_name":      r.supervisor_name,
                "supervisor_staff_id":  r.supervisor_staff_id,
            }
            for r in rows
        ]
    finally:
        db.close()


# ── Student detail ─────────────────────────────────────────────────────────────

@router.get("/api/students/{student_id}")
def get_student(student_id: int, user: dict = Depends(get_current_user)):
    """
    Return full student detail: profile + milestones + PPM + risk.
    Lecturers can only view students they supervise.
    """
    db = SyncSessionLocal()
    try:
        # ── access check for non-admins ──
        if not _is_admin(user):
            allowed = db.execute(text("""
                SELECT 1 FROM student_supervisor
                WHERE student_id = :sid AND supervisor_id = :sup_id
                LIMIT 1
            """), {"sid": student_id, "sup_id": _supervisor_id(user)}).fetchone()
            if not allowed:
                raise HTTPException(status_code=403, detail="You do not supervise this student.")

        # ── base profile ──
        s = db.execute(text("""
            SELECT
                s.student_id, s.student_id_number, s.student_name, s.email,
                s.degree_type, s.study_method, s.enrollment_date,
                s.has_external_work, s.weekly_work_hours,
                s.is_cross_discipline, s.in_research_group, s.family_support,
                s.entry_gpa, s.gender,
                pr.program_short_desc, pr.program_description,
                f.faculty_description,
                ft.funding_name,
                c.country_name,
                d.discipline_name,
                ca.campus_name
            FROM student s
            JOIN program pr ON s.program_id = pr.program_id
            JOIN faculty f  ON pr.faculty_id = f.faculty_id
            LEFT JOIN funding_type ft ON s.funding_id    = ft.funding_id
            LEFT JOIN country c       ON s.country_id    = c.country_id
            LEFT JOIN discipline d    ON s.discipline_id = d.discipline_id
            LEFT JOIN campus ca       ON s.campus_id     = ca.campus_id
            WHERE s.student_id = :sid
        """), {"sid": student_id}).fetchone()

        if not s:
            raise HTTPException(status_code=404, detail="Student not found.")

        # ── supervisors ──
        supervisors = db.execute(text("""
            SELECT sup.supervisor_id, sup.staff_id, sup.name, sup.email, ss.role
            FROM student_supervisor ss
            JOIN supervisor sup ON ss.supervisor_id = sup.supervisor_id
            WHERE ss.student_id = :sid
        """), {"sid": student_id}).fetchall()

        # ── milestones ──
        milestones = db.execute(text("""
            SELECT m.milestone_name, m.milestone_order,
                   sm.expected_date, sm.actual_date, sm.status, sm.remarks
            FROM student_milestone sm
            JOIN milestone m ON sm.milestone_id = m.milestone_id
            WHERE sm.student_id = :sid
            ORDER BY m.milestone_order ASC
        """), {"sid": student_id}).fetchall()

        # ── PPM records ──
        ppm = db.execute(text("""
            SELECT ppm_year, ppm_cycle, result, verify_status, verify_date, remarks
            FROM ppm_record
            WHERE student_id = :sid
            ORDER BY ppm_year, ppm_cycle
        """), {"sid": student_id}).fetchall()

        # ── risk prediction ──
        risk = db.execute(text("""
            SELECT risk_score, risk_label, cluster_id, key_risk_factors, predicted_at
            FROM student_risk_prediction
            WHERE student_id = :sid
        """), {"sid": student_id}).fetchone()

        return {
            "student_id":       s.student_id,
            "student_id_number": s.student_id_number,
            "student_name":     s.student_name,
            "email":            s.email,
            "gender":           s.gender,
            "degree_type":      s.degree_type,
            "study_method":     s.study_method,
            "enrollment_date":  str(s.enrollment_date) if s.enrollment_date else None,
            "program":          s.program_short_desc,
            "program_full":     s.program_description,
            "faculty":          s.faculty_description,
            "funding":          s.funding_name,
            "country":          s.country_name,
            "discipline":       s.discipline_name,
            "campus":           s.campus_name,
            "entry_gpa":        float(s.entry_gpa) if s.entry_gpa else None,
            "has_external_work": bool(s.has_external_work),
            "weekly_work_hours": float(s.weekly_work_hours) if s.weekly_work_hours else 0,
            "is_cross_discipline": bool(s.is_cross_discipline),
            "in_research_group":   bool(s.in_research_group),
            "family_support":      s.family_support,
            "supervisors": [
                {
                    "supervisor_id": r.supervisor_id,
                    "staff_id": r.staff_id,
                    "name": r.name,
                    "email": r.email,
                    "role": r.role,
                }
                for r in supervisors
            ],
            "milestones": [
                {
                    "name":          m.milestone_name,
                    "order":         m.milestone_order,
                    "expected_date": str(m.expected_date) if m.expected_date else None,
                    "actual_date":   str(m.actual_date)   if m.actual_date   else None,
                    "status":        m.status,
                    "remarks":       m.remarks,
                }
                for m in milestones
            ],
            "ppm_records": [
                {
                    "year":          p.ppm_year,
                    "cycle":         p.ppm_cycle,
                    "result":        p.result,
                    "verified":      p.verify_status == "Y",
                    "verify_date":   str(p.verify_date) if p.verify_date else None,
                    "remarks":       p.remarks,
                }
                for p in ppm
            ],
            "risk": {
                "risk_score":      float(risk.risk_score) if risk else None,
                "risk_label":      risk.risk_label if risk else None,
                "cluster_id":      risk.cluster_id if risk else None,
                "key_risk_factors": json.loads(risk.key_risk_factors or "[]") if risk else [],
                "predicted_at":    str(risk.predicted_at) if risk and risk.predicted_at else None,
            } if risk else None,
        }
    finally:
        db.close()


# ── Supervisor list (admin only) ───────────────────────────────────────────────

@router.get("/api/supervisors/")
def list_supervisors(user: dict = Depends(require_admin)):
    """Return all supervisors with student counts. Admin only."""
    db = SyncSessionLocal()
    try:
        rows = db.execute(text("""
            SELECT
                sup.supervisor_id,
                sup.staff_id,
                sup.name,
                sup.email,
                sup.role,
                sup.faculty_id,
                f.faculty_description,
                sup.is_active,
                sup.max_students,
                COUNT(DISTINCT ss.student_id) AS student_count
            FROM supervisor sup
            LEFT JOIN faculty f ON sup.faculty_id = f.faculty_id
            LEFT JOIN student_supervisor ss ON sup.supervisor_id = ss.supervisor_id
            GROUP BY sup.supervisor_id, sup.staff_id, sup.name, sup.email,
                     sup.role, sup.faculty_id, f.faculty_description,
                     sup.is_active, sup.max_students
            ORDER BY sup.name ASC
        """)).fetchall()

        return [
            {
                "supervisor_id":  r.supervisor_id,
                "staff_id":       r.staff_id,
                "name":           r.name,
                "email":          r.email,
                "role":           r.role,
                "faculty_id":     r.faculty_id,
                "faculty":        r.faculty_description,
                "is_active":      bool(r.is_active),
                "max_students":   r.max_students,
                "student_count":  int(r.student_count),
            }
            for r in rows
        ]
    finally:
        db.close()


class UpdateSupervisorRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    faculty_id: int | None = None
    role: str | None = None
    is_active: bool | None = None
    max_students: int | None = None   # None = no limit


@router.put("/api/supervisors/{supervisor_id}")
def update_supervisor(
    supervisor_id: int,
    body: UpdateSupervisorRequest,
    user: dict = Depends(require_admin),
):
    """Update supervisor info and/or student cap. Admin only."""
    db = SyncSessionLocal()
    try:
        existing = db.execute(
            text("SELECT supervisor_id FROM supervisor WHERE supervisor_id = :id"),
            {"id": supervisor_id},
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Supervisor not found.")

        fields, params = [], {"id": supervisor_id}
        if body.name is not None:
            fields.append("name = :name");        params["name"] = body.name
        if body.email is not None:
            # Check email uniqueness (exclude self)
            dup = db.execute(text(
                "SELECT 1 FROM supervisor WHERE email = :email AND supervisor_id != :id"
            ), {"email": body.email, "id": supervisor_id}).fetchone()
            if dup:
                raise HTTPException(status_code=409, detail=f"Email '{body.email}' already in use.")
            fields.append("email = :email");      params["email"] = body.email
        if body.faculty_id is not None:
            fields.append("faculty_id = :fid");  params["fid"] = body.faculty_id
        if body.role is not None:
            fields.append("role = :role");        params["role"] = body.role
        if body.is_active is not None:
            fields.append("is_active = :active"); params["active"] = int(body.is_active)
        if body.max_students is not None:
            fields.append("max_students = :ms");  params["ms"] = body.max_students
        else:
            # Explicitly pass None → clear the limit
            if "max_students" in body.model_fields_set:
                fields.append("max_students = NULL")

        if not fields:
            return {"success": True, "message": "Nothing to update."}

        db.execute(
            text(f"UPDATE supervisor SET {', '.join(fields)} WHERE supervisor_id = :id"),
            params,
        )
        db.commit()
        return {"success": True, "message": "Supervisor updated."}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


# ── My summary (lecturer dashboard) ───────────────────────────────────────────

@router.get("/api/dashboard/my-summary")
def my_summary(user: dict = Depends(get_current_user)):
    """
    Summary metrics scoped to the current user's students.
    Admins get global totals; lecturers get their own students' stats.
    """
    db = SyncSessionLocal()
    try:
        if _is_admin(user):
            scope_filter = ""
            params: dict = {}
        else:
            scope_filter = """
                AND s.student_id IN (
                    SELECT student_id FROM student_supervisor WHERE supervisor_id = :sup_id
                )
            """
            params = {"sup_id": _supervisor_id(user)}

        total = db.execute(text(f"""
            SELECT COUNT(*) FROM student s WHERE 1=1 {scope_filter}
        """), params).scalar()

        risk_dist = db.execute(text(f"""
            SELECT rp.risk_label, COUNT(*) AS cnt
            FROM student_risk_prediction rp
            JOIN student s ON rp.student_id = s.student_id
            WHERE 1=1 {scope_filter}
            GROUP BY rp.risk_label
        """), params).fetchall()

        overdue = db.execute(text(f"""
            SELECT COUNT(DISTINCT s.student_id)
            FROM student_milestone sm
            JOIN student s ON sm.student_id = s.student_id
            WHERE (sm.status = 'Overdue'
                   OR (sm.expected_date < CURDATE() AND sm.status = 'Pending'))
            {scope_filter}
        """), params).scalar()

        upcoming_30 = db.execute(text(f"""
            SELECT COUNT(DISTINCT s.student_id)
            FROM student_milestone sm
            JOIN student s ON sm.student_id = s.student_id
            WHERE sm.status = 'Pending'
            AND sm.expected_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)
            {scope_filter}
        """), params).scalar()

        dist = {r.risk_label: int(r.cnt) for r in risk_dist}
        return {
            "total_students":   total,
            "high_risk":        dist.get("High",   0),
            "medium_risk":      dist.get("Medium", 0),
            "low_risk":         dist.get("Low",    0),
            "overdue_students": overdue,
            "upcoming_30_days": upcoming_30,
        }
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# LOOKUP ENDPOINTS — dropdown data for forms
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/api/lookups/programs")
def get_programs(user: dict = Depends(require_admin)):
    db = SyncSessionLocal()
    try:
        rows = db.execute(text("""
            SELECT p.program_id, p.program_short_desc, p.program_description, f.faculty_description
            FROM program p JOIN faculty f ON p.faculty_id = f.faculty_id
            ORDER BY p.program_short_desc
        """)).fetchall()
        return [{"id": r.program_id, "short": r.program_short_desc,
                 "full": r.program_description, "faculty": r.faculty_description} for r in rows]
    finally:
        db.close()


@router.get("/api/lookups/faculties")
def get_faculties(user: dict = Depends(require_admin)):
    db = SyncSessionLocal()
    try:
        rows = db.execute(text("SELECT faculty_id, faculty_description FROM faculty ORDER BY faculty_description")).fetchall()
        return [{"id": r.faculty_id, "name": r.faculty_description} for r in rows]
    finally:
        db.close()


@router.get("/api/lookups/countries")
def get_countries(user: dict = Depends(require_admin)):
    db = SyncSessionLocal()
    try:
        rows = db.execute(text("""
            SELECT c.country_id, c.country_name, cr.region_name
            FROM country c JOIN country_region cr ON c.region_id = cr.region_id
            ORDER BY c.country_name
        """)).fetchall()
        return [{"id": r.country_id, "name": r.country_name, "region": r.region_name} for r in rows]
    finally:
        db.close()


@router.get("/api/lookups/disciplines")
def get_disciplines(user: dict = Depends(require_admin)):
    db = SyncSessionLocal()
    try:
        rows = db.execute(text("SELECT discipline_id, discipline_name, discipline_group FROM discipline ORDER BY discipline_name")).fetchall()
        return [{"id": r.discipline_id, "name": r.discipline_name, "group": r.discipline_group} for r in rows]
    finally:
        db.close()


@router.get("/api/lookups/funding-types")
def get_funding_types(user: dict = Depends(require_admin)):
    db = SyncSessionLocal()
    try:
        rows = db.execute(text("SELECT funding_id, funding_name FROM funding_type ORDER BY funding_name")).fetchall()
        return [{"id": r.funding_id, "name": r.funding_name} for r in rows]
    finally:
        db.close()


@router.get("/api/lookups/campuses")
def get_campuses(user: dict = Depends(require_admin)):
    db = SyncSessionLocal()
    try:
        rows = db.execute(text("SELECT campus_id, campus_name FROM campus ORDER BY campus_name")).fetchall()
        return [{"id": r.campus_id, "name": r.campus_name} for r in rows]
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# CREATE STUDENT
# ══════════════════════════════════════════════════════════════════════════════

class CreateStudentRequest(BaseModel):
    # Required
    student_id_number: str
    student_name: str
    program_id: int
    degree_type: str          # Master | PhD
    study_method: str         # Full-time | Part-time
    enrollment_date: date
    campus_id: int
    # Optional
    email: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    country_id: Optional[int] = None
    marital_status: Optional[str] = None
    num_children: int = 0
    discipline_id: Optional[int] = None
    entry_gpa: Optional[float] = None
    is_cross_discipline: bool = False
    funding_id: Optional[int] = None
    has_external_work: bool = False
    weekly_work_hours: float = 0
    in_research_group: bool = False
    family_support: Optional[int] = None   # 1–5
    # Related
    supervisor_id: Optional[int] = None    # main supervisor


def _milestone_expected_date(enrollment_date: date, months: int) -> date:
    """Add months to enrollment_date."""
    import calendar
    m = enrollment_date.month + months
    y = enrollment_date.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    d = min(enrollment_date.day, calendar.monthrange(y, m)[1])
    return date(y, m, d)


@router.post("/api/students/")
def create_student(body: CreateStudentRequest, user: dict = Depends(require_admin)):
    """Create a new student with auto-generated milestones. Admin only."""
    db = SyncSessionLocal()
    try:
        # Check duplicate matric number
        exists = db.execute(text(
            "SELECT 1 FROM student WHERE student_id_number = :num"
        ), {"num": body.student_id_number}).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail=f"Student ID '{body.student_id_number}' already exists.")

        # Insert student
        result = db.execute(text("""
            INSERT INTO student (
                student_id_number, student_name, email, campus_id,
                gender, date_of_birth, country_id, marital_status, num_children,
                program_id, degree_type, discipline_id, enrollment_date, entry_gpa,
                is_cross_discipline, study_method,
                funding_id, has_external_work, weekly_work_hours,
                in_research_group, family_support
            ) VALUES (
                :num, :name, :email, :campus_id,
                :gender, :dob, :country_id, :marital_status, :num_children,
                :program_id, :degree_type, :discipline_id, :enrollment_date, :entry_gpa,
                :is_cross_discipline, :study_method,
                :funding_id, :has_external_work, :weekly_work_hours,
                :in_research_group, :family_support
            )
        """), {
            "num":               body.student_id_number,
            "name":              body.student_name,
            "email":             body.email,
            "campus_id":         body.campus_id,
            "gender":            body.gender,
            "dob":               body.date_of_birth,
            "country_id":        body.country_id,
            "marital_status":    body.marital_status,
            "num_children":      body.num_children,
            "program_id":        body.program_id,
            "degree_type":       body.degree_type,
            "discipline_id":     body.discipline_id,
            "enrollment_date":   body.enrollment_date,
            "entry_gpa":         body.entry_gpa,
            "is_cross_discipline": body.is_cross_discipline,
            "study_method":      body.study_method,
            "funding_id":        body.funding_id,
            "has_external_work": body.has_external_work,
            "weekly_work_hours": body.weekly_work_hours,
            "in_research_group": body.in_research_group,
            "family_support":    body.family_support,
        })
        student_id = result.lastrowid

        # Auto-generate milestones based on degree + study method
        dt = body.degree_type    # Master | PhD
        sm = body.study_method   # Full-time | Part-time
        en = body.enrollment_date

        # Milestone timeline (months from enrollment)
        # milestone_id: (norm_months, max_months)
        milestone_map = {
            1: {  # RPD
                ("Master", "Full-time"):  (6,  9),
                ("Master", "Part-time"):  (9,  12),
                ("PhD",    "Full-time"):  (9,  12),
                ("PhD",    "Part-time"):  (12, 15),
            },
            3: {  # Publication
                ("Master", "Full-time"):  (15, 15),
                ("Master", "Part-time"):  (15, 15),
                ("PhD",    "Full-time"):  (24, 24),
                ("PhD",    "Part-time"):  (24, 24),
            },
            4: {  # Thesis Seminar
                ("Master", "Full-time"):  (18, 20),
                ("Master", "Part-time"):  (18, 20),
                ("PhD",    "Full-time"):  (30, 32),
                ("PhD",    "Part-time"):  (30, 32),
            },
        }

        for milestone_id, schedule in milestone_map.items():
            months_norm, _ = schedule.get((dt, sm), (18, 24))
            expected = _milestone_expected_date(en, months_norm)
            db.execute(text("""
                INSERT INTO student_milestone (student_id, milestone_id, expected_date, status)
                VALUES (:sid, :mid, :exp, 'Pending')
                ON DUPLICATE KEY UPDATE expected_date = VALUES(expected_date)
            """), {"sid": student_id, "mid": milestone_id, "exp": expected})

        # PPM milestone (no fixed date)
        db.execute(text("""
            INSERT INTO student_milestone (student_id, milestone_id, status)
            VALUES (:sid, 2, 'Pending')
            ON DUPLICATE KEY UPDATE status = status
        """), {"sid": student_id})

        # Assign main supervisor if provided
        if body.supervisor_id:
            db.execute(text("""
                INSERT INTO student_supervisor (student_id, supervisor_id, role, assigned_date)
                VALUES (:sid, :sup, 'Main', CURDATE())
                ON DUPLICATE KEY UPDATE role = role
            """), {"sid": student_id, "sup": body.supervisor_id})

        db.commit()
        return {"success": True, "student_id": student_id, "message": f"Student '{body.student_name}' created successfully."}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# UPDATE STUDENT
# ══════════════════════════════════════════════════════════════════════════════

class UpdateStudentRequest(BaseModel):
    student_name:       Optional[str]   = None
    email:              Optional[str]   = None
    gender:             Optional[str]   = None
    date_of_birth:      Optional[date]  = None
    country_id:         Optional[int]   = None
    marital_status:     Optional[str]   = None
    num_children:       Optional[int]   = None
    program_id:         Optional[int]   = None
    degree_type:        Optional[str]   = None
    study_method:       Optional[str]   = None
    enrollment_date:    Optional[date]  = None
    entry_gpa:          Optional[float] = None
    is_cross_discipline: Optional[bool] = None
    discipline_id:      Optional[int]   = None
    campus_id:          Optional[int]   = None
    funding_id:         Optional[int]   = None
    has_external_work:  Optional[bool]  = None
    weekly_work_hours:  Optional[float] = None
    in_research_group:  Optional[bool]  = None
    family_support:     Optional[int]   = None
    program_status:     Optional[str]   = None


@router.put("/api/students/{student_id}")
def update_student(
    student_id: int,
    body: UpdateStudentRequest,
    user: dict = Depends(require_admin),
):
    """Update student profile fields. Admin only."""
    db = SyncSessionLocal()
    try:
        existing = db.execute(
            text("SELECT student_id FROM student WHERE student_id = :id"),
            {"id": student_id},
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Student not found.")

        fields, params = [], {"id": student_id}

        _map = {
            "student_name":        ("student_name",        body.student_name),
            "gender":              ("gender",               body.gender),
            "marital_status":      ("marital_status",       body.marital_status),
            "degree_type":         ("degree_type",          body.degree_type),
            "study_method":        ("study_method",         body.study_method),
            "program_status":      ("program_status",       body.program_status),
        }
        for key, (col, val) in _map.items():
            if val is not None:
                fields.append(f"{col} = :{key}"); params[key] = val

        _int_map = {
            "country_id":   body.country_id,
            "num_children": body.num_children,
            "program_id":   body.program_id,
            "discipline_id": body.discipline_id,
            "campus_id":    body.campus_id,
            "funding_id":   body.funding_id,
            "family_support": body.family_support,
        }
        for col, val in _int_map.items():
            if val is not None:
                fields.append(f"{col} = :{col}"); params[col] = val

        if body.email is not None:
            dup = db.execute(text(
                "SELECT 1 FROM student WHERE email = :email AND student_id != :id"
            ), {"email": body.email, "id": student_id}).fetchone()
            if dup:
                raise HTTPException(status_code=409, detail=f"Email '{body.email}' already in use.")
            fields.append("email = :email"); params["email"] = body.email

        if body.date_of_birth is not None:
            fields.append("date_of_birth = :dob"); params["dob"] = body.date_of_birth
        if body.enrollment_date is not None:
            fields.append("enrollment_date = :enrollment_date"); params["enrollment_date"] = body.enrollment_date
        if body.entry_gpa is not None:
            fields.append("entry_gpa = :entry_gpa"); params["entry_gpa"] = body.entry_gpa
        if body.is_cross_discipline is not None:
            fields.append("is_cross_discipline = :cross"); params["cross"] = int(body.is_cross_discipline)
        if body.has_external_work is not None:
            fields.append("has_external_work = :ext_work"); params["ext_work"] = int(body.has_external_work)
        if body.weekly_work_hours is not None:
            fields.append("weekly_work_hours = :wh"); params["wh"] = body.weekly_work_hours
        if body.in_research_group is not None:
            fields.append("in_research_group = :rg"); params["rg"] = int(body.in_research_group)

        if not fields:
            return {"success": True, "message": "Nothing to update."}

        db.execute(
            text(f"UPDATE student SET {', '.join(fields)} WHERE student_id = :id"),
            params,
        )
        db.commit()
        return {"success": True, "message": "Student updated."}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# CREATE SUPERVISOR / LECTURER
# ══════════════════════════════════════════════════════════════════════════════

class CreateSupervisorRequest(BaseModel):
    staff_id: str
    name: str
    email: str
    faculty_id: int
    role: str = "Supervisor"    # Supervisor | Admin | Both
    password: str


@router.post("/api/supervisors/")
def create_supervisor(body: CreateSupervisorRequest, user: dict = Depends(require_admin)):
    """Create a new supervisor/lecturer account. Admin only."""
    db = SyncSessionLocal()
    try:
        # Check duplicate staff_id
        exists = db.execute(text(
            "SELECT 1 FROM supervisor WHERE staff_id = :sid"
        ), {"sid": body.staff_id}).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail=f"Staff ID '{body.staff_id}' already exists.")

        # Check duplicate email
        exists_email = db.execute(text(
            "SELECT 1 FROM supervisor WHERE email = :email"
        ), {"email": body.email}).fetchone()
        if exists_email:
            raise HTTPException(status_code=409, detail=f"Email '{body.email}' already registered.")

        hashed = _pwd.hash(body.password)
        result = db.execute(text("""
            INSERT INTO supervisor (staff_id, name, email, faculty_id, role, password_hash, is_active)
            VALUES (:staff_id, :name, :email, :faculty_id, :role, :pw_hash, 1)
        """), {
            "staff_id":   body.staff_id,
            "name":       body.name,
            "email":      body.email,
            "faculty_id": body.faculty_id,
            "role":       body.role,
            "pw_hash":    hashed,
        })
        db.commit()
        return {"success": True, "supervisor_id": result.lastrowid,
                "message": f"Account '{body.name}' ({body.staff_id}) created successfully."}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
