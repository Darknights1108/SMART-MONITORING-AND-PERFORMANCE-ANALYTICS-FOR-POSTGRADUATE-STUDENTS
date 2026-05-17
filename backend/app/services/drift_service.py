"""
Drift Detection Service
-----------------------
Uses Evidently AI to detect data drift between the reference dataset
(first/baseline training run) and the current feature snapshot.

Flow:
  1. First pipeline run  → save current features as reference, no drift computed.
  2. Every subsequent run → compare current vs reference with Evidently.
  3. Results (dataset_drift flag, per-feature scores) stored in ml_drift_report.
  4. HTML report is logged to the active MLflow run as an artifact.
  5. Drift metrics (drift_detected, drifted_features, drift_share) are logged
     to MLflow by the caller (ml_service.train_and_predict) while the run
     context is still open.
"""

import json
import logging
import os
import tempfile
from datetime import datetime
from typing import Optional

import pandas as pd
from sqlalchemy import text

from app.database import SyncSessionLocal

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
_MODEL_DIR      = os.path.join(os.path.dirname(__file__), "..", "ml_models")
_REFERENCE_PATH = os.path.join(_MODEL_DIR, "reference_features.csv")

# Features to monitor — matches the 8 ML features + risk_score output
_MONITORED_FEATURES = [
    "rpd_delay_norm",
    "ppm_us_rate",
    "work_hours_norm",
    "is_part_time",
    "is_cross_discipline",
    "not_in_research_group",
    "is_phd",
    "low_family_support",
    "risk_score",
]

# Drift threshold: if share of drifted features exceeds this, flag as alert
DRIFT_ALERT_THRESHOLD = 0.30   # 30 %


# ── Reference dataset management ───────────────────────────────────────────────

def save_reference(df: pd.DataFrame, force: bool = False) -> bool:
    """
    Save the current feature snapshot as the reference dataset (CSV).
    Skips the write if the file already exists and force=False.
    Returns True if saved, False if skipped.
    """
    os.makedirs(_MODEL_DIR, exist_ok=True)
    if os.path.exists(_REFERENCE_PATH) and not force:
        return False

    cols = [c for c in _MONITORED_FEATURES if c in df.columns]
    df[cols].to_csv(_REFERENCE_PATH, index=False)
    logger.info(
        f"[Drift] Reference dataset saved — "
        f"{len(df)} rows × {len(cols)} features → {_REFERENCE_PATH}"
    )
    return True


def load_reference() -> Optional[pd.DataFrame]:
    """Load the reference CSV. Returns None if it has never been saved."""
    if not os.path.exists(_REFERENCE_PATH):
        return None
    try:
        return pd.read_csv(_REFERENCE_PATH)
    except Exception as e:
        logger.warning(f"[Drift] Could not load reference dataset: {e}")
        return None


def reset_reference() -> bool:
    """Delete the reference file so the next training run re-establishes it."""
    if os.path.exists(_REFERENCE_PATH):
        os.remove(_REFERENCE_PATH)
        logger.info("[Drift] Reference dataset reset.")
        return True
    return False


# ── Main drift detection ───────────────────────────────────────────────────────

def run_drift_detection(current_df: pd.DataFrame) -> dict:
    """
    Compare *current_df* (output of compute_risk_scores) against the saved
    reference dataset.

    Returns a dict:
      status            : "reference_set" | "success" | "skipped" | "error"
      dataset_drift     : bool  (True = significant overall drift)
      drifted_features  : int
      total_features    : int
      drift_share       : float  (0–1)
      feature_details   : dict  per-feature stats
      alert             : bool  (True if drift_share > DRIFT_ALERT_THRESHOLD)
    """
    # Pull only the monitored columns that actually exist in the DataFrame
    feature_cols = [c for c in _MONITORED_FEATURES if c in current_df.columns]
    current = current_df[feature_cols].fillna(0).reset_index(drop=True)

    ref_df = load_reference()

    # ── First run: establish baseline ─────────────────────────────────────────
    if ref_df is None:
        save_reference(current_df, force=True)
        _store_report(
            mlflow_run_id=None,
            dataset_drift=False,
            drifted_features=0,
            total_features=len(feature_cols),
            drift_share=0.0,
            feature_details={"_note": "Initial reference dataset established"},
        )
        logger.info("[Drift] First run — reference dataset established, no drift computed.")
        return {
            "status":           "reference_set",
            "dataset_drift":    False,
            "drifted_features": 0,
            "total_features":   len(feature_cols),
            "drift_share":      0.0,
            "feature_details":  {},
            "alert":            False,
        }

    # ── Subsequent runs: compare ──────────────────────────────────────────────
    common_cols = [c for c in feature_cols if c in ref_df.columns]
    ref     = ref_df[common_cols].fillna(0).reset_index(drop=True)
    current = current[common_cols]

    try:
        from evidently.report import Report
        from evidently.metric_presets import DataDriftPreset

        report = Report(metrics=[DataDriftPreset()])
        report.run(reference_data=ref, current_data=current)
        result = report.as_dict()

        # Find the DatasetDriftMetric in the metrics list (robust index-free lookup)
        drift_result = None
        for m in result.get("metrics", []):
            if m.get("metric") == "DatasetDriftMetric":
                drift_result = m["result"]
                break

        if drift_result is None:
            # Fallback: use first metric
            drift_result = result["metrics"][0]["result"]

        dataset_drift    = bool(drift_result.get("dataset_drift", False))
        drifted_features = int(drift_result.get("number_of_drifted_columns", 0))
        total_features   = int(drift_result.get("number_of_columns", len(common_cols)))
        drift_share      = float(drift_result.get("share_of_drifted_columns", 0.0))

        # Per-feature breakdown
        feature_details: dict = {}
        for col, col_data in drift_result.get("drift_by_columns", {}).items():
            feature_details[col] = {
                "drifted":     bool(col_data.get("drift_detected", False)),
                "drift_score": round(float(col_data.get("drift_score", 0)), 4)
                               if col_data.get("drift_score") is not None else None,
                "p_value":     round(float(col_data.get("p_value", 0)), 4)
                               if col_data.get("p_value") is not None else None,
                "stattest":    col_data.get("stattest_name"),
            }

        # Log HTML report artifact to the currently active MLflow run (if any)
        _try_log_html_artifact(report)

        # Persist summary to DB
        _store_report(
            mlflow_run_id=_get_active_mlflow_run_id(),
            dataset_drift=dataset_drift,
            drifted_features=drifted_features,
            total_features=total_features,
            drift_share=drift_share,
            feature_details=feature_details,
        )

        alert = drift_share > DRIFT_ALERT_THRESHOLD
        if alert:
            logger.warning(
                f"[Drift] ⚠️  Data drift ALERT — "
                f"{drifted_features}/{total_features} features drifted "
                f"({drift_share:.1%}, threshold={DRIFT_ALERT_THRESHOLD:.0%})"
            )
        else:
            logger.info(
                f"[Drift] ✅ No significant drift — "
                f"{drifted_features}/{total_features} features drifted ({drift_share:.1%})"
            )

        return {
            "status":           "success",
            "dataset_drift":    dataset_drift,
            "drifted_features": drifted_features,
            "total_features":   total_features,
            "drift_share":      round(drift_share, 4),
            "feature_details":  feature_details,
            "alert":            alert,
        }

    except ImportError:
        logger.warning("[Drift] Evidently not installed — skipping drift detection.")
        return {"status": "skipped", "reason": "evidently not installed",
                "dataset_drift": False, "alert": False}
    except Exception as e:
        logger.error(f"[Drift] Detection failed: {e}", exc_info=True)
        return {"status": "error", "reason": str(e),
                "dataset_drift": False, "alert": False}


