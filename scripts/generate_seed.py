"""
Generate seed_data.sql from real Excel data.
Reads Data_input and data_coll sheets from PHD_data - Copy.xlsx
and produces a complete seed_data.sql with accurate milestone dates.

Usage:  python scripts/generate_seed.py
Output: scripts/seed_data.sql  (overwrites existing file)
"""
import sys
import os
from datetime import date, datetime

sys.stdout.reconfigure(encoding="utf-8")

try:
    import openpyxl
except ImportError:
    print("ERROR: openpyxl not installed.  Run: python -m pip install openpyxl")
    sys.exit(1)

EXCEL_PATH = r"D:\CodingSpace\DATATRAIN\PHD_data - Copy.xlsx"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "seed_data.sql")
TODAY = date(2026, 4, 28)

# ──────────────────────────────────────────────
# Lookup maps (must match INSERT order in SQL)
# ──────────────────────────────────────────────
CAMPUS_MAP   = {"CYBER": 1, "MLAKA": 2}
FACULTY_MAP  = {
    "Faculty of AI and Engineering": 1,
    "Faculty of Business":           2,
    "Faculty of Applied Comm":       3,
    "Faculty of Law":                4,
}
PROGRAM_MAP  = {
    "Ph.D. (Eng)":           (1, "PhD"),
    "Ph.D. (Mgmt.)":         (2, "PhD"),
    "Master (Mgmt)":         (3, "Master"),
    "Ph.D. (Communication)": (4, "PhD"),
    "Master (Communication)":(5, "Master"),
    "Master (Law)":          (6, "Master"),
}
STUDY_METHOD_MAP = {
    "full-time": "Full-time",
    "part-time": "Part-time",
}

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def d(val):
    """Format a date/datetime as SQL date string or NULL."""
    if val is None:
        return "NULL"
    if isinstance(val, datetime):
        val = val.date()
    return f"'{val.strftime('%Y-%m-%d')}'"

def q(val):
    """Single-quote a string value or NULL."""
    if val is None:
        return "NULL"
    escaped = str(val).replace("'", "''")
    return f"'{escaped}'"

def milestone_status(expected, actual):
    """Compute Pending/Completed/Overdue."""
    if actual is not None:
        return "Completed"
    if expected is None:
        return "Pending"
    exp = expected.date() if isinstance(expected, datetime) else expected
    return "Overdue" if exp <= TODAY else "Pending"

# ──────────────────────────────────────────────
# Read Excel
# ──────────────────────────────────────────────
wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)

# ---- Data_input ----
ws_input = wb["Data_input"]
input_headers = [c.value for c in ws_input[1]]

students_input = []   # list of dicts
for row in ws_input.iter_rows(min_row=2, values_only=True):
    if row[0] is None:
        continue
    r = dict(zip(input_headers, row))
    students_input.append(r)

# ---- data_coll ----
ws_coll = wb["data_coll"]
coll_headers = [c.value for c in ws_coll[1]]

students_coll = []
for row in ws_coll.iter_rows(min_row=2, values_only=True):
    if row[0] is None:
        continue
    r = dict(zip(coll_headers, row))
    students_coll.append(r)

wb.close()

# ──────────────────────────────────────────────
# Merge: join on row position (same order in both sheets)
# The duplicate Student_ID '250PS297RL' appears in both rows 38 & 39.
# Row 38 → KOH CHEE MING (Master, expected 2028)
# Row 39 → ANG ANSON     (PhD,    expected 2030) — ID fixed to 250PS298RL
# ──────────────────────────────────────────────
assert len(students_input) == len(students_coll), \
    f"Row count mismatch: Data_input={len(students_input)}, data_coll={len(students_coll)}"

# Fix duplicate ID on last row
if students_coll[-1]["Student_ID"] == students_coll[-2]["Student_ID"]:
    students_coll[-1]["Student_ID"] = "250PS298RL"
if students_input[-1]["Student_ID"] == students_input[-2]["Student_ID"]:
    students_input[-1]["Student_ID"] = "250PS298RL"

merged = []
for inp, col in zip(students_input, students_coll):
    assert inp["Student_ID"] == col["Student_ID"], \
        f"ID mismatch at same row: {inp['Student_ID']} vs {col['Student_ID']}"
    rec = {**inp, **col}   # col keys that overlap will overwrite (same values anyway)
    merged.append(rec)

# ──────────────────────────────────────────────
# Build SQL
# ──────────────────────────────────────────────
lines = []
A = lines.append   # append shorthand

