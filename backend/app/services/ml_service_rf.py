"""
Multi-Stage Random Forest Risk Prediction Service
--------------------------------------------------
Predicts graduation delay risk using a staged approach.
ALL THREE stages use Random Forest models pre-trained on the UCI dataset.

  Stage 1 — Enrollment features only (available from day 1)
    Pre-trained on: UCI data.csv (3630 students, enrollment features only)
    Features: age, GPA, work hours, family support, gender, study mode,
              external work, research group, cross-discipline, degree type,
              region, discipline group, funding type, marital status

  Stage 2 — Adds academic progress proxies (after first PPM cycle / RPD)
    Pre-trained on: UCI data.csv (1st semester performance columns)
    UCI → DATATRAIN proxy mapping:
      perf_rate_s1   : 1st sem approved/enrolled  →  1 − PPM unsatisfactory rate
      perf_quality_s1: 1st sem grade / 20          →  1 − clip(RPD delay / 365, 0, 1)
      months_enrolled: ~18 (fixed for UCI)         →  actual months since enrollment

  Stage 3 — Adds second-cycle academic assessment (after examiner report)
    Pre-trained on: UCI data.csv (2nd semester performance columns)
    UCI → DATATRAIN proxy mapping:
      perf_rate_s2   : 2nd sem approved/enrolled  →  examiner_avg_score / 5
      perf_quality_s2: 2nd sem grade / 20          →  examiner_avg_score / 5
      perf_trend     : (s2_grade − s1_grade) / 20 →  perf_rate_s2 − perf_rate_s1

Feature proxy rationale (see research notes in _rule_based_stage2):
  - UCI curricular unit approval rate captures same signal as PPM pass rate
  - UCI semester grade decline parallels RPD milestone delay pattern
  - Both are 0–1 normalised → same RF feature space

MLOps:
  - All stages logged to MLflow under separate run tags
  - Models saved locally as joblib fallback
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

import joblib
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    classification_report,
)
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sqlalchemy import text

from app.config import get_settings
from app.database import SyncSessionLocal

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Paths ──────────────────────────────────────────────────────────────────────
_MODEL_DIR   = os.path.join(os.path.dirname(__file__), "..", "ml_models")
_DATA_CSV    = "/app/data.csv"

_RF_S1_PATH  = os.path.join(_MODEL_DIR, "rf_stage1.joblib")
_RF_S2_PATH  = os.path.join(_MODEL_DIR, "rf_stage2.joblib")
_RF_S3_PATH  = os.path.join(_MODEL_DIR, "rf_stage3.joblib")
_ENC_PATH    = os.path.join(_MODEL_DIR, "rf_encoders.joblib")

# ── Feature definitions per stage ─────────────────────────────────────────────
STAGE1_FEATURES = [
    "age_at_enrollment",    # numeric
    "entry_gpa",            # numeric (nullable → fill 0)
    "weekly_work_hours",    # numeric
    "family_support",       # numeric 1–5 (nullable → fill 3)
    "gender_enc",           # encoded: Male=0, Female=1, Other=2
    "is_part_time",         # binary: Part-time=1
    "has_external_work",    # binary
    "in_research_group",    # binary
    "is_cross_discipline",  # binary
    "is_phd",               # binary: PhD=1
    "region_enc",           # encoded region
    "discipline_group_enc", # encoded discipline group
    "funding_enc",          # encoded funding type
    "marital_status_enc",   # encoded marital status
]

# Stage 2 adds academic-progress proxy features.
# These are derived from UCI 1st-semester columns during pre-training,
# and from PPM/RPD data during DATATRAIN inference — both normalised to [0,1].
#
#   perf_rate_s1   : UCI 1st sem approved/enrolled  |  DATATRAIN 1 - ppm_us_rate
#   perf_quality_s1: UCI 1st sem grade/20            |  DATATRAIN 1 - clip(rpd_delay/365, 0, 1)
#   months_enrolled: UCI fixed ~18 months            |  DATATRAIN actual months
STAGE2_FEATURES = STAGE1_FEATURES + [
    "perf_rate_s1",         # [0-1] academic performance rate, 1st cycle
    "perf_quality_s1",      # [0-1] academic quality score, 1st cycle
    "months_enrolled",      # months since enrollment
]

# Stage 3 adds second-cycle assessment proxy features.
# UCI source: 2nd semester columns. DATATRAIN source: examiner report.
#
#   perf_rate_s2   : UCI 2nd sem approved/enrolled  |  DATATRAIN examiner_avg/5
#   perf_quality_s2: UCI 2nd sem grade/20            |  DATATRAIN examiner_avg/5
#   perf_trend     : UCI (s2_grade-s1_grade)/20      |  DATATRAIN perf_rate_s2 - perf_rate_s1
STAGE3_FEATURES = STAGE2_FEATURES + [
    "perf_rate_s2",         # [0-1] academic performance rate, 2nd cycle
    "perf_quality_s2",      # [0-1] academic quality score, 2nd cycle
    "perf_trend",           # [-1,1] improvement from 1st → 2nd cycle
]

# ── RF hyperparameters ─────────────────────────────────────────────────────────
RF_PARAMS = {
    "n_estimators":  200,
    "max_depth":     8,
    "min_samples_leaf": 5,
    "class_weight":  "balanced",
    "random_state":  42,
    "n_jobs":        -1,
}

# ── Label thresholds (predict_proba → risk label) ─────────────────────────────
# RF outputs P(dropout). Map to Low/Medium/High.
def _proba_to_label(proba_dropout: float) -> str:
    if proba_dropout >= 0.60:
        return "High"
    elif proba_dropout >= 0.35:
        return "Medium"
    return "Low"

def _proba_to_score(proba_dropout: float) -> float:
    """Convert P(dropout) to 0–100 risk score."""
    return round(float(proba_dropout) * 100, 2)


# ══════════════════════════════════════════════════════════════════════════════
# PART 1: Pre-training on data.csv  (UCI Student Dropout dataset)
# ══════════════════════════════════════════════════════════════════════════════

def _load_external_data() -> Optional[pd.DataFrame]:
    """
    Load and preprocess the UCI data.csv for Stage 1 pre-training.
    Maps UCI columns → our Stage 1 feature names.
    Returns None if file not found.
    """
    csv_path = _DATA_CSV
    if not os.path.exists(csv_path):
        logger.warning(f"[RF] data.csv not found at {csv_path}. Skipping pre-training.")
        return None

    df = pd.read_csv(csv_path, sep=";")

    # Keep only Graduate / Dropout (drop Enrolled — still ongoing)
    df = df[df["Target"].isin(["Graduate", "Dropout"])].copy()
    df["is_delayed"] = (df["Target"] == "Dropout").astype(int)

    # Map UCI columns → our feature names
    # Daytime=1 → Full-time, Evening=0 → Part-time
    df["is_part_time"]        = (df["Daytime/evening attendance\t"] == 0).astype(float)
    df["has_external_work"]   = df["Debtor"].astype(float)        # proxy: debtor
    # in_research_group: UCI has no direct equivalent → use 0 (unknown)
    # funding_enc now carries the scholarship signal properly
    df["in_research_group"]   = 0.0                               # not in UCI → unknown
    df["is_cross_discipline"] = 0.0                               # not in UCI
    df["is_phd"]              = 0.0                               # UCI = undergrad → all 0

    # Numeric features
    df["age_at_enrollment"]   = pd.to_numeric(df["Age at enrollment"], errors="coerce").fillna(22)
    df["entry_gpa"]           = pd.to_numeric(df["Admission grade"],   errors="coerce").fillna(130)
    # Normalise 95–190 → 0–4 GPA scale (rough mapping)
    df["entry_gpa"]           = ((df["entry_gpa"] - 95) / (190 - 95) * 4.0).clip(0, 4)
    df["weekly_work_hours"]   = np.where(df["has_external_work"] == 1, 20.0, 0.0)
    df["family_support"]      = 3.0                               # not in UCI → neutral

    # Gender: 1=Male, 0=Female in UCI
    df["gender_enc"]          = df["Gender"].astype(float)        # already 0/1

    # Region: proxy via International flag
    df["region_enc"]          = df["International"].astype(float) # 0=local, 1=international

    # Discipline group: proxy via Course (just use 0 — unknown)
    df["discipline_group_enc"] = 0.0

    # Funding: map UCI Scholarship holder → numeric
    # 1 = has scholarship, 0 = no scholarship (proxy for Full Scholarship vs Self-funded)
    df["funding_name"] = df["Scholarship holder"].map({1: "Full Scholarship", 0: "Self-funded"})
    df["funding_enc"]  = df["Scholarship holder"].astype(float)

    # Marital status: map UCI numeric codes → our ENUM strings
    # 1=Single, 2=Married, 3=Widower→Widowed, 4=Divorced, 5=Facto union→Married, 6=Legally separated→Divorced
    marital_map = {1: "Single", 2: "Married", 3: "Widowed", 4: "Divorced", 5: "Married", 6: "Divorced"}
    df["marital_status"] = df["Marital status"].map(marital_map).fillna("Single")
    # Pre-encode using alphabetical order (consistent with LabelEncoder on DB data):
    # Divorced=0, Married=1, Single=2, Widowed=3
    enc_map = {"Divorced": 0, "Married": 1, "Single": 2, "Widowed": 3}
    df["marital_status_enc"] = df["marital_status"].map(enc_map).fillna(2).astype(float)

    # ── Stage 2 proxy features from UCI 1st-semester columns ─────────────────
    # UCI grading scale: 0–20 (Portuguese system; passing = 10)
    # We normalise to [0,1] so the feature space matches DATATRAIN proxies.
    #
    # perf_rate_s1   = approved units / enrolled units  (pass rate)
    # perf_quality_s1 = avg grade / 20                  (quality)
    # months_enrolled = fixed ~18 for UCI undergrads (1 academic year ≈ 9 months
    #                   but research-programme students start Stage 2 ~12–18 months in)

    uci_1st_enrolled = pd.to_numeric(df["Curricular units 1st sem (enrolled)"],  errors="coerce").fillna(0)
    uci_1st_approved = pd.to_numeric(df["Curricular units 1st sem (approved)"],  errors="coerce").fillna(0)
    uci_1st_grade    = pd.to_numeric(df["Curricular units 1st sem (grade)"],     errors="coerce").fillna(0)

    df["perf_rate_s1"]    = np.where(uci_1st_enrolled > 0,
                                     uci_1st_approved / uci_1st_enrolled, 0.0).clip(0.0, 1.0)
    df["perf_quality_s1"] = (uci_1st_grade / 20.0).clip(0.0, 1.0)
    df["months_enrolled"] = 18.0   # fixed proxy: Stage 2 ≈ first-year review point

    # ── Stage 3 proxy features from UCI 2nd-semester columns ─────────────────
    # perf_rate_s2   = 2nd sem approved/enrolled
    # perf_quality_s2 = 2nd sem grade/20
    # perf_trend     = (grade_s2 - grade_s1) / 20  — negative = declining performance

    uci_2nd_enrolled = pd.to_numeric(df["Curricular units 2nd sem (enrolled)"],  errors="coerce").fillna(0)
    uci_2nd_approved = pd.to_numeric(df["Curricular units 2nd sem (approved)"],  errors="coerce").fillna(0)
    uci_2nd_grade    = pd.to_numeric(df["Curricular units 2nd sem (grade)"],     errors="coerce").fillna(0)

    df["perf_rate_s2"]    = np.where(uci_2nd_enrolled > 0,
                                     uci_2nd_approved / uci_2nd_enrolled, 0.0).clip(0.0, 1.0)
    df["perf_quality_s2"] = (uci_2nd_grade / 20.0).clip(0.0, 1.0)
    df["perf_trend"]      = ((uci_2nd_grade - uci_1st_grade) / 20.0).clip(-1.0, 1.0)

    all_features = STAGE3_FEATURES + ["is_delayed"]   # STAGE3 is a superset of all
    out = df[all_features].copy()
    out = out.fillna(0)
    logger.info(
        f"[RF] External data loaded: {len(out)} rows, "
        f"dropout rate={out['is_delayed'].mean():.2%}, "
        f"avg perf_rate_s1={out['perf_rate_s1'].mean():.2f}, "
        f"avg perf_rate_s2={out['perf_rate_s2'].mean():.2f}"
    )
    return out


# ══════════════════════════════════════════════════════════════════════════════
# PART 2: Extract features from our DB
# ══════════════════════════════════════════════════════════════════════════════

_FEATURE_QUERY = text("""
    SELECT
        s.student_id,
        s.student_name,
        s.student_id_number,
        s.degree_type,
        s.study_method,
        s.gender,
        COALESCE(s.age_at_enrollment, 25)   AS age_at_enrollment,
        COALESCE(s.entry_gpa, 0)            AS entry_gpa,
        s.weekly_work_hours,
        s.has_external_work,
        s.is_cross_discipline,
        s.in_research_group,
        COALESCE(s.family_support, 3)       AS family_support,
        cr.region_name,
        d.discipline_group,
        COALESCE(ft.funding_name, 'Unknown')           AS funding_name,
        COALESCE(s.marital_status, 'Single')           AS marital_status,
        -- RPD milestone delay
        CASE
            WHEN sm.actual_date IS NOT NULL
                THEN DATEDIFF(sm.actual_date, sm.expected_date)
            WHEN sm.expected_date IS NOT NULL
                THEN DATEDIFF(CURDATE(), sm.expected_date)
            ELSE 0
        END AS rpd_delay_days,
        -- 1 if RPD is actually submitted/completed, 0 otherwise
        CASE WHEN sm.actual_date IS NOT NULL THEN 1 ELSE 0 END AS rpd_completed,
        -- PPM stats
        COALESCE(ppm.cumulative_us, 0) AS ppm_us_count,
        COALESCE(ppm.total_ppm, 0)     AS ppm_total,
        -- Months enrolled
        TIMESTAMPDIFF(MONTH, s.enrollment_date, CURDATE()) AS months_enrolled,
        -- Publication progress
        (SELECT COUNT(*) FROM student_publication sp
         WHERE sp.student_id = s.student_id
           AND sp.status IN ('Accepted','Published')) AS pub_accepted_count,
        (SELECT COUNT(*) FROM student_publication sp
         WHERE sp.student_id = s.student_id) AS pub_submitted_count,
        -- Required papers: PhD=2, Master=1
        CASE WHEN s.degree_type = 'PhD' THEN 2 ELSE 1 END AS pub_required,
        -- Publication milestone overdue days (milestone_id=3)
        CASE
            WHEN sm3.actual_date IS NOT NULL THEN 0
            WHEN sm3.expected_date IS NOT NULL AND sm3.expected_date < CURDATE()
                THEN DATEDIFF(CURDATE(), sm3.expected_date)
            ELSE 0
        END AS pub_overdue_days,
        -- Examiner avg (NULL if no report yet)
        (SELECT AVG(er.score_avg)
         FROM examiner_report er
         WHERE er.student_id = s.student_id) AS examiner_avg_score,
        -- Thesis seminar delay
        CASE
            WHEN sm4.actual_date IS NOT NULL
                THEN DATEDIFF(sm4.actual_date, sm4.expected_date)
            WHEN sm4.expected_date IS NOT NULL
                THEN DATEDIFF(CURDATE(), sm4.expected_date)
            ELSE 0
        END AS thesis_seminar_delay,
        -- Ground truth label (NULL for active students)
        go.is_delayed
    FROM student s
    LEFT JOIN country c             ON s.country_id = c.country_id
    LEFT JOIN country_region cr     ON c.region_id = cr.region_id
    LEFT JOIN discipline d          ON s.discipline_id = d.discipline_id
    LEFT JOIN funding_type ft       ON s.funding_id = ft.funding_id
    LEFT JOIN student_milestone sm  ON s.student_id = sm.student_id AND sm.milestone_id = 1
    LEFT JOIN student_milestone sm3 ON s.student_id = sm3.student_id AND sm3.milestone_id = 3
    LEFT JOIN student_milestone sm4 ON s.student_id = sm4.student_id AND sm4.milestone_id = 4
    LEFT JOIN v_ppm_us_count ppm    ON s.student_id = ppm.student_id
    LEFT JOIN graduation_outcome go ON s.student_id = go.student_id