# ── MLflow helpers ─────────────────────────────────────────────────────────────

def _get_active_mlflow_run_id() -> Optional[str]:
    """Return the ID of the currently active MLflow run, or None."""
    try:
        import mlflow
        run = mlflow.active_run()
        return run.info.run_id if run else None
    except Exception:
        return None


def _try_log_html_artifact(report) -> None:
    """
    Save the Evidently HTML report to a temp file and log it as an MLflow artifact.
    Silently skips if no active MLflow run or if MLflow is unavailable.
    """
    try:
        import mlflow
        if mlflow.active_run() is None:
            return

        with tempfile.NamedTemporaryFile(
            suffix=".html", delete=False, mode="w", encoding="utf-8"
        ) as f:
            tmp_path = f.name

        report.save_html(tmp_path)
        mlflow.log_artifact(tmp_path, artifact_path="drift_reports")
        os.unlink(tmp_path)
        logger.info("[Drift] HTML report logged to MLflow.")
    except Exception as e:
        logger.debug(f"[Drift] HTML artifact upload skipped: {e}")


# ── DB persistence ─────────────────────────────────────────────────────────────

def _store_report(
    mlflow_run_id: Optional[str],
    dataset_drift: bool,
    drifted_features: int,
    total_features: int,
    drift_share: float,
    feature_details: dict,
) -> None:
    """Insert a drift report summary row into ml_drift_report."""
    db = SyncSessionLocal()
    try:
        db.execute(text("""
            INSERT INTO ml_drift_report
                (mlflow_run_id, dataset_drift, drifted_features,
                 total_features, drift_share, feature_details, created_at)
            VALUES
                (:run_id, :drift, :drifted, :total, :share, :details, :now)
        """), {
            "run_id":  mlflow_run_id,
            "drift":   int(dataset_drift),
            "drifted": drifted_features,
            "total":   total_features,
            "share":   drift_share,
            "details": json.dumps(feature_details),
            "now":     datetime.now(),
        })
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"[Drift] Failed to store report to DB: {e}")
    finally:
        db.close()


# ── Query helpers ──────────────────────────────────────────────────────────────

def get_latest_drift_report() -> Optional[dict]:
    """Return the most recent drift report, or None if none exist yet."""
    db = SyncSessionLocal()
    try:
        row = db.execute(text("""
            SELECT report_id, mlflow_run_id, dataset_drift,
                   drifted_features, total_features, drift_share,
                   feature_details, created_at
            FROM ml_drift_report
            ORDER BY created_at DESC
            LIMIT 1
        """)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        db.close()


def get_drift_history(limit: int = 10) -> list[dict]:
    """Return the last *limit* drift reports (newest first)."""
    db = SyncSessionLocal()
    try:
        rows = db.execute(text("""
            SELECT report_id, mlflow_run_id, dataset_drift,
                   drifted_features, total_features, drift_share,
                   feature_details, created_at
            FROM ml_drift_report
            ORDER BY created_at DESC
            LIMIT :lim
        """), {"lim": limit}).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        db.close()


def _row_to_dict(row) -> dict:
    return {
        "report_id":        row.report_id,
        "mlflow_run_id":    row.mlflow_run_id,
        "dataset_drift":    bool(row.dataset_drift),
        "drifted_features": int(row.drifted_features),
        "total_features":   int(row.total_features),
        "drift_share":      float(row.drift_share),
        "feature_details":  json.loads(row.feature_details or "{}"),
        "created_at":       row.created_at.isoformat() if row.created_at else None,
        "alert":            float(row.drift_share) > DRIFT_ALERT_THRESHOLD,
    }
