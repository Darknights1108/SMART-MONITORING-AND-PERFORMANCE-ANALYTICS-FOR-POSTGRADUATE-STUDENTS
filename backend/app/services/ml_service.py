"""
ML Risk Prediction Service
--------------------------
Uses K-Means clustering + weighted risk scoring to predict which students
are at risk of delayed graduation.

Pipeline:
  1. extract_features()      — query DB → pandas DataFrame
  2. compute_risk_scores()   — weighted formula → score 0-100
  3. run_clustering()        — K-Means k=3, label clusters Low/Medium/High
  4. generate_risk_factors() — human-readable explanation per student
  5. store_predictions()     — upsert to student_risk_prediction table
  6. train_and_predict()     — full pipeline entry point
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text

from app.database import SyncSessionLocal

logger = logging.getLogger(__name__)

# Path to save the trained model artefacts
_MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "ml_models")
_SCALER_PATH = os.path.join(_MODEL_DIR, "scaler.joblib")
_KMEANS_PATH = os.path.join(_MODEL_DIR, "kmeans.joblib")

# ──────────────────────────────────────────────────────────────────────────────
# Feature weights for the risk score formula (must sum to 1.0)
# ──────────────────────────────────────────────────────────────────────────────
_WEIGHTS = {
    "rpd_delay_norm":         0.28,   # days overdue on RPD milestone
    "ppm_us_rate":            0.22,   # fraction of PPM cycles that were Unsatisfactory
    "work_hours_norm":        0.12,   # external work hours burden
    "is_part_time":           0.10,   # part-time students take longer
    "is_cross_discipline":    0.08,   # added academic challenge
    "not_in_research_group":  0.08,   # research group membership is protective
    "is_phd":                 0.06,   # PhD programs have longer, riskier timelines
    "low_family_support":     0.06,   # low social support increases risk
}

# ──────────────────────────────────────────────────────────────────────────────
# 1. Feature Extraction
# ──────────────────────────────────────────────────────────────────────────────
_FEATURE_QUERY = text("""
    SELECT
        s.student_id,
        s.student_name,
        s.student_id_number,
        s.degree_type,
        s.study_method,
        s.has_external_work,
        s.weekly_work_hours,
        s.is_cross_discipline,
        s.in_research_group,
        s.family_support,
        -- RPD: delay in days (positive = overdue, negative = early)
        CASE
            WHEN sm.actual_date IS NOT NULL
                THEN DATEDIFF(sm.actual_date, sm.expected_date)
            WHEN sm.expected_date IS NOT NULL
                THEN DATEDIFF(CURDATE(), sm.expected_date)
            ELSE 0
        END AS rpd_delay_days,
        -- PPM
        COALESCE(ppm.cumulative_us, 0)  AS ppm_us_count,
        COALESCE(ppm.total_ppm, 0)      AS ppm_total,
        -- Examiner average (may be NULL if no reports yet)
        (SELECT AVG(er.score_avg)
         FROM examiner_report er
         WHERE er.student_id = s.student_id) AS examiner_avg_score
    FROM student s
    LEFT JOIN student_milestone sm
        ON s.student_id = sm.student_id AND sm.milestone_id = 1
    LEFT JOIN v_ppm_us_count ppm
        ON s.student_id = ppm.student_id
""")


def extract_features() -> pd.DataFrame:
    """Query the database and return a raw feature DataFrame."""
    db = SyncSessionLocal()
    try:
        rows = db.execute(_FEATURE_QUERY).fetchall()
        df = pd.DataFrame(rows, columns=[
            "student_id", "student_name", "student_id_number",
            "degree_type", "study_method",
            "has_external_work", "weekly_work_hours",
            "is_cross_discipline", "in_research_group", "family_support",
            "rpd_delay_days", "ppm_us_count", "ppm_total",
            "examiner_avg_score",
        ])
        return df
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# 2. Risk Score (0–100 weighted formula)
# ──────────────────────────────────────────────────────────────────────────────
def _normalize(series: pd.Series, lo: float, hi: float) -> pd.Series:
    """Clip and min-max normalise to [0, 1]."""
    clipped = series.clip(lo, hi)
    span = hi - lo
    return (clipped - lo) / span if span > 0 else clipped * 0


def compute_risk_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Add normalised feature columns and a risk_score column to df."""
    out = df.copy()

    # --- individual normalised features ---
    out["rpd_delay_norm"]        = _normalize(out["rpd_delay_days"], -30, 180)
    out["ppm_us_rate"]           = np.where(
        out["ppm_total"] > 0,
        out["ppm_us_count"] / out["ppm_total"],
        0.0,
    )
    out["work_hours_norm"]       = _normalize(out["weekly_work_hours"], 0, 40)
    out["is_part_time"]          = (out["study_method"] == "Part-time").astype(float)
    out["is_cross_discipline"]   = out["is_cross_discipline"].astype(float)
    out["not_in_research_group"] = (~out["in_research_group"].astype(bool)).astype(float)
    out["is_phd"]                = (out["degree_type"] == "PhD").astype(float)
    # family_support: 1=Very Low → high risk, 5=Very High → low risk
    out["low_family_support"]    = np.where(
        out["family_support"].notna(),
        _normalize(6 - out["family_support"], 1, 5),   # invert scale
        0.5,   # unknown → assume moderate risk
    )

    # --- weighted sum → 0–100 ---
    score = sum(
        _WEIGHTS[feat] * out[feat]
        for feat in _WEIGHTS
    )
    out["risk_score"] = (score * 100).round(2)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 3. K-Means Clustering
