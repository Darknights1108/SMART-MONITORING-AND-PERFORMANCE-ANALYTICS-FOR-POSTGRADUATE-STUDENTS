"""
Multi-Stage Risk Prediction Service
-------------------------------------
Stage 1 — Random Forest pre-trained on UCI dataset (3630 students).
           Uses enrollment features available from day 1.

Stage 2 — Simple rule-based detection using PPM results + RPD delay.
           Triggered once the student has PPM records or an overdue milestone.

Stage 3 — Simple rule-based detection using examiner score + thesis seminar delay.
           Triggered once the student has an examiner report.

Rationale for keeping Stage 2/3 rule-based:
  - No public postgraduate dataset with milestone/supervisor data exists.
  - University policy (3 US PPM = termination) is itself ground truth.
  - Simple, explainable rules are appropriate for FYP scope.
  - Stage 1 ML is validated on UCI holdout (Acc=70.8%, AUC=77.3%).
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

import joblib
try:
    import mlflow
    import mlflow.sklearn
    _MLFLOW_AVAILABLE = True
except ImportError:
    mlflow = None
    _MLFLOW_AVAILABLE = False
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
from sklearn.preprocessing import LabelEncoder
from sqlalchemy import text

from app.config import get_settings
from app.database import SyncSessionLocal

logger   = logging.getLogger(__name__)
settings = get_settings()

# ── Paths ──────────────────────────────────────────────────────────────────────
_MODEL_DIR  = os.path.join(os.path.dirname(__file__), "..", "ml_models")
_DATA_CSV   = "/app/data.csv"
_RF_S1_PATH = os.path.join(_MODEL_DIR, "rf_stage1.joblib")
_ENC_PATH   = os.path.join(_MODEL_DIR, "rf_encoders.joblib")

# ── Stage 1 features (enrollment, available day 1) ────────────────────────────
STAGE1_FEATURES = [
    "age_at_enrollment",    # numeric
    "entry_gpa",            # numeric
    "weekly_work_hours",    # numeric
    "family_support",       # numeric 1-5
    "gender_enc",           # Male=0, Female=1
    "is_part_time",         # Part-time=1
    "has_external_work",    # binary
    "in_research_group",    # binary
    "is_cross_discipline",  # binary
    "is_phd",               # PhD=1
    "region_enc",           # encoded
    "discipline_group_enc", # encoded
    "funding_enc",          # encoded
    "marital_status_enc",   # encoded
]

RF_PARAMS = dict(
    n_estimators=200, max_depth=8, min_samples_leaf=5,
    class_weight="balanced", random_state=42, n_jobs=-1,
)


# ── NaN-safe helper ────────────────────────────────────────────────────────────
def _s(val, default=0):
    """Return float value or default if None/NaN."""
    if val is None:
        return default
    try:
        f = float(val)
        return default if (f != f) else f
    except (TypeError, ValueError):
        return default


# ══════════════════════════════════════════════════════════════════════════════
# PART 1 — Stage 1 RF (trained on UCI data)
# ══════════════════════════════════════════════════════════════════════════════

def _load_uci_data() -> Optional[pd.DataFrame]:
    """Load UCI data.csv, map columns to Stage 1 feature names."""
    if not os.path.exists(_DATA_CSV):
        logger.warning(f"[RF] data.csv not found at {_DATA_CSV}")
        return None

    df = pd.read_csv(_DATA_CSV, sep=";")
    df = df[df["Target"].isin(["Graduate", "Dropout"])].copy()
    df["is_delayed"] = (df["Target"] == "Dropout").astype(int)

    df["is_part_time"]        = (df["Daytime/evening attendance\t"] == 0).astype(float)
    df["has_external_work"]   = df["Debtor"].astype(float)
    df["in_research_group"]   = 0.0
    df["is_cross_discipline"] = 0.0
    df["is_phd"]              = 0.0
    df["age_at_enrollment"]   = pd.to_numeric(df["Age at enrollment"], errors="coerce").fillna(22)
    df["entry_gpa"]           = ((pd.to_numeric(df["Admission grade"], errors="coerce").fillna(130) - 95) / 95 * 4).clip(0, 4)
    df["weekly_work_hours"]   = np.where(df["has_external_work"] == 1, 20.0, 0.0)
    df["family_support"]      = 3.0
    df["gender_enc"]          = df["Gender"].astype(float)
    df["region_enc"]          = df["International"].astype(float)
    df["discipline_group_enc"] = 0.0
    df["funding_name"]        = df["Scholarship holder"].map({1: "Full Scholarship", 0: "Self-funded"})
    df["funding_enc"]         = df["Scholarship holder"].astype(float)
    _ms = {1: "Single", 2: "Married", 3: "Widowed", 4: "Divorced", 5: "Married", 6: "Divorced"}
    df["marital_status"]      = df["Marital status"].map(_ms).fillna("Single")
    _me = {"Divorced": 0, "Married": 1, "Single": 2, "Widowed": 3}
    df["marital_status_enc"]  = df["marital_status"].map(_me).fillna(2).astype(float)

    out = df[STAGE1_FEATURES + ["is_delayed"]].fillna(0)
    logger.info(f"[RF] UCI data: {len(out)} rows, dropout={out['is_delayed'].mean():.1%}")
    return out


def train_stage1_on_uci() -> Optional[tuple[RandomForestClassifier, dict]]:
    """Train Stage 1 RF on full UCI dataset. Returns (model, metrics)."""
    data = _load_uci_data()
    if data is None:
        return None

    X = data[STAGE1_FEATURES].values
    y = data["is_delayed"].values

    model = RandomForestClassifier(**RF_PARAMS)
    model.fit(X, y)

    y_pred  = model.predict(X)
    y_proba = model.predict_proba(X)[:, 1]
    cv      = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_acc  = cross_val_score(model, X, y, cv=cv, scoring="accuracy")

    metrics = {
        "source":          "UCI data.csv (3630 students, full training set)",
        "n_samples":       int(len(X)),
        "dropout_rate":    round(float(y.mean()), 4),
        "train_accuracy":  round(float(accuracy_score(y, y_pred)), 4),
        "train_auc":       round(float(roc_auc_score(y, y_proba)), 4),
        "cv_accuracy_mean": round(float(cv_acc.mean()), 4),
        "cv_accuracy_std":  round(float(cv_acc.std()),  4),
    }
    logger.info(f"[RF] Stage 1 trained: acc={metrics['train_accuracy']}, "
                f"cv={metrics['cv_accuracy_mean']}±{metrics['cv_accuracy_std']}")
    return model, metrics


def evaluate_stage1_holdout() -> dict:
    """
    80/20 stratified holdout evaluation of Stage 1 RF on UCI data.
    Returns ground-truth-validated metrics for FYP reporting.
    """
    data = _load_uci_data()
    if data is None:
        return {"available": False}

    X = data[STAGE1_FEATURES].values
    y = data["is_delayed"].values

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )
    model = RandomForestClassifier(**RF_PARAMS)
    model.fit(X_tr, y_tr)

    y_pred  = model.predict(X_te)
    y_proba = model.predict_proba(X_te)[:, 1]
    cv      = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_acc  = cross_val_score(model, X_tr, y_tr, cv=cv, scoring="accuracy")
    cv_auc  = cross_val_score(model, X_tr, y_tr, cv=cv, scoring="roc_auc")

    from sklearn.metrics import confusion_matrix
    tn, fp, fn, tp = confusion_matrix(y_te, y_pred).ravel()

    result = {
        "available":        True,
        "stage":            1,
        "description":      "Stage 1 — RF trained on UCI enrollment features",
        "n_train":          int(len(X_tr)),
        "n_test":           int(len(X_te)),
        "n_features":       len(STAGE1_FEATURES),
        "test_accuracy":    round(float(accuracy_score(y_te, y_pred)), 4),
        "test_auc_roc":     round(float(roc_auc_score(y_te, y_proba)), 4),
        "test_f1":          round(float(f1_score(y_te, y_pred, average="weighted")), 4),
        "test_precision":   round(float(precision_score(y_te, y_pred, average="weighted", zero_division=0)), 4),
        "test_recall":      round(float(recall_score(y_te, y_pred, average="weighted", zero_division=0)), 4),
        "confusion_matrix": {"TP": int(tp), "TN": int(tn), "FP": int(fp), "FN": int(fn)},
        "cv_accuracy_mean": round(float(cv_acc.mean()), 4),
        "cv_accuracy_std":  round(float(cv_acc.std()),  4),
        "cv_auc_mean":      round(float(cv_auc.mean()), 4),
        "cv_auc_std":       round(float(cv_auc.std()),  4),
        "classification_report": classification_report(
            y_te, y_pred, target_names=["Graduate", "Dropout"]
        ),
        "feature_importances": dict(sorted(
            zip(STAGE1_FEATURES, model.feature_importances_),
            key=lambda x: x[1], reverse=True
        )),
        "validation_note": (
            "Validated on UCI Student Dropout dataset (Polytechnic Institute of Portalegre, "
            "Portugal). 3630 students with known Graduate/Dropout outcomes. "
            "Limitation: undergraduate data; Stage 1 enrollment features have partial "
            "transferability to postgraduate context."
        ),
    }
    logger.info(
        f"[RF] Stage 1 holdout: Acc={result['test_accuracy']}, "
        f"AUC={result['test_auc_roc']}, F1={result['test_f1']}"
    )
    return result


# ══════════════════════════════════════════════════════════════════════════════
# PART 2 — Stage 2 & 3 Rule-Based Detection
# ══════════════════════════════════════════════════════════════════════════════
#
# Design rationale:
#   No public postgraduate dataset with PPM/milestone/examiner data exists.
#   University policy (3× US PPM = termination) is itself the ground truth.
#   Simple threshold rules are transparent, explainable, and policy-aligned.
#
# Stage 2 rules — PRE-DEADLINE early warning (fire BEFORE deadline is missed):
#   HIGH   → 2+ Unsatisfactory PPM  (termination imminent)
#             OR 1 US PPM + RPD due within 30 days (compounding risk)
#             OR RPD due within 30 days and not yet submitted
#   MEDIUM → 1 Unsatisfactory PPM
#             OR RPD due within 31–60 days and not yet submitted
#             OR Publication still short + pub deadline within 30 days
#   LOW    → everything else
#
# Stage 3 rules — PRE-DEADLINE early warning, no Examiner score:
#   HIGH   → Thesis seminar due within 30 days and not yet done
#             OR Stage 2 = High (carry forward)
#   MEDIUM → Thesis seminar due within 31–60 days and not yet done
#             OR Stage 2 = Medium (carry forward)
#   LOW    → everything else
#
# Convention for date fields (rpd_delay_days, pub_days_from_deadline, thesis_seminar_delay):
#   negative = days until deadline (future)   e.g. -20 = due in 20 days
#   positive = days past deadline (overdue)   e.g.  30 = 30 days overdue
#   0        = no milestone / completed on time
#   LOW    → examiner avg ≥ 3.5 and no significant delays

def _detect_stage2(row: pd.Series) -> dict:
    """
    Stage 2 pre-deadline early warning.
    Priority: PPM (result) > RPD (deadline) > Publication (deadline).
    Date fields: negative = days until deadline, positive = days overdue.
    """
    factors = []

    us            = int(_s(row.get("ppm_us_count")))
    rpd           = _s(row.get("rpd_delay_days"))
    rpd_completed = bool(_s(row.get("rpd_completed")))
    pub_accepted  = int(_s(row.get("pub_accepted_count")))
    pub_required  = int(_s(row.get("pub_required"), default=1)) or 1
    pub_days      = _s(row.get("pub_days_from_deadline"))   # negative = future
    pub_deficit   = max(pub_required - pub_accepted, 0)

    # ── Pre-deadline windows ──────────────────────────────────────────────────
    rpd_due_within_30  = (not rpd_completed) and (-30 <= rpd < 0)
    rpd_due_within_60  = (not rpd_completed) and (-60 <= rpd < -30)
    pub_due_within_30  = pub_deficit > 0 and (-30 <= pub_days < 0)
    pub_due_within_60  = pub_deficit > 0 and (-60 <= pub_days < -30)

    # ── Determine label (priority order) ─────────────────────────────────────
    if us >= 2:
        label = "High"
        factors.append(f"{us} Unsatisfactory PPM results (termination risk)")
    elif us == 1 and rpd_due_within_30:
        label = "High"
        factors.append("1 Unsatisfactory PPM + RPD due in "
                        f"{int(-rpd)} days (compounding risk)")
    elif rpd_due_within_30:
        label = "High"
        factors.append(f"RPD due in {int(-rpd)} days — submission required urgently")
    elif us == 1:
        label = "Medium"
        factors.append("1 Unsatisfactory PPM result")
    elif rpd_due_within_60:
        label = "Medium"
        factors.append(f"RPD due in {int(-rpd)} days — prepare submission")
    elif pub_due_within_30:
        label = "Medium"
        factors.append(f"Publication deadline in {int(-pub_days)} days "
                       f"({pub_accepted}/{pub_required} accepted, {pub_deficit} short)")
    else:
        label = "Low"

    # ── Supplementary informational factors ──────────────────────────────────
    # RPD status (if not already the main label driver)
    if rpd_completed and rpd < -7:
        factors.append("RPD submitted ahead of schedule")
    elif rpd_completed and rpd == 0:
        factors.append("RPD submitted on time")
    elif rpd_completed and rpd > 0:
        factors.append(f"RPD submitted {int(rpd)} days late")
    elif pub_due_within_60 and label == "Low":
        factors.append(f"Publication deadline in {int(-pub_days)} days "
                       f"({pub_accepted}/{pub_required} accepted)")

    # Publication progress
    sub = int(_s(row.get("pub_submitted_count")))
    if pub_deficit == 0:
        factors.append(f"Publication requirement met ({pub_accepted}/{pub_required} accepted)")
    elif sub > 0 and pub_deficit > 0:
        factors.append(f"Publication in progress ({sub} submitted, "
                       f"{pub_accepted}/{pub_required} accepted)")
    elif pub_deficit > 0 and pub_days == 0:
        factors.append(f"No publications yet ({pub_accepted}/{pub_required} required)")

    # Work hours
    wh = _s(row.get("weekly_work_hours"))
    if wh >= 20:
        factors.append(f"High external workload ({int(wh)} hrs/week)")
    elif wh > 0:
        factors.append(f"External work ({int(wh)} hrs/week)")
    if row.get("is_part_time", 0):
        factors.append("Part-time student")

    if not factors:
        factors.append("No major risk indicators")

    score = {"High": 80.0, "Medium": 50.0, "Low": 15.0}[label]
    return {"risk_label": label, "risk_score": score, "factors": factors}


def _detect_stage3(row: pd.Series) -> dict:
    """
    Stage 3 pre-deadline early warning.
    Builds on Stage 2; adds thesis seminar deadline warning (no Examiner score).
    """
    ts_delay    = _s(row.get("thesis_seminar_delay"))
    ts_complete = bool(_s(row.get("thesis_seminar_completed")))

    # Stage 2 base (carry forward PPM/RPD signals)
    s2      = _detect_stage2(row)
    factors = [f for f in s2["factors"] if "No major" not in f]

    # ── Pre-deadline windows ──────────────────────────────────────────────────
    ts_due_within_30 = (not ts_complete) and (-30 <= ts_delay < 0)
    ts_due_within_60 = (not ts_complete) and (-60 <= ts_delay < -30)

    # ── Determine label ───────────────────────────────────────────────────────
    if ts_due_within_30:
        label = "High"
        factors.append(f"Thesis seminar due in {int(-ts_delay)} days — action required")
    elif s2["risk_label"] == "High":
        label = "High"
    elif ts_due_within_60:
        label = "Medium"
        factors.append(f"Thesis seminar due in {int(-ts_delay)} days — prepare early")
    elif s2["risk_label"] == "Medium":
        label = "Medium"
    else:
        label = "Low"
        if ts_complete:
            factors.append("Thesis seminar completed")

    if not factors:
        factors.append("No major risk indicators")

    score = {"High": 80.0, "Medium": 50.0, "Low": 15.0}[label]
    return {"risk_label": label, "risk_score": score, "factors": factors}


# ══════════════════════════════════════════════════════════════════════════════
# PART 3 — DB Feature Extraction
# ══════════════════════════════════════════════════════════════════════════════

_FEATURE_QUERY = text("""
    SELECT
        s.student_id,
        s.student_name,
        s.student_id_number,
        s.degree_type,
        s.study_method,
        s.gender,
        COALESCE(s.age_at_enrollment, 25)           AS age_at_enrollment,
        COALESCE(s.entry_gpa, 0)                    AS entry_gpa,
        s.weekly_work_hours,
        s.has_external_work,
        s.is_cross_discipline,
        s.in_research_group,
        COALESCE(s.family_support, 3)               AS family_support,
        cr.region_name,
        d.discipline_group,
        COALESCE(ft.funding_name, 'Unknown')        AS funding_name,
        COALESCE(s.marital_status, 'Single')        AS marital_status,
        -- RPD milestone
        CASE
            WHEN sm.actual_date IS NOT NULL
                THEN DATEDIFF(sm.actual_date, sm.expected_date)
            WHEN sm.expected_date IS NOT NULL
                THEN DATEDIFF(CURDATE(), sm.expected_date)
            ELSE 0
        END AS rpd_delay_days,
        (sm.actual_date IS NOT NULL) AS rpd_completed,
        -- PPM
        COALESCE(ppm.cumulative_us, 0) AS ppm_us_count,
        COALESCE(ppm.total_ppm, 0)     AS ppm_total,
        -- Months enrolled
        TIMESTAMPDIFF(MONTH, s.enrollment_date, CURDATE()) AS months_enrolled,
        -- Publication
        (SELECT COUNT(*) FROM student_publication sp
         WHERE sp.student_id = s.student_id
           AND sp.status IN ('Accepted','Published'))        AS pub_accepted_count,
        (SELECT COUNT(*) FROM student_publication sp
         WHERE sp.student_id = s.student_id)                 AS pub_submitted_count,
        CASE WHEN s.degree_type = 'PhD' THEN 2 ELSE 1 END   AS pub_required,
        -- Publication days from deadline: negative = days until due, positive = overdue, 0 = done/no deadline
        CASE
            WHEN sm3.actual_date IS NOT NULL THEN 0
            WHEN sm3.expected_date IS NOT NULL
                THEN DATEDIFF(CURDATE(), sm3.expected_date)
            ELSE 0
        END AS pub_days_from_deadline,
        -- Thesis seminar: negative = days until due, positive = overdue
        CASE
            WHEN sm4.actual_date IS NOT NULL
                THEN DATEDIFF(sm4.actual_date, sm4.expected_date)
            WHEN sm4.expected_date IS NOT NULL
                THEN DATEDIFF(CURDATE(), sm4.expected_date)
            ELSE 0
        END AS thesis_seminar_delay,
        (sm4.actual_date IS NOT NULL) AS thesis_seminar_completed,
        go.is_delayed
    FROM student s
    LEFT JOIN country c             ON s.country_id = c.country_id
    LEFT JOIN country_region cr     ON c.region_id  = cr.region_id
    LEFT JOIN discipline d          ON s.discipline_id = d.discipline_id
    LEFT JOIN funding_type ft       ON s.funding_id    = ft.funding_id
    LEFT JOIN student_milestone sm  ON s.student_id = sm.student_id AND sm.milestone_id = 1
    LEFT JOIN student_milestone sm3 ON s.student_id = sm3.student_id AND sm3.milestone_id = 3
    LEFT JOIN student_milestone sm4 ON s.student_id = sm4.student_id AND sm4.milestone_id = 4
    LEFT JOIN v_ppm_us_count ppm    ON s.student_id = ppm.student_id
    LEFT JOIN graduation_outcome go ON s.student_id = go.student_id
