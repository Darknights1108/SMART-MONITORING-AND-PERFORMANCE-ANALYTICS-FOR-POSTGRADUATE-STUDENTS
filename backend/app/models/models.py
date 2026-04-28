"""
SQLAlchemy ORM models matching schema.sql
"""
from sqlalchemy import (
    Column, Integer, String, Date, DateTime, Boolean, Enum, Text,
    DECIMAL, ForeignKey, YEAR, func, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database import Base


# =====================
# 1. LOOKUP TABLES
# =====================

class CountryRegion(Base):
    __tablename__ = "country_region"
    region_id = Column(Integer, primary_key=True, autoincrement=True)
    region_name = Column(String(50), nullable=False, unique=True)
    countries = relationship("Country", back_populates="region")


class Country(Base):
    __tablename__ = "country"
    country_id = Column(Integer, primary_key=True, autoincrement=True)
    country_name = Column(String(100), nullable=False, unique=True)
    region_id = Column(Integer, ForeignKey("country_region.region_id"), nullable=False)
    region = relationship("CountryRegion", back_populates="countries")


class Faculty(Base):
    __tablename__ = "faculty"
    faculty_id = Column(Integer, primary_key=True, autoincrement=True)
    faculty_description = Column(String(200), nullable=False, unique=True)
    programs = relationship("Program", back_populates="faculty")
    supervisors = relationship("Supervisor", back_populates="faculty")


class Program(Base):
    __tablename__ = "program"
    program_id = Column(Integer, primary_key=True, autoincrement=True)
    program_short_desc = Column(String(50), nullable=False)
    program_description = Column(String(200), nullable=False)
    faculty_id = Column(Integer, ForeignKey("faculty.faculty_id"), nullable=False)
    faculty = relationship("Faculty", back_populates="programs")


class Discipline(Base):
    __tablename__ = "discipline"
    discipline_id = Column(Integer, primary_key=True, autoincrement=True)
    discipline_name = Column(String(100), nullable=False, unique=True)
    discipline_group = Column(String(50), nullable=False)


class FundingType(Base):
    __tablename__ = "funding_type"
    funding_id = Column(Integer, primary_key=True, autoincrement=True)
    funding_name = Column(String(100), nullable=False, unique=True)


class Campus(Base):
    __tablename__ = "campus"
    campus_id = Column(Integer, primary_key=True, autoincrement=True)
    campus_name = Column(String(200), nullable=False, unique=True)


# =====================
# 2. CORE: STUDENT
# =====================

class Student(Base):
    __tablename__ = "student"
    student_id = Column(Integer, primary_key=True, autoincrement=True)
    student_id_number = Column(String(50), nullable=False, unique=True)
    student_name = Column(String(200), nullable=False)
    email = Column(String(200), nullable=True)
    campus_id = Column(Integer, ForeignKey("campus.campus_id"), nullable=False)

    # Term / intake info (from university system)
    campus_code = Column(String(20), nullable=True)
    admit_term = Column(Integer, nullable=True)
    admit_term_begin_date = Column(Date, nullable=True)
    expected_grad_term = Column(Integer, nullable=True)
    program_status = Column(String(50), nullable=True, default="Active in Program")

    # Demographic
    gender = Column(Enum("Male", "Female", "Other"), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    country_id = Column(Integer, ForeignKey("country.country_id"), nullable=True)
    marital_status = Column(Enum("Single", "Married", "Divorced", "Widowed"), nullable=True)
    num_children = Column(Integer, nullable=False, default=0)
    youngest_child_age = Column(DECIMAL(3, 1), nullable=True)

    # Academic
    program_id = Column(Integer, ForeignKey("program.program_id"), nullable=False)
    degree_type = Column(Enum("Master", "PhD"), nullable=False)
    discipline_id = Column(Integer, ForeignKey("discipline.discipline_id"), nullable=True)
    enrollment_date = Column(Date, nullable=False)
    entry_gpa = Column(DECIMAL(4, 2), nullable=True)
    is_cross_discipline = Column(Boolean, nullable=False, default=False)
    study_method = Column(Enum("Full-time", "Part-time"), nullable=False)

    # Financial
    funding_id = Column(Integer, ForeignKey("funding_type.funding_id"), nullable=True)
    has_external_work = Column(Boolean, nullable=False, default=False)
    weekly_work_hours = Column(DECIMAL(4, 1), nullable=False, default=0)

    # Social
    in_research_group = Column(Boolean, nullable=False, default=False)
    family_support = Column(Integer, nullable=True)

    # Relationships
    campus = relationship("Campus")
    country = relationship("Country")
    program = relationship("Program")
    discipline = relationship("Discipline")
    funding = relationship("FundingType")
    milestones = relationship("StudentMilestone", back_populates="student")
    ppm_records = relationship("PPMRecord", back_populates="student")
    graduation_outcome = relationship("GraduationOutcome", back_populates="student", uselist=False)
    supervisors = relationship("StudentSupervisor", back_populates="student")
    examiner_reports = relationship("ExaminerReport", back_populates="student")


# =====================
# 3. MILESTONE TRACKING
# =====================

class Milestone(Base):
    __tablename__ = "milestone"
    milestone_id = Column(Integer, primary_key=True)
    milestone_name = Column(String(100), nullable=False, unique=True)
    milestone_order = Column(Integer, nullable=False)
    master_ft_norm = Column(Integer, nullable=True)
    master_ft_max = Column(Integer, nullable=True)
    master_pt_norm = Column(Integer, nullable=True)
    master_pt_max = Column(Integer, nullable=True)
    phd_ft_norm = Column(Integer, nullable=True)
    phd_ft_max = Column(Integer, nullable=True)
    phd_pt_norm = Column(Integer, nullable=True)
    phd_pt_max = Column(Integer, nullable=True)


class StudentMilestone(Base):
    __tablename__ = "student_milestone"
    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("student.student_id"), nullable=False)
    milestone_id = Column(Integer, ForeignKey("milestone.milestone_id"), nullable=False)
    earliest_start_date = Column(Date, nullable=True)  # Only used by Thesis Seminar
    expected_date = Column(Date, nullable=True)
    actual_date = Column(Date, nullable=True)
    status = Column(Enum("Pending", "Completed", "Overdue"), nullable=False, default="Pending")
    remarks = Column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("student_id", "milestone_id"),)
    student = relationship("Student", back_populates="milestones")
    milestone = relationship("Milestone")