# ──────────────────────────────────────────────────────────────────────────────
_CLUSTER_FEATURES = list(_WEIGHTS.keys())


def run_clustering(df: pd.DataFrame, n_clusters: int = 3) -> pd.DataFrame:
    """
    Fit K-Means on the normalised feature columns.
    Assigns risk_label (Low/Medium/High) by ranking cluster mean risk scores.
    Returns df with cluster_id and risk_label columns added.
    Saves scaler + model to disk for later inference.
    """
    os.makedirs(_MODEL_DIR, exist_ok=True)

    X = df[_CLUSTER_FEATURES].fillna(0).values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Guard: if fewer students than clusters, reduce k
    k = min(n_clusters, len(df))
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    df = df.copy()
    df["cluster_id"] = kmeans.fit_predict(X_scaled)

    # Label clusters by mean risk score (ascending → Low, Medium, High)
    cluster_means = df.groupby("cluster_id")["risk_score"].mean().sort_values()
    label_map = {}
    labels = ["Low", "Medium", "High"]
    for rank, cid in enumerate(cluster_means.index):
        label_map[cid] = labels[min(rank, 2)]
    df["risk_label"] = df["cluster_id"].map(label_map)

    # Persist model artefacts
    joblib.dump(scaler, _SCALER_PATH)
    joblib.dump(kmeans, _KMEANS_PATH)
    logger.info(f"[ML] K-Means trained with k={k}. Cluster→label map: {label_map}")

    return df


# ──────────────────────────────────────────────────────────────────────────────
# 4. Human-Readable Risk Factor Explanations
# ──────────────────────────────────────────────────────────────────────────────
def generate_risk_factors(row: pd.Series) -> list[str]:
    """Return a list of the top risk reasons for one student row."""
    factors = []

    if row["rpd_delay_days"] > 0:
        factors.append(f"RPD overdue by {int(row['rpd_delay_days'])} days")
    elif row["rpd_delay_days"] < -7:
        factors.append("RPD completed ahead of schedule")

    if row["ppm_us_count"] >= 2:
        factors.append(f"{int(row['ppm_us_count'])} Unsatisfactory PPM results (termination risk)")
    elif row["ppm_us_count"] == 1:
        factors.append("1 Unsatisfactory PPM result")

    if row["is_part_time"]:
        factors.append("Part-time student (longer programme duration)")

    if row["weekly_work_hours"] >= 20:
        factors.append(f"High external workload ({row['weekly_work_hours']:.0f} hrs/week)")
    elif row["weekly_work_hours"] > 0:
        factors.append(f"External work ({row['weekly_work_hours']:.0f} hrs/week)")

    if row["is_cross_discipline"]:
        factors.append("Cross-discipline study (added academic challenge)")

    if not row["in_research_group"]:
        factors.append("Not in a research group (less peer support)")

    fs = row["family_support"]
    if pd.notna(fs) and fs <= 2:
        factors.append(f"Low family support (score {int(fs)}/5)")

    if not factors:
        factors.append("No major risk indicators detected")

    return factors