""")


def _extract_db_features() -> pd.DataFrame:
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
        "family_support", "region_name", "discipline_group",
        "funding_name", "marital_status",
        "rpd_delay_days", "rpd_completed",
        "ppm_us_count", "ppm_total", "months_enrolled",
        "pub_accepted_count", "pub_submitted_count", "pub_required", "pub_days_from_deadline",
        "thesis_seminar_delay", "thesis_seminar_completed",
        "is_delayed",
    ])

    num_cols = [
        "age_at_enrollment", "entry_gpa", "weekly_work_hours", "family_support",
        "rpd_delay_days", "rpd_completed", "ppm_us_count", "ppm_total", "months_enrolled",
        "pub_accepted_count", "pub_submitted_count", "pub_required", "pub_days_from_deadline",
        "thesis_seminar_delay", "thesis_seminar_completed",
    ]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["rpd_completed", "thesis_seminar_completed", "pub_days_from_deadline",
              "pub_accepted_count", "pub_submitted_count", "pub_required"]:
        df[c] = df[c].fillna(0)

    return df


def _encode_features(df: pd.DataFrame, encoders: Optional[dict] = None):
    out      = df.copy()
    fit_mode = encoders is None
    if fit_mode:
        encoders = {}

    out["is_part_time"]        = (out["study_method"] == "Part-time").astype(float)
    out["is_phd"]              = (out["degree_type"]  == "PhD").astype(float)
    out["ppm_us_rate"]         = np.where(out["ppm_total"] > 0,
                                          out["ppm_us_count"] / out["ppm_total"], 0.0)
    out["has_external_work"]   = out["has_external_work"].astype(float)
    out["in_research_group"]   = out["in_research_group"].astype(float)
    out["is_cross_discipline"] = out["is_cross_discipline"].astype(float)

    _ME = {"Divorced": 0, "Married": 1, "Single": 2, "Widowed": 3}
    out["marital_status"]     = out["marital_status"].fillna("Single")
    out["marital_status_enc"] = out["marital_status"].map(_ME).fillna(2).astype(float)

    for col, enc_name in [
        ("gender",           "gender_enc"),
        ("region_name",      "region_enc"),
        ("discipline_group", "discipline_group_enc"),
        ("funding_name",     "funding_enc"),
    ]:
        out[col] = out[col].fillna("Unknown")
        if fit_mode:
            le = LabelEncoder()
            le.fit(list(out[col].unique()) + ["Unknown"])
            encoders[col] = le
        le    = encoders[col]
        known = set(le.classes_)
        out[col]      = out[col].apply(lambda x: x if x in known else "Unknown")
        out[enc_name] = le.transform(out[col]).astype(float)

    out["entry_gpa"] = out["entry_gpa"].fillna(0.0)

    return out, encoders


# ══════════════════════════════════════════════════════════════════════════════
# PART 4 — Stage determination
# ══════════════════════════════════════════════════════════════════════════════

def _determine_stage(row: pd.Series) -> int:
    """
    Stage 1: enrolled ≤3 months ago (new student, Stage 2 not yet begun) — early prediction.
    Stage 3: thesis seminar is completed OR due within 180 days (actively relevant).
    Stage 2: has PPM records OR RPD is completed/upcoming within 90 days.
    Stage 1 (fallback): just enrolled, no active milestones.
    """
    # New student override — always Stage 1 / early prediction
    if _s(row.get("months_enrolled")) <= 3:
        return 1

    ts_delay    = _s(row.get("thesis_seminar_delay"))
    ts_complete = bool(_s(row.get("thesis_seminar_completed")))
    # Stage 3: thesis seminar done, or actively upcoming (within 180 days)
    if ts_complete or (-180 <= ts_delay < 0):
        return 3

    # Stage 2: has PPM history, or RPD is active (completed or upcoming within 90 days)
    if _s(row.get("ppm_total")) > 0:
        return 2
    rpd = _s(row.get("rpd_delay_days"))
    rpd_completed = bool(_s(row.get("rpd_completed")))
    if rpd_completed or (-90 <= rpd < 0):
        return 2

    return 1


# ══════════════════════════════════════════════════════════════════════════════
# PART 5 — Stage 1 RF inference helpers
# ══════════════════════════════════════════════════════════════════════════════

def _proba_to_label(p: float) -> str:
    if p >= 0.60:
        return "High"
    if p >= 0.35:
        return "Medium"
    return "Low"


def _stage1_factors(row: pd.Series) -> list[str]:
    """Human-readable Stage 1 risk factors from enrollment profile."""
    factors = []
    if row.get("is_part_time", 0):
        factors.append("Part-time student (longer programme duration)")
    wh = _s(row.get("weekly_work_hours"))
    if wh >= 20:
        factors.append(f"High external workload ({int(wh)} hrs/week)")
    elif wh > 0:
        factors.append(f"External work ({int(wh)} hrs/week)")
    if row.get("is_cross_discipline", 0):
        factors.append("Cross-discipline study")
    if not row.get("in_research_group", 1):
        factors.append("Not in a research group")
    fs = _s(row.get("family_support"), default=3)
    if fs <= 2:
        factors.append(f"Low family support ({int(fs)}/5)")
    gpa = _s(row.get("entry_gpa"))
    if 0 < gpa < 2.5:
        factors.append(f"Low entry GPA ({gpa:.2f})")
    if not factors:
        factors.append("No major risk indicators detected")
    return factors


# ══════════════════════════════════════════════════════════════════════════════
# PART 6 — Main Pipeline
# ══════════════════════════════════════════════════════════════════════════════

def train_and_predict_rf() -> dict:
    """
    Full pipeline:
      1. Train Stage 1 RF on UCI data (+ holdout evaluation)
      2. Extract + encode DB features
      3. For each student: determine stage, run Stage 1 RF or Stage 2/3 rules
      4. Store predictions, log to MLflow
    """
    logger.info("[RF] Starting pipeline (Stage 1 RF + Stage 2/3 rules)...")
    os.makedirs(_MODEL_DIR, exist_ok=True)

    mlflow_ok = False
    if _MLFLOW_AVAILABLE:
        try:
            mlflow.set_tracking_uri(getattr(settings, "MLFLOW_TRACKING_URI", ""))
            mlflow.set_experiment(getattr(settings, "MLFLOW_EXPERIMENT_NAME", "datatrain") + "_RF")
            mlflow_ok = True
        except Exception as e:
            logger.warning(f"[RF] MLflow unavailable: {e}")

    all_metrics: dict = {}

    # ── Stage 1 holdout evaluation (FYP validation results) ──────────────────
    eval_result = evaluate_stage1_holdout()
    if eval_result.get("available"):
        all_metrics["stage1_holdout"] = eval_result
        logger.info(
            f"[RF] Stage 1 holdout — "
            f"Acc={eval_result['test_accuracy']}, AUC={eval_result['test_auc_roc']}"
        )

    # ── Train Stage 1 on full UCI dataset ────────────────────────────────────
    s1_result = train_stage1_on_uci()
    if s1_result:
        model_s1, s1_metrics = s1_result
        all_metrics["stage1_training"] = s1_metrics
        joblib.dump(model_s1, _RF_S1_PATH)
    elif os.path.exists(_RF_S1_PATH):
        model_s1 = joblib.load(_RF_S1_PATH)
        logger.info("[RF] Stage 1 loaded from saved model.")
    else:
        return {"status": "error", "reason": "No Stage 1 model available"}

    # ── Extract + encode DB features ─────────────────────────────────────────
    df_raw = _extract_db_features()
    if df_raw.empty:
        return {"status": "skipped", "reason": "no student data"}

    if os.path.exists(_ENC_PATH):
        encoders = joblib.load(_ENC_PATH)
        df_enc, _ = _encode_features(df_raw, encoders=encoders)
    else:
        df_enc, encoders = _encode_features(df_raw)
        joblib.dump(encoders, _ENC_PATH)

    # ── Inference ─────────────────────────────────────────────────────────────
    predictions  = []
    stage_counts = {1: 0, 2: 0, 3: 0}

    for _, row in df_enc.iterrows():
        stage = _determine_stage(row)
        stage_counts[stage] += 1

        if stage == 1:
            X       = row[STAGE1_FEATURES].fillna(0).values.reshape(1, -1)
            proba   = model_s1.predict_proba(X)[0]
            classes = list(model_s1.classes_)
            p_drop  = float(proba[classes.index(1)]) if 1 in classes else 0.0
            label   = _proba_to_label(p_drop)
            score   = round(p_drop * 100, 2)
            factors = _stage1_factors(row)
            conf    = round(float(proba.max()), 4)
        elif stage == 2:
            rb      = _detect_stage2(row)
            label, score, factors = rb["risk_label"], rb["risk_score"], rb["factors"]
            conf    = 1.0
        else:
            rb      = _detect_stage3(row)
            label, score, factors = rb["risk_label"], rb["risk_score"], rb["factors"]
            conf    = 1.0

        predictions.append({
            "student_id":       int(row["student_id"]),
            "risk_score":       score,
            "risk_label":       label,
            "cluster_id":       stage,
            "key_risk_factors": json.dumps(factors),
            "stage":            stage,
            "confidence":       conf,
        })

    _store_predictions(predictions)

    distribution = {}
    for p in predictions:
        distribution[p["risk_label"]] = distribution.get(p["risk_label"], 0) + 1

    # ── MLflow logging ────────────────────────────────────────────────────────
    if mlflow_ok:
        try:
            with mlflow.start_run(
                run_name=f"rf_s1_rules_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            ) as run:
                mlflow.log_param("stage1_model", "RandomForest (UCI pre-trained)")
                mlflow.log_param("stage2_model", "Rule-based threshold")
                mlflow.log_param("stage3_model", "Rule-based threshold")
                mlflow.log_metric("total_students",    len(predictions))
                mlflow.log_metric("high_risk_count",   distribution.get("High",   0))
                mlflow.log_metric("medium_risk_count", distribution.get("Medium", 0))
                mlflow.log_metric("low_risk_count",    distribution.get("Low",    0))
                for s, c in stage_counts.items():
                    mlflow.log_metric(f"stage{s}_count", c)
                if eval_result.get("available"):
                    mlflow.log_metric("stage1_test_accuracy", eval_result["test_accuracy"])
                    mlflow.log_metric("stage1_test_auc",      eval_result["test_auc_roc"])
                    mlflow.log_metric("stage1_cv_accuracy",   eval_result["cv_accuracy_mean"])
        except Exception as e:
            logger.warning(f"[RF] MLflow logging failed: {e}")

    logger.info(f"[RF] Done. Stages: {stage_counts}. Distribution: {distribution}")
    return {
        "status":         "success",
        "total_students": len(predictions),
        "distribution":   distribution,
        "stage_counts":   stage_counts,
        "stage1_holdout": {
            "test_accuracy": eval_result.get("test_accuracy"),
            "test_auc_roc":  eval_result.get("test_auc_roc"),
            "test_f1":       eval_result.get("test_f1"),
            "cv_accuracy":   f"{eval_result.get('cv_accuracy_mean')}±{eval_result.get('cv_accuracy_std')}",
        } if eval_result.get("available") else {},
    }


def _store_predictions(predictions: list[dict]) -> None:
    db = SyncSessionLocal()
    try:
        now = datetime.now()
        for p in predictions:
            db.execute(text("""
                INSERT INTO student_risk_prediction
                    (student_id, risk_score, risk_label, cluster_id, key_risk_factors, predicted_at)
                VALUES (:sid, :score, :label, :cluster, :factors, :now)
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
        logger.info(f"[RF] Stored {len(predictions)} predictions.")
    except Exception as e:
        db.rollback()
        logger.error(f"[RF] Store failed: {e}")
        raise
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# PART 7 — Query helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_stage_summary() -> dict:
    db = SyncSessionLocal()
    try:
        rows = db.execute(text("""
            SELECT cluster_id AS stage, COUNT(*) AS cnt
            FROM student_risk_prediction GROUP BY cluster_id
        """)).fetchall()
        return {f"stage_{r.stage}": r.cnt for r in rows}
    finally:
        db.close()