# =====================
# 4. PPM RECORDS
# =====================

class PPMRecord(Base):
    __tablename__ = "ppm_record"
    ppm_id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("student.student_id"), nullable=False)
    ppm_year = Column(Integer, nullable=False)
    ppm_cycle = Column(Integer, nullable=False)
    result = Column(Enum("S", "US"), nullable=True)
    verify_status = Column(Enum("Y", "N"), nullable=False, default="N")
    verify_date = Column(Date, nullable=True)
    verified_by_id = Column(String(50), nullable=True)
    verified_by_name = Column(String(200), nullable=True)
    remarks = Column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("student_id", "ppm_year", "ppm_cycle"),)
    student = relationship("Student", back_populates="ppm_records")


# =====================
# 5. EXAMINER
# =====================

class Examiner(Base):
    __tablename__ = "examiner"
    examiner_id = Column(Integer, primary_key=True, autoincrement=True)
    examiner_name = Column(String(200), nullable=False)
    institution = Column(String(200), nullable=True)
    is_external = Column(Boolean, nullable=False, default=False)


class ExaminerReport(Base):
    __tablename__ = "examiner_report"
    report_id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("student.student_id"), nullable=False)
    examiner_id = Column(Integer, ForeignKey("examiner.examiner_id"), nullable=False)
    report_date = Column(Date, nullable=False)

    score_motivation = Column(Integer, nullable=False)
    score_objectives = Column(Integer, nullable=False)
    score_literature = Column(Integer, nullable=False)
    score_methodology = Column(Integer, nullable=False)
    score_data_collection = Column(Integer, nullable=False)
    score_analysis = Column(Integer, nullable=False)
    score_contribution = Column(Integer, nullable=False)
    score_references = Column(Integer, nullable=False)
    score_rigour = Column(Integer, nullable=False)
    score_general = Column(Integer, nullable=False)

    recommendation = Column(Enum(
        "Accepted", "Minor Modifications", "Major Corrections",
        "Re-examination", "Rejected"
    ), nullable=False)
    rejection_suboption = Column(Enum(
        "Award Master", "Resubmit as Master", "No Degree"
    ), nullable=True)

    student = relationship("Student", back_populates="examiner_reports")
    examiner = relationship("Examiner")


