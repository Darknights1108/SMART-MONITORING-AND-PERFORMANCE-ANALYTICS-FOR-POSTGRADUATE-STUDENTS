"""
Multi-Stage Random Forest Risk Prediction Service
--------------------------------------------------
Predicts graduation delay risk using a staged approach:

  Stage 1 — Enrollment features only (available from day 1)
    Features: age_at_enrollment, entry_gpa, weekly_work_hours, family_support,
              gender, study_method, has_external_work, in_research_group,
              is_cross_discipline, degree_type, region_name, discipline_group
    Pre-trained on: data.csv (UCI Student Dropout dataset, 3630 rows)
    Fine-tuned on:  Our students WITH graduation_outcome labels

  Stage 2 — Adds progress indicators (after first PPM cycle / RPD)
    Additional features: rpd_delay_days, ppm_us_count, ppm_us_rate, months_since_enrollment

  Stage 3 — Adds academic assessment (after examiner report)
    Additional features: examiner_avg_score, thesis_seminar_delay_days

Each stage produces:
  - risk_label: Low / Medium / High
  - risk_score: 0–100
  - stage: 1 / 2 / 3 (which model was used)
  - confidence: RF predict_proba max confidence

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
_DATA_CSV    = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data.csv")

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
]

STAGE2_FEATURES = STAGE1_FEATURES + [
    "rpd_delay_days",       # days overdue on RPD (negative = early)
    "ppm_us_count",         # total unsatisfactory PPM
    "ppm_us_rate",          # ppm_us_count / ppm_total
    "months_enrolled",      # months since enrollment_date
]

STAGE3_FEATURES = STAGE2_FEATURES + [
    "examiner_avg_score",   # avg of 10-dim examiner report (nullable → fill 0)
    "thesis_seminar_delay", # days delay on Thesis Seminar milestone
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
    df["in_research_group"]   = df["Scholarship holder"].astype(float)  # proxy
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

    out = df[STAGE1_FEATURES + ["is_delayed"]].copy()
    out = out.fillna(0)
    logger.info(f"[RF] External data loaded: {len(out)} rows, dropout rate={out['is_delayed'].mean():.2%}")
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
        -- RPD milestone delay
        CASE
            WHEN sm.actual_date IS NOT NULL
                THEN DATEDIFF(sm.actual_date, sm.expected_date)
            WHEN sm.expected_date IS NOT NULL
                THEN DATEDIFF(CURDATE(), sm.expected_date)
            ELSE 0
        END AS rpd_delay_days,
        -- PPM stats
        COALESCE(ppm.cumulative_us, 0) AS ppm_us_count,
        COALESCE(ppm.total_ppm, 0)     AS ppm_total,
        -- Months enrolled
        TIMESTAMPDIFF(MONTH, s.enrollment_date, CURDATE()) AS months_enrolled,
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
    LEFT JOIN student_milestone sm  ON s.student_id = sm.student_id AND sm.milestone_id = 1
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
        "family_support", "region_name", "discipline_group",
        "rpd_delay_days", "ppm_us_count", "ppm_total", "months_enrolled",
        "examiner_avg_score", "thesis_seminar_delay",
        "is_delayed",
    ])

    # Cast numerics
    numeric_cols = [
        "age_at_enrollment", "entry_gpa", "weekly_work_hours",
        "family_support", "rpd_delay_days", "ppm_us_count", "ppm_total",
        "months_enrolled", "examiner_avg_score", "thesis_seminar_delay",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

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

    # Binary derived features
    out["is_part_time"]  = (out["study_method"] == "Part-time").astype(float)
    out["is_phd"]        = (out["degree_type"]  == "PhD").astype(float)
    out["ppm_us_rate"]   = np.where(out["ppm_total"] > 0, out["ppm_us_count"] / out["ppm_total"], 0.0)
    out["has_external_work"]   = out["has_external_work"].astype(float)
    out["in_research_group"]   = out["in_research_group"].astype(float)
    out["is_cross_discipline"] = out["is_cross_discipline"].astype(float)

    # Gender encoding
    for col, name in [("gender", "gender_enc"), ("region_name", "region_enc"), ("discipline_group", "discipline_group_enc")]:
        out[col] = out[col].fillna("Unknown")
        if fit_mode:
            le = LabelEncoder()
            le.fit(list(out[col].unique()) + ["Unknown"])
            encoders[col] = le
        le = encoders[col]
        # Handle unseen labels
        known = set(le.classes_)
        out[col] = out[col].apply(lambda x: x if x in known else "Unknown")
        out[name] = le.transform(out[col]).astype(float)

    # Fill nulls
    out["examiner_avg_score"] = out["examiner_avg_score"].fillna(0.0)
    out["entry_gpa"]          = out["entry_gpa"].fillna(0.0)

    return out, encoders


def _determine_stage(row: pd.Series) -> int:
    """
    Determine which stage a student qualifies for:
    Stage 3: has examiner report
    Stage 2: has at least 1 PPM record or RPD is past expected date
    Stage 1: enrollment data only
    """
    if row.get("examiner_avg_score", 0) and row["examiner_avg_score"] > 0:
        return 3
    if row.get("ppm_total", 0) > 0 or abs(row.get("rpd_delay_days", 0)) > 0:
        return 2
    return 1


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


def pretrain_on_external_data() -> Optional[tuple[RandomForestClassifier, dict]]:
    """
    Train Stage 1 RF on data.csv (UCI dataset).
    Returns (model, metrics) or None if data not available.
    """
    ext = _load_external_data()
    if ext is None:
        return None

    X = ext[STAGE1_FEATURES].fillna(0).values
    y = ext["is_delayed"].values

    model, metrics = _train_rf(X, y, "S1-external")
    metrics["source"] = "data.csv (UCI)"
    logger.info(f"[RF] Stage 1 pre-trained on external data: {metrics}")
    return model, metrics


def train_all_stages(df_encoded: pd.DataFrame) -> dict:
    """
    Train all 3 RF stages using our DB students that have graduation_outcome.
    Students without labels → only used for inference.
    Returns dict of {stage: (model, metrics)} for stages that have enough data.
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
            logger.warning(f"[RF:{tag}] Only {len(stage_df)} labeled rows — skipping DB training for stage {stage}.")
            results[stage] = None
            continue
        X = stage_df[features].fillna(0).values
        y = stage_df["is_delayed"].values
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
    """Generate human-readable risk reasons (same logic as before, stage-aware)."""
    factors = []
    if stage >= 2:
        if row.get("rpd_delay_days", 0) > 0:
            factors.append(f"RPD overdue by {int(row['rpd_delay_days'])} days")
        if row.get("ppm_us_count", 0) >= 2:
            factors.append(f"{int(row['ppm_us_count'])} Unsatisfactory PPM results (termination risk)")
        elif row.get("ppm_us_count", 0) == 1:
            factors.append("1 Unsatisfactory PPM result")
    if stage >= 3 and row.get("examiner_avg_score", 0) > 0:
        score = row["examiner_avg_score"]
        if score < 2.5:
            factors.append(f"Low examiner avg score ({score:.1f}/5)")
        elif score < 3.5:
            factors.append(f"Moderate examiner avg score ({score:.1f}/5)")
    if row.get("is_part_time", 0):
        factors.append("Part-time student (longer programme duration)")
    if row.get("weekly_work_hours", 0) >= 20:
        factors.append(f"High external workload ({row['weekly_work_hours']:.0f} hrs/week)")
    elif row.get("weekly_work_hours", 0) > 0:
        factors.append(f"External work ({row['weekly_work_hours']:.0f} hrs/week)")
    if row.get("is_cross_discipline", 0):
        factors.append("Cross-discipline study (added academic challenge)")
    if not row.get("in_research_group", 1):
        factors.append("Not in a research group")
    fs = row.get("family_support", 3)
    if pd.notna(fs) and fs <= 2:
        factors.append(f"Low family support (score {int(fs)}/5)")
    if row.get("entry_gpa", 4) < 2.5 and row.get("entry_gpa", 0) > 0:
        factors.append(f"Low entry GPA ({row['entry_gpa']:.2f})")
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

    # ── Stage 1: pre-train on external data ──────────────────────────────────
    s1_external = pretrain_on_external_data()
    models: dict[int, RandomForestClassifier] = {}

    if s1_external:
        models[1], ext_metrics = s1_external
        all_metrics["stage1_external"] = ext_metrics
        joblib.dump(models[1], _RF_S1_PATH)
    elif os.path.exists(_RF_S1_PATH):
        models[1] = joblib.load(_RF_S1_PATH)
        logger.info("[RF] Loaded Stage 1 model from local joblib.")

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
    db_results = train_all_stages(df_enc)
    for stage, result in db_results.items():
        if result is not None:
            model, metrics = result
            models[stage] = model
            all_metrics[f"stage{stage}_db"] = metrics
            path = {1: _RF_S1_PATH, 2: _RF_S2_PATH, 3: _RF_S3_PATH}[stage]
            joblib.dump(model, path)

    # Load any missing stage models from disk
    for stage, path in [(1, _RF_S1_PATH), (2, _RF_S2_PATH), (3, _RF_S3_PATH)]:
        if stage not in models and os.path.exists(path):
            models[stage] = joblib.load(path)
            logger.info(f"[RF] Stage {stage} loaded from local joblib.")

    if not models:
        return {"status": "error", "reason": "No RF models available"}

    # ── Inference on all students ─────────────────────────────────────────────
    predictions = []
    stage_counts = {1: 0, 2: 0, 3: 0}

    for _, row in df_enc.iterrows():
        stage = _determine_stage(row)
        pred  = _predict_student(row, models, stage)
        stage_counts[pred["stage"]] = stage_counts.get(pred["stage"], 0) + 1
        factors = generate_risk_factors_rf(row, stage)
        predictions.append({
            "student_id":       int(row["student_id"]),
            "risk_score":       pred["risk_score"],
            "risk_label":       pred["risk_label"],
            "cluster_id":       pred["stage"],   # reuse cluster_id column for stage
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