""")


def _extract_db_features() -> pd.DataFrame:
    """Pull all features from our DB and return an encoded DataFrame."""
    db = SyncSessionLocal()
    try:
        rows = db.execute(_FEATURE_QUERY).fetchall()
    finally:
        db.close()

    df = pd.DataFrame(rows, columns=[
        "student_id", "student_name", "student_id_number",
        "degree_type", "study_method", "gender",
        "age_at_enrollment", "entry_gpa", "weekly_work_hours",
        "has_external_work", "is_cross_discipline", "in_research_group",
        "family_support", "region_name", "discipline_group", "funding_name", "marital_status",
        "rpd_delay_days", "rpd_completed",
        "ppm_us_count", "ppm_total", "months_enrolled",
        "pub_accepted_count", "pub_submitted_count", "pub_required", "pub_overdue_days",
        "examiner_avg_score", "thesis_seminar_delay",
        "is_delayed",
    ])

    # Cast numerics
    numeric_cols = [
        "age_at_enrollment", "entry_gpa", "weekly_work_hours",
        "family_support", "rpd_delay_days", "rpd_completed",
        "ppm_us_count", "ppm_total", "months_enrolled",
        "pub_accepted_count", "pub_submitted_count",
        "pub_required", "pub_overdue_days",
        "examiner_avg_score", "thesis_seminar_delay",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Ensure key columns never have NaN — SQL CASE always returns 0 or a
    # positive integer, but defensive fill guards against any edge cases
    # (e.g. unexpected NULL from DB driver) that would silently break the
    # rule-based scoring logic in _rule_based_stage2/_rule_based_stage3.
    for col in ["rpd_completed", "pub_overdue_days", "pub_accepted_count", "pub_submitted_count", "pub_required"]:
        df[col] = df[col].fillna(0)

    return df


def _encode_features(df: pd.DataFrame, encoders: Optional[dict] = None) -> tuple[pd.DataFrame, dict]:
    """
    Encode categorical features and build/apply label encoders.
    Returns (encoded_df, encoders_dict).
    If encoders is provided, apply existing encoders (inference mode).
    If None, fit new encoders (training mode).
    """
    out = df.copy()
    fit_mode = encoders is None
    if fit_mode:
        encoders = {}

    # ── Binary / simple derived features ─────────────────────────────────────
    out["is_part_time"]        = (out["study_method"] == "Part-time").astype(float)
    out["is_phd"]              = (out["degree_type"]  == "PhD").astype(float)
    out["ppm_us_rate"]         = np.where(out["ppm_total"] > 0,
                                          out["ppm_us_count"] / out["ppm_total"], 0.0)
    out["has_external_work"]   = out["has_external_work"].astype(float)
    out["in_research_group"]   = out["in_research_group"].astype(float)
    out["is_cross_discipline"] = out["is_cross_discipline"].astype(float)

    # ── Fixed encoding for marital_status ────────────────────────────────────
    # Must match the alphabetical order used in _load_external_data UCI mapping.
    _MARITAL_ENC = {"Divorced": 0, "Married": 1, "Single": 2, "Widowed": 3}
    out["marital_status"]     = out["marital_status"].fillna("Single")
    out["marital_status_enc"] = out["marital_status"].map(_MARITAL_ENC).fillna(2).astype(float)

    # ── Categorical label encoding ────────────────────────────────────────────
    for col, name in [
        ("gender",          "gender_enc"),
        ("region_name",     "region_enc"),
        ("discipline_group","discipline_group_enc"),
        ("funding_name",    "funding_enc"),
    ]:
        out[col] = out[col].fillna("Unknown")
        if fit_mode:
            le = LabelEncoder()
            le.fit(list(out[col].unique()) + ["Unknown"])
            encoders[col] = le
        le = encoders[col]
        known = set(le.classes_)
        out[col] = out[col].apply(lambda x: x if x in known else "Unknown")
        out[name] = le.transform(out[col]).astype(float)

    # ── Stage 2 proxy features (DATATRAIN → UCI-compatible [0,1] space) ──────
    # perf_rate_s1: proportion of PPM cycles that were Satisfactory
    #   = 1 − ppm_us_rate  (all Satisfactory → 1.0, all US → 0.0)
    #   If no PPM yet (Stage 1 student), defaults to 1.0 (no failure signal).
    out["perf_rate_s1"] = (1.0 - out["ppm_us_rate"]).clip(0.0, 1.0)

    # perf_quality_s1: RPD progress quality score
    #   = 1 − clip(rpd_delay_days / 365, 0, 1)
    #   On-time or early RPD → 1.0; 1-year overdue → 0.0; not yet due → 1.0
    rpd_delay = out["rpd_delay_days"].fillna(0).clip(lower=0)
    out["perf_quality_s1"] = (1.0 - (rpd_delay / 365.0).clip(0.0, 1.0))

    # months_enrolled: already in the DB query, just fill NaN
    out["months_enrolled"] = out["months_enrolled"].fillna(0)

    # ── Stage 3 proxy features (DATATRAIN → UCI-compatible [0,1] space) ──────
    # perf_rate_s2 / perf_quality_s2: examiner average score normalised to [0,1]
    #   UCI grade scale 0–20; examiner scale 0–5  → scale ×4 to match
    #   Both features use the same signal; they're kept separate in case
    #   future model improvements add distinct measures per feature.
    exam = out["examiner_avg_score"].fillna(0).clip(0, 5)
    out["perf_rate_s2"]    = (exam / 5.0).clip(0.0, 1.0)
    out["perf_quality_s2"] = out["perf_rate_s2"]

    # perf_trend: improvement from 1st cycle to 2nd cycle
    #   Positive = improving  (examiner better than PPM implied)
    #   Negative = declining  (examiner worse)
    out["perf_trend"] = (out["perf_rate_s2"] - out["perf_rate_s1"]).clip(-1.0, 1.0)

    # ── Fill remaining nulls ──────────────────────────────────────────────────
    out["examiner_avg_score"] = exam
    out["entry_gpa"]          = out["entry_gpa"].fillna(0.0)

    return out, encoders


# ── NaN-safe scalar helper ────────────────────────────────────────────────────
def _s(val, default=0):
    """Return val as a Python float, or default if val is NaN/None/non-numeric."""
    if val is None:
        return default
    try:
        f = float(val)
        return default if (f != f) else f   # NaN check: NaN != NaN is True
    except (TypeError, ValueError):
        return default


def _determine_stage(row: pd.Series) -> int:
    """
    Determine which stage a student qualifies for:
      Stage 3: has at least one examiner report
      Stage 2: has PPM records OR any milestone is overdue (RPD / Publication)
      Stage 1: truly early — just enrolled, all milestones still in the future

    A student with overdue milestones but no PPM records is still in Stage 2
    because progress indicators are now available and should be factored in.
    """
    if _s(row.get("examiner_avg_score")) > 0:
        return 3
    if _s(row.get("ppm_total")) > 0:
        return 2
    # Any milestone overdue → enough progress data for Stage 2 rule-based
    if _s(row.get("rpd_delay_days")) > 0:
        return 2
    if _s(row.get("pub_overdue_days")) > 0:
        return 2
    return 1


# ── Scoring constants (evidence-based, see research notes) ───────────────────
#
# Sources:
#   - Bair & Haworth (2004) meta-synthesis, 118 studies on doctoral attrition
#   - Council of Graduate Schools PhD Completion Project (57% 10-yr completion)
#   - PLOS ONE: "What Took Them So Long?" PhD delays study
#   - Malaysian postgrad study: avg PhD 4.5 yrs, Master 2.69 yrs (vs 3/2 yr norm)
#
# Evidence-based rationale:
#   PPM Unsatisfactory — STRONGEST predictor; 3 US = termination (university policy)
#     1 US = 35 pts  (1/3 of termination threshold — significant early warning)
#     2 US = 70 pts  (2/3 of termination threshold — critical)
#
#   RPD overdue — MODERATE predictor of DELAY (not so much dropout directly).
#     Malaysian policy: RPD within 12–18 months of enrollment.
#     Normalize over 365 days (1 year) → max 30 pts.
#     This is more lenient for short delays (30 days late = 2.5 pts) but still
#     reaches full weight at 1 year overdue, matching policy expectations.
#     Previous: 180-day basis was too aggressive.
#
#   Publication overdue — WEAKEST predictor during candidature.
#     External peer-review cycle = 6–12 months; delays often beyond student's control.
#     Research shows most dropouts occur BEFORE the publication stage.
#     Normalize over 365 days → max 15 pts (reduced from 20).
#     Reflects real-world review timelines; still flags severely overdue students.
#
# Thresholds:
#   High ≥ 60  (2 US alone = 70; or 1 US + ~180 days RPD overdue)
#   Medium ≥ 25 (1 US alone = 35; or RPD ~1 year overdue without PPM issues)
#   Low < 25

_PPM_US1_PTS   = 35.0   # 1 Unsatisfactory PPM
_PPM_US2_PTS   = 70.0   # 2+ Unsatisfactory PPM (2/3 of termination threshold)
_RPD_MAX_PTS   = 30.0   # RPD delay max contribution
_RPD_NORM_DAYS = 365    # normalise RPD over 1 year (Malaysian policy: RPD ≤ 18 months)
_PUB_MAX_PTS   = 15.0   # Publication overdue max contribution (weak predictor)
_PUB_NORM_DAYS = 365    # normalise pub over 1 year (peer-review cycle reality)

_S2_HIGH   = 60.0
_S2_MEDIUM = 25.0


# ── Rule-based prediction for Stage 2 ────────────────────────────────────────
def _rule_based_stage2(row: pd.Series) -> dict:
    """
    Rule-based risk prediction for Stage 2 students.
    Evidence-based weights derived from postgraduate attrition literature.

    Scoring (0–100):
      ppm_us_count  : 1 → 35pts | ≥2 → 70pts  (policy: 3 US = termination)
      rpd_delay     : min(days/365, 1) × 30pts  (gate milestone; 1-yr norm)
      pub_overdue   : min(days/365, 1) × 15pts  (weak predictor; 1-yr norm)
    Thresholds: High ≥ 60 | Medium ≥ 25 | Low < 25
    """
    score = 0.0
    factors = []

    # ── PPM US component (strongest predictor — 3 US = automatic termination) ──
    us = int(_s(row.get("ppm_us_count")))
    if us >= 2:
        score += _PPM_US2_PTS
        factors.append(f"{us} Unsatisfactory PPM results (termination risk)")
    elif us == 1:
        score += _PPM_US1_PTS
        factors.append("1 Unsatisfactory PPM result")

    # ── RPD delay component (moderate predictor; gate milestone) ──────────────
    rpd           = _s(row.get("rpd_delay_days"))
    rpd_completed = _s(row.get("rpd_completed"))   # 1 = actual_date is set
    if rpd > 0:
        rpd_pts = min(rpd / _RPD_NORM_DAYS, 1.0) * _RPD_MAX_PTS
        score += rpd_pts
        factors.append(f"RPD overdue by {int(rpd)} days")
    elif rpd_completed and rpd < -7:
        # Only show when RPD is actually submitted (actual_date set), not just "not yet due"
        factors.append("RPD completed ahead of schedule")

    # ── Publication progress component (weak predictor; external factors) ─────
    pub_accepted = int(_s(row.get("pub_accepted_count")))
    pub_required = int(_s(row.get("pub_required"), default=1)) or 1
    pub_overdue  = _s(row.get("pub_overdue_days"))
    pub_deficit  = max(pub_required - pub_accepted, 0)

    if pub_deficit > 0 and pub_overdue > 0:
        pub_pts = min(pub_overdue / _PUB_NORM_DAYS, 1.0) * _PUB_MAX_PTS
        score += pub_pts
        factors.append(
            f"Publication overdue by {int(pub_overdue)} days "
            f"({pub_accepted}/{pub_required} papers accepted)"
        )
    elif pub_deficit > 0 and pub_overdue == 0:
        sub = int(_s(row.get("pub_submitted_count")))
        if sub > 0:
            factors.append(f"Publication in progress ({sub} submitted, {pub_accepted} accepted/{pub_required} required)")
        else:
            factors.append(f"No publications submitted yet ({pub_accepted}/{pub_required} required)")
    else:
        factors.append(f"Publication requirement met ({pub_accepted}/{pub_required} accepted)")

    # Part-time / work burden (informational)
    if row.get("is_part_time", 0):
        factors.append("Part-time student (longer programme duration)")
    wh = _s(row.get("weekly_work_hours"))
    if wh >= 20:
        factors.append(f"High external workload ({int(wh)} hrs/week)")
    elif wh > 0:
        factors.append(f"External work ({int(wh)} hrs/week)")

    if not factors:
        factors.append("No major risk indicators detected")

    score = min(score, 100.0)
    if score >= _S2_HIGH:
        label = "High"
    elif score >= _S2_MEDIUM:
        label = "Medium"
    else:
        label = "Low"

    return {"risk_label": label, "risk_score": round(score, 2), "factors": factors}


# ── Rule-based prediction for Stage 3 ────────────────────────────────────────
def _rule_based_stage3(row: pd.Series) -> dict:
    """
    Rule-based risk prediction for Stage 3 students (have examiner reports).
    Builds on Stage 2 rules and adds examiner score + thesis seminar delay.

    Scoring (0–100):
      Stage 2 base:        up to 60pts (ppm + rpd, capped)
      examiner_avg_score:  < 2.5 → +30pts | 2.5–3.5 → +15pts
      thesis_seminar_delay: > 90d → +20pts | 30–90d → +10pts
    Thresholds: High ≥ 60 | Medium ≥ 30 | Low < 30
    """
    # Start from Stage 2 base
    s2 = _rule_based_stage2(row)
    score = min(s2["risk_score"], 60.0)   # cap Stage 2 contribution at 60
    factors = [f for f in s2["factors"] if "No major" not in f]

    # Examiner score component
    exam = _s(row.get("examiner_avg_score"))
    if exam > 0:
        if exam < 2.5:
            score += 30.0
            factors.append(f"Low examiner avg score ({exam:.1f}/5)")
        elif exam < 3.5:
            score += 15.0
            factors.append(f"Moderate examiner avg score ({exam:.1f}/5)")
        else:
            factors.append(f"Good examiner avg score ({exam:.1f}/5)")

    # Thesis seminar delay
    ts_delay = _s(row.get("thesis_seminar_delay"))
    if ts_delay > 90:
        score += 20.0
        factors.append(f"Thesis seminar overdue by {int(ts_delay)} days")
    elif ts_delay > 30:
        score += 10.0
        factors.append(f"Thesis seminar delayed by {int(ts_delay)} days")

    if not factors:
        factors.append("No major risk indicators detected")

    score = min(score, 100.0)
    if score >= 60.0:
        label = "High"
    elif score >= 30.0:
        label = "Medium"
    else:
        label = "Low"

    return {"risk_label": label, "risk_score": round(score, 2), "factors": factors}


# ══════════════════════════════════════════════════════════════════════════════
# PART 3: Training
# ══════════════════════════════════════════════════════════════════════════════

def _train_rf(X_train: np.ndarray, y_train: np.ndarray, tag: str) -> tuple[RandomForestClassifier, dict]:
    """Train one RF and return (model, metrics_dict)."""
    model = RandomForestClassifier(**RF_PARAMS)
    model.fit(X_train, y_train)

    metrics: dict = {}

    # Cross-val on training data (5-fold)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(model, X_train, y_train, cv=cv, scoring="f1_weighted", n_jobs=-1)
    metrics["cv_f1_mean"]  = round(float(cv_scores.mean()), 4)
    metrics["cv_f1_std"]   = round(float(cv_scores.std()),  4)

    # Train-set metrics
    y_pred  = model.predict(X_train)
    y_proba = model.predict_proba(X_train)[:, 1] if len(model.classes_) == 2 else None

    metrics["train_accuracy"]  = round(float(accuracy_score(y_train, y_pred)),   4)
    metrics["train_f1"]        = round(float(f1_score(y_train, y_pred, average="weighted")), 4)
    metrics["train_precision"] = round(float(precision_score(y_train, y_pred, average="weighted", zero_division=0)), 4)
    metrics["train_recall"]    = round(float(recall_score(y_train, y_pred, average="weighted", zero_division=0)), 4)
    if y_proba is not None:
        metrics["train_auc"] = round(float(roc_auc_score(y_train, y_proba)), 4)

    metrics["n_samples"]    = int(len(X_train))
    metrics["n_features"]   = int(X_train.shape[1])
    metrics["dropout_rate"] = round(float(y_train.mean()), 4)

    logger.info(f"[RF:{tag}] acc={metrics['train_accuracy']}, f1={metrics['train_f1']}, cv_f1={metrics['cv_f1_mean']}±{metrics['cv_f1_std']}")
    return model, metrics


def _feature_importance(model: RandomForestClassifier, feature_names: list) -> dict:
    return dict(sorted(
        zip(feature_names, model.feature_importances_),
        key=lambda x: x[1], reverse=True
    ))


def pretrain_on_external_data() -> Optional[dict[int, tuple[RandomForestClassifier, dict]]]:
    """
    Pre-train ALL THREE stage RF models on data.csv (UCI dataset).

    Stage 1: enrollment features only (Stage 1 features)
    Stage 2: + 1st-semester proxy features (perf_rate_s1, perf_quality_s1, months_enrolled)
    Stage 3: + 2nd-semester proxy features (perf_rate_s2, perf_quality_s2, perf_trend)

    Returns dict {stage: (model, metrics)} or None if data not available.
    """
    ext = _load_external_data()
    if ext is None:
        return None

    results: dict[int, tuple[RandomForestClassifier, dict]] = {}
    for stage, features, tag in [
        (1, STAGE1_FEATURES, "S1-ext"),
        (2, STAGE2_FEATURES, "S2-ext"),
        (3, STAGE3_FEATURES, "S3-ext"),
    ]:
        X = ext[features].fillna(0).values
        y = ext["is_delayed"].values
        model, metrics = _train_rf(X, y, tag)
        metrics["source"] = f"data.csv (UCI) — Stage {stage}"
        results[stage] = (model, metrics)
        logger.info(f"[RF] Stage {stage} pre-trained on UCI: acc={metrics['train_accuracy']}, "
                    f"auc={metrics.get('train_auc', 'N/A')}, n={len(X)}")

    return results


def train_all_stages(df_encoded: pd.DataFrame) -> dict:
    """
    Fine-tune RF stages on our DB students that have graduation_outcome labels.
    Skips training if:
      - fewer than 10 labeled rows, OR
      - only one class present (all graduated or all delayed) — model would be useless.
    Returns dict of {stage: (model, metrics)} for stages with sufficient data.
    """
    labeled = df_encoded[df_encoded["is_delayed"].notna()].copy()
    labeled["is_delayed"] = labeled["is_delayed"].astype(int)

    results = {}

    for stage, features, tag in [
        (1, STAGE1_FEATURES, "S1-db"),
        (2, STAGE2_FEATURES, "S2-db"),
        (3, STAGE3_FEATURES, "S3-db"),
    ]:
        stage_df = labeled.dropna(subset=features)
        if len(stage_df) < 10:
            logger.warning(f"[RF:{tag}] Only {len(stage_df)} labeled rows — skipping.")
            results[stage] = None
            continue
        y = stage_df["is_delayed"].values
        # Require BOTH classes — single-class training produces a useless model
        if len(np.unique(y)) < 2:
            logger.warning(f"[RF:{tag}] Only one class (dropout_rate={y.mean():.2%}) — skipping DB fine-tune.")
            results[stage] = None
            continue
        X = stage_df[features].fillna(0).values
        model, metrics = _train_rf(X, y, tag)
        results[stage] = (model, metrics)

    return results


# ══════════════════════════════════════════════════════════════════════════════
# PART 4: Inference
# ══════════════════════════════════════════════════════════════════════════════

def _predict_student(row: pd.Series, models: dict, stage: int) -> dict:
    """
    Run prediction for one student using the highest available stage model.
    Falls back to lower stage if the target stage model is missing.
    """
    feature_map = {1: STAGE1_FEATURES, 2: STAGE2_FEATURES, 3: STAGE3_FEATURES}

    # Try from student's stage down to 1
    for s in range(stage, 0, -1):
        model = models.get(s)
        if model is None:
            continue
        features = feature_map[s]
        X = row[features].fillna(0).values.reshape(1, -1)
        proba = model.predict_proba(X)[0]
        classes = list(model.classes_)
        # Handle single-class models (all graduates or all dropouts)
        if 1 not in classes:
            p_dropout = 0.0          # model only saw graduates → no dropout risk
        elif len(classes) == 1:
            p_dropout = float(proba[0])   # model only saw dropouts
        else:
            p_dropout = float(proba[classes.index(1)])
        return {
            "stage":       s,
            "risk_label":  _proba_to_label(p_dropout),
            "risk_score":  _proba_to_score(p_dropout),
            "confidence":  round(float(proba.max()), 4),
            "p_dropout":   round(p_dropout, 4),
        }

    # Fallback: no model available
    return {"stage": 0, "risk_label": "Unknown", "risk_score": 0.0, "confidence": 0.0, "p_dropout": 0.0}


def generate_risk_factors_rf(row: pd.Series, stage: int) -> list[str]:
    """
    Generate human-readable risk factors for ALL stages (RF-based).
    Since Stage 2/3 now use RF instead of rule-based, this function
    translates the proxy features back into readable explanations.
    """
    factors = []

    # ── Stage 1 factors (enrollment profile) ─────────────────────────────────
    if row.get("is_part_time", 0):
        factors.append("Part-time student (longer programme duration)")
    wh = _s(row.get("weekly_work_hours"))
    if wh >= 20:
        factors.append(f"High external workload ({int(wh)} hrs/week)")
    elif wh > 0:
        factors.append(f"External work ({int(wh)} hrs/week)")
    if row.get("is_cross_discipline", 0):
        factors.append("Cross-discipline study (added academic challenge)")
    if not row.get("in_research_group", 1):
        factors.append("Not in a research group")
    fs = _s(row.get("family_support"), default=3)
    if fs <= 2:
        factors.append(f"Low family support (score {int(fs)}/5)")
    gpa = _s(row.get("entry_gpa"))
    if 0 < gpa < 2.5:
        factors.append(f"Low entry GPA ({gpa:.2f})")

    # ── Stage 2 factors (progress indicators, if available) ───────────────────
    if stage >= 2:
        rpd = _s(row.get("rpd_delay_days"))
        if rpd > 0:
            factors.append(f"RPD overdue by {int(rpd)} days")
        elif _s(row.get("rpd_completed")) and rpd < -7:
            factors.append("RPD completed ahead of schedule")

        us = int(_s(row.get("ppm_us_count")))
        if us >= 2:
            factors.append(f"{us} Unsatisfactory PPM results (termination risk)")
        elif us == 1:
            factors.append("1 Unsatisfactory PPM result")

        pub_overdue = _s(row.get("pub_overdue_days"))
        pub_deficit = max(
            int(_s(row.get("pub_required"), default=1)) - int(_s(row.get("pub_accepted_count"))), 0
        )
        if pub_deficit > 0 and pub_overdue > 0:
            pub_accepted = int(_s(row.get("pub_accepted_count")))
            pub_required = int(_s(row.get("pub_required"), default=1)) or 1
            factors.append(
                f"Publication overdue by {int(pub_overdue)} days "
                f"({pub_accepted}/{pub_required} papers accepted)"
            )

    # ── Stage 3 factors (examiner assessment, if available) ───────────────────
    if stage >= 3:
        exam = _s(row.get("examiner_avg_score"))
        if exam > 0:
            if exam < 2.5:
                factors.append(f"Low examiner avg score ({exam:.1f}/5)")
            elif exam < 3.5:
                factors.append(f"Moderate examiner avg score ({exam:.1f}/5)")
            else:
                factors.append(f"Good examiner avg score ({exam:.1f}/5)")
        ts = _s(row.get("thesis_seminar_delay"))
        if ts > 90:
            factors.append(f"Thesis seminar overdue by {int(ts)} days")
        elif ts > 30:
            factors.append(f"Thesis seminar delayed by {int(ts)} days")

    if not factors:
        factors.append("No major risk indicators detected")
    return factors


# ══════════════════════════════════════════════════════════════════════════════
# PART 5: Full Pipeline Entry Point
# ══════════════════════════════════════════════════════════════════════════════

def train_and_predict_rf() -> dict:
    """
    Full multi-stage RF pipeline:
      1. Pre-train Stage 1 on data.csv (if not already trained / on first run)
      2. Fine-tune all stages on our DB students (if labeled data exists)
      3. Run inference on all students using their highest applicable stage
      4. Store predictions + log to MLflow
    Returns summary dict.
    """
    logger.info("[RF] Starting multi-stage RF pipeline...")
    os.makedirs(_MODEL_DIR, exist_ok=True)

    # ── Setup MLflow ──────────────────────────────────────────────────────────
    mlflow_ok = False
    try:
        mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
        mlflow.set_experiment(settings.MLFLOW_EXPERIMENT_NAME + "_RF")
        mlflow_ok = True
    except Exception as e:
        logger.warning(f"[RF] MLflow unavailable: {e}")

    all_metrics: dict = {}

    # ── Pre-train ALL stages on UCI external data ─────────────────────────────
    # All three RF models (Stage 1/2/3) are pre-trained on data.csv.
    # Stage 2/3 use 1st/2nd-semester UCI columns as academic-progress proxies.
    ext_results = pretrain_on_external_data()
    models: dict[int, RandomForestClassifier] = {}
    _STAGE_PATHS = {1: _RF_S1_PATH, 2: _RF_S2_PATH, 3: _RF_S3_PATH}

    if ext_results:
        for stage, (model, metrics) in ext_results.items():
            models[stage] = model
            all_metrics[f"stage{stage}_external"] = metrics
            joblib.dump(model, _STAGE_PATHS[stage])
            logger.info(f"[RF] Stage {stage} UCI pre-trained model saved.")
    else:
        # Fall back to loading from disk if data.csv not available
        for stage, path in _STAGE_PATHS.items():
            if os.path.exists(path):
                models[stage] = joblib.load(path)
                logger.info(f"[RF] Stage {stage} loaded from local joblib.")

    # ── Extract + encode DB features ─────────────────────────────────────────
    df_raw = _extract_db_features()
    if df_raw.empty:
        return {"status": "skipped", "reason": "no student data"}

    # Fit or load encoders
    if os.path.exists(_ENC_PATH):
        encoders = joblib.load(_ENC_PATH)
        df_enc, _ = _encode_features(df_raw, encoders=encoders)
    else:
        df_enc, encoders = _encode_features(df_raw, encoders=None)
        joblib.dump(encoders, _ENC_PATH)

    # ── Fine-tune on DB labeled students ─────────────────────────────────────
    # Stage 1 UCI pre-trained model is the primary model.
    # Only overwrite it with a DB fine-tuned version when real graduation data exists.
    db_results = train_all_stages(df_enc)
    for stage, result in db_results.items():
        if result is not None:
            model, metrics = result
            models[stage] = model
            all_metrics[f"stage{stage}_db"] = metrics
            path = {1: _RF_S1_PATH, 2: _RF_S2_PATH, 3: _RF_S3_PATH}[stage]
            joblib.dump(model, path)
            logger.info(f"[RF] Stage {stage} DB fine-tuned model saved.")

    # Load any stage models that weren't just trained (shouldn't happen normally)
    for stage, path in _STAGE_PATHS.items():
        if stage not in models and os.path.exists(path):
            models[stage] = joblib.load(path)
            logger.info(f"[RF] Stage {stage} loaded from local joblib (fallback).")

    if not models:
        return {"status": "error", "reason": "No RF models available"}

    # ── Inference on all students ─────────────────────────────────────────────
    # ALL stages now use Random Forest (pre-trained on UCI data).
    # Stage 1: enrollment features only
    # Stage 2: + PPM/RPD proxy features (perf_rate_s1, perf_quality_s1)
    # Stage 3: + examiner proxy features (perf_rate_s2, perf_quality_s2, perf_trend)
    predictions = []
    stage_counts = {1: 0, 2: 0, 3: 0}

    for _, row in df_enc.iterrows():
        stage = _determine_stage(row)
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

        pred    = _predict_student(row, models, stage)
        factors = generate_risk_factors_rf(row, stage)

        predictions.append({
            "student_id":       int(row["student_id"]),
            "risk_score":       pred["risk_score"],
            "risk_label":       pred["risk_label"],
            "cluster_id":       pred["stage"],   # actual stage used (may fall back)
            "key_risk_factors": json.dumps(factors),
            "stage":            pred["stage"],
            "confidence":       pred["confidence"],
        })

    # ── Store to DB ───────────────────────────────────────────────────────────
    _store_rf_predictions(predictions)

    distribution = {}
    for p in predictions:
        distribution[p["risk_label"]] = distribution.get(p["risk_label"], 0) + 1

    total  = len(predictions)
    high   = distribution.get("High",   0)
    medium = distribution.get("Medium", 0)
    low    = distribution.get("Low",    0)

    # ── MLflow logging ────────────────────────────────────────────────────────
    if mlflow_ok:
        try:
            with mlflow.start_run(run_name=f"rf_multistage_{datetime.now().strftime('%Y%m%d_%H%M%S')}") as run:
                mlflow.log_param("model_type",    "RandomForest")
                mlflow.log_param("n_estimators",  RF_PARAMS["n_estimators"])
                mlflow.log_param("max_depth",     RF_PARAMS["max_depth"])
                mlflow.log_param("stages_active", list(models.keys()))

                mlflow.log_metric("total_students",    total)
                mlflow.log_metric("high_risk_count",   high)
                mlflow.log_metric("medium_risk_count", medium)
                mlflow.log_metric("low_risk_count",    low)
                for s, cnt in stage_counts.items():
                    mlflow.log_metric(f"stage{s}_count", cnt)

                for key, metrics in all_metrics.items():
                    for m, v in metrics.items():
                        if isinstance(v, (int, float)):
                            mlflow.log_metric(f"{key}_{m}", v)

                # Log feature importances for each stage
                for stage, model in models.items():
                    features = {1: STAGE1_FEATURES, 2: STAGE2_FEATURES, 3: STAGE3_FEATURES}[stage]
                    imp = _feature_importance(model, features)
                    top3 = list(imp.items())[:3]
                    logger.info(f"[RF] Stage {stage} top features: {top3}")
                    for feat, val in list(imp.items())[:5]:
                        mlflow.log_metric(f"stage{stage}_imp_{feat}", round(float(val), 4))

        except Exception as e:
            logger.warning(f"[RF] MLflow logging failed: {e}")

    logger.info(f"[RF] Pipeline complete. Stages used: {stage_counts}. Distribution: {distribution}")
    return {
        "status":        "success",
        "model":         "RandomForest",
        "total_students": total,
        "distribution":  distribution,
        "stage_counts":  stage_counts,
        "metrics":       all_metrics,
    }


def _store_rf_predictions(predictions: list[dict]) -> None:
    """Upsert RF predictions into student_risk_prediction table."""
    db = SyncSessionLocal()
    try:
        now = datetime.now()
        for p in predictions:
            db.execute(text("""
                INSERT INTO student_risk_prediction
                    (student_id, risk_score, risk_label, cluster_id,
                     key_risk_factors, predicted_at)
                VALUES
                    (:sid, :score, :label, :cluster, :factors, :now)
                ON DUPLICATE KEY UPDATE
                    risk_score       = VALUES(risk_score),
                    risk_label       = VALUES(risk_label),
                    cluster_id       = VALUES(cluster_id),
                    key_risk_factors = VALUES(key_risk_factors),
                    predicted_at     = VALUES(predicted_at)
            """), {
                "sid":     p["student_id"],
                "score":   p["risk_score"],
                "label":   p["risk_label"],
                "cluster": p["stage"],
                "factors": p["key_risk_factors"],
                "now":     now,
            })
        db.commit()
        logger.info(f"[RF] Stored {len(predictions)} RF predictions.")
    except Exception as e:
        db.rollback()
        logger.error(f"[RF] Failed to store predictions: {e}")
        raise
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# PART 6: Query helpers (same interface as ml_service.py)
# ══════════════════════════════════════════════════════════════════════════════

def get_stage_summary() -> dict:
    """Return how many students are in each prediction stage."""
    db = SyncSessionLocal()
    try:
        rows = db.execute(text("""
            SELECT cluster_id AS stage, COUNT(*) AS cnt
            FROM student_risk_prediction
            GROUP BY cluster_id
        """)).fetchall()
        return {f"stage_{r.stage}": r.cnt for r in rows}
    finally:
        db.close()