# =====================
# 6. GRADUATION OUTCOME
# =====================

class GraduationOutcome(Base):
    __tablename__ = "graduation_outcome"
    outcome_id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("student.student_id"), nullable=False, unique=True)
    expected_end_date = Column(Date, nullable=False)
    actual_end_date = Column(Date, nullable=True)
    is_delayed = Column(Boolean, nullable=False, default=False)
    final_status = Column(Enum(
        "Graduated On-time", "Graduated Delayed", "Dropped Out", "Ongoing"
    ), nullable=False)

    student = relationship("Student", back_populates="graduation_outcome")


# =====================
# 8. SUPERVISOR / USER
# =====================

class Supervisor(Base):
    __tablename__ = "supervisor"
    supervisor_id = Column(Integer, primary_key=True, autoincrement=True)
    staff_id = Column(String(50), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    email = Column(String(200), nullable=False)
    faculty_id = Column(Integer, ForeignKey("faculty.faculty_id"), nullable=False)
    role = Column(Enum("Supervisor", "Admin", "Both"), nullable=False, default="Supervisor")
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    faculty = relationship("Faculty", back_populates="supervisors")
    students = relationship("StudentSupervisor", back_populates="supervisor")
    chat_history = relationship("ChatHistory", back_populates="supervisor")


class StudentSupervisor(Base):
    __tablename__ = "student_supervisor"
    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("student.student_id"), nullable=False)
    supervisor_id = Column(Integer, ForeignKey("supervisor.supervisor_id"), nullable=False)
    role = Column(Enum("Main", "Co"), nullable=False, default="Main")
    assigned_date = Column(Date, nullable=False)

    __table_args__ = (UniqueConstraint("student_id", "supervisor_id"),)
    student = relationship("Student", back_populates="supervisors")
    supervisor = relationship("Supervisor", back_populates="students")


# =====================
# 9. EMAIL LOG
# =====================

class EmailLog(Base):
    __tablename__ = "email_log"
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("student.student_id"), nullable=False)
    recipient_type = Column(Enum("Student", "Supervisor", "Admin"), nullable=False)
    recipient_email = Column(String(200), nullable=False)
    subject = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    trigger_type = Column(Enum("Auto", "Manual"), nullable=False)
    urgency_level = Column(Enum("Normal", "Urgent", "Critical"), nullable=False, default="Normal")
    milestone_id = Column(Integer, ForeignKey("milestone.milestone_id"), nullable=True)
    sent_at = Column(DateTime, nullable=False, server_default=func.now())

    student = relationship("Student")
    milestone = relationship("Milestone")


# =====================
# 10. CHAT HISTORY
# =====================

class ChatHistory(Base):
    __tablename__ = "chat_history"
    chat_id = Column(Integer, primary_key=True, autoincrement=True)
    supervisor_id = Column(Integer, ForeignKey("supervisor.supervisor_id"), nullable=False)
    session_id = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    role = Column(Enum("user", "assistant"), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    supervisor = relationship("Supervisor", back_populates="chat_history")


# =====================
# 11. REMINDER RULES
# =====================

class ReminderRule(Base):
    __tablename__ = "reminder_rule"
    rule_id = Column(Integer, primary_key=True, autoincrement=True)
    days_before = Column(Integer, nullable=False)
    notify_student = Column(Boolean, nullable=False, default=True)
    notify_supervisor = Column(Boolean, nullable=False, default=False)
    notify_admin = Column(Boolean, nullable=False, default=False)
    urgency_level = Column(Enum("Normal", "Urgent", "Critical"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