# ──────────────────────────────────────────────────────────────────────────────
# 5. Store Predictions to DB
# ──────────────────────────────────────────────────────────────────────────────
def store_predictions(df: pd.DataFrame) -> None:
    """Upsert all predictions into student_risk_prediction."""
    db = SyncSessionLocal()
    try:
        now = datetime.now()
        for _, row in df.iterrows():
            factors = generate_risk_factors(row)
            db.execute(text("""
                INSERT INTO student_risk_prediction
                    (student_id, risk_score, risk_label, cluster_id,
                     key_risk_factors, predicted_at)
                VALUES
                    (:sid, :score, :label, :cluster,
                     :factors, :now)
                ON DUPLICATE KEY UPDATE
                    risk_score       = VALUES(risk_score),
                    risk_label       = VALUES(risk_label),
                    cluster_id       = VALUES(cluster_id),
                    key_risk_factors = VALUES(key_risk_factors),
                    predicted_at     = VALUES(predicted_at)
            """), {
                "sid":     int(row["student_id"]),
                "score":   float(row["risk_score"]),
                "label":   str(row["risk_label"]),
                "cluster": int(row["cluster_id"]),
                "factors": json.dumps(factors),
                "now":     now,
            })
        db.commit()
        logger.info(f"[ML] Stored {len(df)} predictions.")
    except Exception as e:
        db.rollback()
        logger.error(f"[ML] Failed to store predictions: {e}")
        raise
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# 6. Full Pipeline Entry Point
# ──────────────────────────────────────────────────────────────────────────────
def train_and_predict() -> dict:
    """
    Run the full ML pipeline:
      extract → score → cluster → store
    Returns a summary dict.
    """
    logger.info("[ML] Starting risk prediction pipeline...")
    try:
        df = extract_features()
        if df.empty:
            logger.warning("[ML] No student data found. Skipping.")
            return {"status": "skipped", "reason": "no student data"}

        df = compute_risk_scores(df)
        df = run_clustering(df, n_clusters=3)
        store_predictions(df)

        summary = df["risk_label"].value_counts().to_dict()
        logger.info(f"[ML] Pipeline complete. Distribution: {summary}")
        return {
            "status": "success",
            "total_students": len(df),
            "distribution": summary,
            "high_risk_count": summary.get("High", 0),
        }
    except Exception as e:
        logger.error(f"[ML] Pipeline failed: {e}", exc_info=True)
        return {"status": "error", "reason": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# 7. Query Helpers (used by API and agent tools)
# ──────────────────────────────────────────────────────────────────────────────
def get_all_predictions() -> list[dict]:
    """Return all current predictions with student info."""
    db = SyncSessionLocal()
    try:
        rows = db.execute(text("""
            SELECT
                s.student_id,
                s.student_id_number,
                s.student_name,
                s.degree_type,
                s.study_method,
                p.faculty_description,
                rp.risk_score,
                rp.risk_label,
                rp.cluster_id,
                rp.key_risk_factors,
                rp.predicted_at
            FROM student_risk_prediction rp
            JOIN student s ON s.student_id = rp.student_id
            JOIN program pr ON s.program_id = pr.program_id
            JOIN faculty p  ON pr.faculty_id = p.faculty_id
            ORDER BY rp.risk_score DESC
        """)).fetchall()

        return [
            {
                "student_id":        r.student_id,
                "student_id_number": r.student_id_number,
                "student_name":      r.student_name,
                "degree_type":       r.degree_type,
                "study_method":      r.study_method,
                "faculty":           r.faculty_description,
                "risk_score":        float(r.risk_score),
                "risk_label":        r.risk_label,
                "cluster_id":        r.cluster_id,
                "key_risk_factors":  json.loads(r.key_risk_factors or "[]"),
                "predicted_at":      r.predicted_at.isoformat() if r.predicted_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()


def get_prediction_by_student(student_id: int) -> Optional[dict]:
    """Return the prediction for one student, or None if not found."""
    db = SyncSessionLocal()
    try:
        row = db.execute(text("""
            SELECT
                s.student_id,
                s.student_id_number,
                s.student_name,
                s.degree_type,
                s.study_method,
                pr.program_description,
                p.faculty_description,
                rp.risk_score,
                rp.risk_label,
                rp.cluster_id,
                rp.key_risk_factors,
                rp.predicted_at
            FROM student_risk_prediction rp
            JOIN student s  ON s.student_id = rp.student_id
            JOIN program pr ON s.program_id = pr.program_id
            JOIN faculty p  ON pr.faculty_id = p.faculty_id
            WHERE rp.student_id = :sid
        """), {"sid": student_id}).fetchone()

        if not row:
            return None

        return {
            "student_id":        row.student_id,
            "student_id_number": row.student_id_number,
            "student_name":      row.student_name,
            "degree_type":       row.degree_type,
            "study_method":      row.study_method,
            "program":           row.program_description,
            "faculty":           row.faculty_description,
            "risk_score":        float(row.risk_score),
            "risk_label":        row.risk_label,
            "cluster_id":        row.cluster_id,
            "key_risk_factors":  json.loads(row.key_risk_factors or "[]"),
            "predicted_at":      row.predicted_at.isoformat() if row.predicted_at else None,
        }
    finally:
        db.close()


def get_high_risk_students() -> list[dict]:
    """Return all students labelled High risk."""
    return [p for p in get_all_predictions() if p["risk_label"] == "High"]


def get_risk_distribution() -> dict:
    """Return count per risk label."""
    db = SyncSessionLocal()
    try:
        rows = db.execute(text("""
            SELECT risk_label, COUNT(*) AS cnt
            FROM student_risk_prediction
            GROUP BY risk_label
        """)).fetchall()
        return {r.risk_label: r.cnt for r in rows}
    finally:
        db.close()