A("-- ============================================")
A("-- SEED DATA — auto-generated from Excel")
A(f"-- Source: PHD_data - Copy.xlsx")
A(f"-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
A("-- ============================================")
A("")
A("USE datatrain;")
A("")

# ─── Regions ───
A("-- Regions")
A("INSERT INTO country_region (region_name) VALUES")
regions = [
    "East Asia", "South Asia", "Southeast Asia",
    "Middle East", "Europe", "Africa", "Americas",
]
A(",\n".join(f"({q(r)})" for r in regions) + ";")
A("")

# ─── Countries ───
A("-- Countries")
A("INSERT INTO country (country_name, region_id) VALUES")
countries = [
    ("China", 1), ("Japan", 1), ("South Korea", 1),
    ("India", 2), ("Pakistan", 2), ("Bangladesh", 2),
    ("Malaysia", 3), ("Indonesia", 3), ("Thailand", 3), ("Vietnam", 3),
    ("Saudi Arabia", 4), ("Iran", 4),
    ("United Kingdom", 5), ("Germany", 5),
    ("Nigeria", 6), ("Kenya", 6),
    ("United States", 7), ("Brazil", 7),
]
A(",\n".join(f"({q(c)}, {rid})" for c, rid in countries) + ";")
A("")

# ─── Faculties ───
A("-- Faculties (faculty_id: 1=AI&Eng, 2=Business, 3=Applied Comm, 4=Law)")
A("INSERT INTO faculty (faculty_description) VALUES")
faculties = [
    "Faculty of AI and Engineering",
    "Faculty of Business",
    "Faculty of Applied Comm",
    "Faculty of Law",
]
A(",\n".join(f"({q(f)})" for f in faculties) + ";")
A("")

# ─── Programs ───
A("-- Programs")
A("INSERT INTO program (program_short_desc, program_description, faculty_id) VALUES")
programs = [
    ("Ph.D. (Eng)",            "Doctor of Philosophy (Engineering)",   1),
    ("Ph.D. (Mgmt.)",          "Doctor of Philosophy (Management)",    2),
    ("Master (Mgmt)",          "Master of Management",                 2),
    ("Ph.D. (Communication)",  "Doctor of Philosophy (Communication)", 3),
    ("Master (Communication)", "Master of Communication",              3),
    ("Master (Law)",           "Master of Law",                        4),
]
A(",\n".join(f"({q(s)}, {q(d_)}, {fid})" for s, d_, fid in programs) + ";")
A("")

# ─── Disciplines ───
A("-- Disciplines")
A("INSERT INTO discipline (discipline_name, discipline_group) VALUES")
disciplines = [
    ("Engineering",   "STEM"),
    ("Management",    "Business"),
    ("Communication", "Social Science"),
    ("Law",           "Social Science"),
    ("Data Science",  "STEM"),
    ("Finance",       "Business"),
]
A(",\n".join(f"({q(n)}, {q(g)})" for n, g in disciplines) + ";")
A("")

# ─── Funding types ───
A("-- Funding types")
A("INSERT INTO funding_type (funding_name) VALUES")
fundings = [
    "Full Scholarship", "Partial Scholarship", "Self-funded",
    "Teaching Assistant", "Research Assistant", "Employer-sponsored",
]
A(",\n".join(f"({q(f)})" for f in fundings) + ";")
A("")

# ─── Campus ───
A("-- Campus (1=CYBER, 2=MLAKA)")
A("INSERT INTO campus (campus_name) VALUES")
A("('CYBER'),\n('MLAKA');")
A("")

# ─── Supervisors ───
A("-- Supervisors (password: 'password123'  bcrypt hash)")
A("INSERT INTO supervisor (staff_id, name, email, faculty_id, role, password_hash) VALUES")
supervisors = [
    ("ADM001",   "Dr. Admin User",     "admin@university.edu",      1, "Both"),
    ("MU081217", "Dr. Ahmad Rahman",   "ahmad@university.edu",      1, "Supervisor"),
    ("MU092301", "Dr. Sarah Chen",     "sarah.chen@university.edu", 2, "Supervisor"),
    ("MU103456", "Prof. James Wilson", "j.wilson@university.edu",   3, "Supervisor"),
    ("MU114567", "Dr. Fatimah Idris",  "fatimah@university.edu",    4, "Supervisor"),
]
PWD = "$2b$12$LJ3m4ys3Gz8Kvf0fRsRXB.JpGpx/A6WfFkYzS.3VqYCxLDzFqzfO6"
A(",\n".join(
    f"({q(sid)}, {q(nm)}, {q(em)}, {fid}, {q(role)}, {q(PWD)})"
    for sid, nm, em, fid, role in supervisors
) + ";")
A("")

# ──────────────────────────────────────────────
# Students
# ──────────────────────────────────────────────
A("-- Students (all 40 from Excel)")
A("INSERT INTO student (")
A("    student_id_number, student_name, campus_id,")
A("    campus_code, admit_term, admit_term_begin_date, expected_grad_term, program_status,")
A("    program_id, degree_type, enrollment_date, study_method,")
A("    is_cross_discipline, has_external_work, weekly_work_hours, in_research_group")
A(") VALUES")

student_rows = []
student_ids_ordered = []   # track insertion order (1-based index = student_id)

for rec in merged:
    sid_num = rec["Student_ID"]
    name    = str(rec["Name"]).strip()   # strip trailing whitespace from Excel
    campus_str = str(rec.get("Campus", "CYBER")).strip().upper()
    campus_id  = CAMPUS_MAP.get(campus_str, 1)
    campus_code = rec.get("CAMPUS_ID", None)

    admit_term      = rec.get("Admint_Term")
    admit_begin     = rec.get("AdmitTermBeginDate")
    expected_grad   = rec.get("ExpectedGradTerm")
    prog_status     = rec.get("Program_Status", "Active in Program")
    enrollment_date = rec.get("Admission_Date")

    prog_short = str(rec.get("Prog_short_Des", "")).strip()
    prog_id, degree_type = PROGRAM_MAP.get(prog_short, (1, "PhD"))

    study_raw = str(rec.get("Study_Method", "Full-Time")).strip().lower()
    study_method = STUDY_METHOD_MAP.get(study_raw, "Full-time")

    student_rows.append(
        f"({q(sid_num)}, {q(name)}, {campus_id}, "
        f"{q(campus_code)}, {admit_term}, {d(admit_begin)}, {expected_grad}, {q(prog_status)}, "
        f"{prog_id}, {q(degree_type)}, {d(enrollment_date)}, {q(study_method)}, "
        f"FALSE, FALSE, 0, FALSE)"
    )
    student_ids_ordered.append(sid_num)

A(",\n".join(student_rows) + ";")
A("")

# build id lookup: student_id_number → 1-based index
sid_to_db_id = {sid: i + 1 for i, sid in enumerate(student_ids_ordered)}

# ──────────────────────────────────────────────
# Student Milestones
# ──────────────────────────────────────────────
A("-- Student Milestones")
A("-- milestone_id: 1=RPD, 3=Publication, 4=Thesis Seminar")
A("-- earliest_start_date used only for Thesis Seminar (milestone_id=4)")
A("INSERT INTO student_milestone")
A("    (student_id, milestone_id, earliest_start_date, expected_date, actual_date, status)")
A("VALUES")

milestone_rows = []
for rec in merged:
    sid_num = rec["Student_ID"]
    db_id   = sid_to_db_id[sid_num]

    rpd_expected    = rec.get("RPD_MAXDate")
    rpd_actual      = rec.get("RPD_ActualDate")
    pub_expected    = rec.get("PublicationRequirement_MAXDate")
    pub_actual      = rec.get("PublicationRequirement_paper1_ActualDay（PHD/Master）")
    ts_start        = rec.get("ThesisSem_StartDate")
    ts_expected     = rec.get("ThesisSem_MAXDate")
    ts_actual       = rec.get("ThesisSem_ActualDate")

    # Milestone 1: RPD
    milestone_rows.append(
        f"({db_id}, 1, NULL, {d(rpd_expected)}, {d(rpd_actual)}, "
        f"'{milestone_status(rpd_expected, rpd_actual)}')"
    )
    # Milestone 3: Publication Requirement
    milestone_rows.append(
        f"({db_id}, 3, NULL, {d(pub_expected)}, {d(pub_actual)}, "
        f"'{milestone_status(pub_expected, pub_actual)}')"
    )
    # Milestone 4: Thesis Seminar (includes earliest_start_date)
    milestone_rows.append(
        f"({db_id}, 4, {d(ts_start)}, {d(ts_expected)}, {d(ts_actual)}, "
        f"'{milestone_status(ts_expected, ts_actual)}')"
    )

A(",\n".join(milestone_rows) + ";")
A("")

# ──────────────────────────────────────────────
# Student-Supervisor assignments
# Assign supervisors by faculty alignment; first 10 students get assignments.
# ──────────────────────────────────────────────
A("-- Student-Supervisor assignments")
A("INSERT INTO student_supervisor (student_id, supervisor_id, role, assigned_date) VALUES")

# Supervisor IDs (by insert order):
# 1=ADM001, 2=MU081217(Ahmad/Eng), 3=MU092301(Sarah/Business), 4=MU103456(James/Comm), 5=MU114567(Fatimah/Law)
# Map faculty_id → default supervisor_id
FAC_SUP = {1: 2, 2: 3, 3: 4, 4: 5}

ss_rows = []
seen_ss = set()

for rec in merged:
    sid_num = rec["Student_ID"]
    db_id   = sid_to_db_id[sid_num]
    prog_short = str(rec.get("Prog_short_Des", "")).strip()
    prog_id, _ = PROGRAM_MAP.get(prog_short, (1, "PhD"))

    # faculty based on program
    prog_fac = {1: 1, 2: 2, 3: 2, 4: 3, 5: 3, 6: 4}
    fac_id = prog_fac.get(prog_id, 1)
    sup_id = FAC_SUP.get(fac_id, 2)

    enrollment_date = rec.get("Admission_Date")
    enroll_str = enrollment_date.strftime("%Y-%m-%d") if isinstance(enrollment_date, datetime) else str(enrollment_date)

    key = (db_id, sup_id)
    if key not in seen_ss:
        seen_ss.add(key)
        ss_rows.append(f"({db_id}, {sup_id}, 'Main', '{enroll_str}')")

A(",\n".join(ss_rows) + ";")
A("")

# ──────────────────────────────────────────────
# PPM Records (sample — a few students with 2025 H2 results)
# ──────────────────────────────────────────────
A("-- PPM Records (2025 H2 sample)")
A("INSERT INTO ppm_record (student_id, ppm_year, ppm_cycle, result, verify_status, verified_by_id, verified_by_name) VALUES")
ppm_samples = [
    (1, 2025, 2, "S",  "Y", "MU081217", "Dr. Ahmad Rahman"),
    (2, 2025, 2, "S",  "Y", "MU081217", "Dr. Ahmad Rahman"),
    (3, 2025, 2, "US", "Y", "MU081217", "Dr. Ahmad Rahman"),
    (4, 2025, 2, "S",  "Y", "MU081217", "Dr. Ahmad Rahman"),
    (5, 2025, 2, "US", "Y", "MU081217", "Dr. Ahmad Rahman"),
    (6, 2025, 2, "S",  "Y", "MU103456", "Prof. James Wilson"),
    (7, 2025, 2, "S",  "Y", "MU103456", "Prof. James Wilson"),
]
A(",\n".join(
    f"({sid}, {yr}, {cy}, {q(res)}, {q(vs)}, {q(vid)}, {q(vnm)})"
    for sid, yr, cy, res, vs, vid, vnm in ppm_samples
) + ";")
A("")

# ──────────────────────────────────────────────
# Graduation Outcomes (all students — use real ExpectedEnd_StudyDate)
# ──────────────────────────────────────────────
A("-- Graduation Outcomes (all 40 students)")
A("INSERT INTO graduation_outcome (student_id, expected_end_date, actual_end_date, is_delayed, final_status) VALUES")

go_rows = []
for rec in merged:
    sid_num = rec["Student_ID"]
    db_id   = sid_to_db_id[sid_num]
    exp_end = rec.get("ExpectedEnd_StudyDate")
    go_rows.append(f"({db_id}, {d(exp_end)}, NULL, FALSE, 'Ongoing')")

A(",\n".join(go_rows) + ";")
A("")

# ──────────────────────────────────────────────
# Examiners
# ──────────────────────────────────────────────
A("-- Examiners")
A("INSERT INTO examiner (examiner_name, institution, is_external) VALUES")
A("('Prof. Tan Ah Kow', 'University of Malaya', TRUE),")
A("('Dr. Lee Wei Ming', 'NUS', TRUE),")
A("('Prof. Yamamoto', 'University of Tokyo', TRUE);")
A("")

# ──────────────────────────────────────────────
# Write output
# ──────────────────────────────────────────────
sql_content = "\n".join(lines) + "\n"
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    f.write(sql_content)

print(f"✓ Generated {OUTPUT_PATH}")
print(f"  Students:    {len(merged)}")
print(f"  Milestones:  {len(milestone_rows)} rows  (3 per student)")
print(f"  Grad outcome:{len(go_rows)} rows")
print(f"  Supervisors: {len(ss_rows)} assignments")

# Preview first few milestone rows
print("\nSample milestone rows:")
for r in milestone_rows[:6]:
    print(" ", r)
