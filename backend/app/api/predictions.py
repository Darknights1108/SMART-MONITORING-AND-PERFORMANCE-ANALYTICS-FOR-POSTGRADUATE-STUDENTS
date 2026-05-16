"""
Predictions API — exposes ML risk prediction results.

Endpoints:
  GET  /api/predictions/              — all students with risk scores
  GET  /api/predictions/distribution  — label counts (for dashboard charts)
  GET  /api/predictions/runs          — MLflow run history (admin)
  GET  /api/predictions/drift         — latest data drift report
  GET  /api/predictions/drift/history — last N drift reports
  POST /api/predictions/drift/reset   — force-reset reference dataset (admin)
  GET  /api/predictions/{student_id}  — single student prediction
  POST /api/predictions/retrain       — re-run the K-Means pipeline (admin only)
  POST /api/predictions/retrain-rf    — re-run the multi-stage RF pipeline (admin only)
  GET  /api/predictions/stage         — student count per prediction stage (RF)
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from app.services.ml_service import (
    get_all_predictions,
    get_prediction_by_student,
    get_risk_distribution,
    train_and_predict,
)
from app.services.ml_service_rf import (
    train_and_predict_rf,
    get_stage_summary,
    evaluate_on_uci,
)
from app.services.drift_service import (
    get_latest_drift_report,
    get_drift_history,
    reset_reference,
    DRIFT_ALERT_THRESHOLD,
)
from app.api.auth import require_role
from app.config import get_settings

settings = get_settings()

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


@router.get("/")
def list_predictions():
    """Return all student risk predictions sorted by risk score descending."""
    return get_all_predictions()


@router.get("/distribution")
def risk_distribution():
    """Return count of students per risk label — used by dashboard pie/bar chart."""
    dist = get_risk_distribution()
    total = sum(dist.values())
    return {
        "distribution": dist,
        "total": total,
        "high_risk_count":   dist.get("High",   0),
        "medium_risk_count": dist.get("Medium", 0),
        "low_risk_count":    dist.get("Low",    0),
    }


@router.get("/runs")
def list_mlflow_runs(current_user: dict = Depends(require_role(["Admin", "Both"]))):
    """
    Return the last 20 MLflow training runs with key metrics.
    Admin only — used to audit model history in the dashboard.
    """
    try:
        import mlflow
        mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
        client = mlflow.MlflowClient()
        experiment = client.get_experiment_by_name(settings.MLFLOW_EXPERIMENT_NAME)
        if not experiment:
            return {"runs": [], "message": "No experiment found yet."}

        runs = client.search_runs(
            experiment_ids=[experiment.experiment_id],
            order_by=["start_time DESC"],
            max_results=20,
        )

        result = []
        for r in runs:
            m = r.data.metrics
            result.append({
                "run_id":                   r.info.run_id,
                "status":                   r.info.status,
                "start_time":               r.info.start_time,
                "end_time":                 r.info.end_time,
                "total_students":           int(m.get("total_students",   0)),
                "high_risk_count":          int(m.get("high_risk_count",  0)),
                "medium_risk_count":        int(m.get("medium_risk_count",0)),
                "low_risk_count":           int(m.get("low_risk_count",   0)),
                "risk_score_mean":          m.get("risk_score_mean"),
                "risk_score_std":           m.get("risk_score_std"),
                # Clustering benchmarks
                "silhouette_score":         m.get("silhouette_score"),
                "davies_bouldin_index":     m.get("davies_bouldin_index"),
                "calinski_harabasz_score":  m.get("calinski_harabasz_score"),
                "inertia":                  m.get("inertia"),
            })

        return {"runs": result}

    except Exception as e:
        raise HTTPException(status_code=503, detail=f"MLflow unavailable: {e}")


@router.get("/benchmark-history")
def benchmark_history(limit: int = Query(default=20, ge=1, le=100)):
    """
    Public endpoint — returns last N training runs with full benchmark metrics.
    No auth required (data is non-sensitive clustering stats).
    Used by the standalone /benchmark dashboard page.
    """
    try:
        import mlflow
        mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
        client = mlflow.MlflowClient()
        experiment = client.get_experiment_by_name(settings.MLFLOW_EXPERIMENT_NAME)
        if not experiment:
            return {"runs": [], "available": False}

        runs = client.search_runs(
            experiment_ids=[experiment.experiment_id],
            order_by=["start_time DESC"],
            max_results=limit,
        )

        result = []
        for r in runs:
            m = r.data.metrics
            import datetime
            ts = datetime.datetime.fromtimestamp(r.info.start_time / 1000).strftime("%Y-%m-%d %H:%M:%S") if r.info.start_time else None
            result.append({
                "run_id":                   r.info.run_id[:12],
                "status":                   r.info.status,
                "trained_at":               ts,
                "total_students":           int(m.get("total_students",    0)),
                "high_risk_count":          int(m.get("high_risk_count",   0)),
                "medium_risk_count":        int(m.get("medium_risk_count", 0)),
                "low_risk_count":           int(m.get("low_risk_count",    0)),
                "risk_score_mean":          round(m.get("risk_score_mean", 0), 2),
                "risk_score_std":           round(m.get("risk_score_std",  0), 2),
                "silhouette_score":         round(m["silhouette_score"],        4) if "silhouette_score"        in m else None,
                "davies_bouldin_index":     round(m["davies_bouldin_index"],    4) if "davies_bouldin_index"    in m else None,
                "calinski_harabasz_score":  round(m["calinski_harabasz_score"], 2) if "calinski_harabasz_score" in m else None,
                "inertia":                  round(m["inertia"],                 2) if "inertia"                 in m else None,
            })

        return {"runs": result, "available": True}
    except Exception as e:
        return {"runs": [], "available": False, "error": str(e)}


@router.get("/metrics")
def latest_model_metrics():
    """
    Return clustering benchmark metrics from the most recent MLflow training run.
    Available to all authenticated users.
    """
    try:
        import mlflow
        mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
        client = mlflow.MlflowClient()
        experiment = client.get_experiment_by_name(settings.MLFLOW_EXPERIMENT_NAME)
        if not experiment:
            return {"available": False, "message": "No training run found yet."}

        runs = client.search_runs(
            experiment_ids=[experiment.experiment_id],
            order_by=["start_time DESC"],
            max_results=1,
        )
        if not runs:
            return {"available": False, "message": "No training run found yet."}

        m = runs[0].data.metrics
        return {
            "available":                True,
            "run_id":                   runs[0].info.run_id,
            "trained_at":               runs[0].info.start_time,
            "total_students":           int(m.get("total_students", 0)),
            "risk_score_mean":          m.get("risk_score_mean"),
            "risk_score_std":           m.get("risk_score_std"),
            "risk_score_min":           m.get("risk_score_min"),
            "risk_score_max":           m.get("risk_score_max"),
            # Clustering quality
            "silhouette_score":         m.get("silhouette_score"),
            "davies_bouldin_index":     m.get("davies_bouldin_index"),
            "calinski_harabasz_score":  m.get("calinski_harabasz_score"),
            "inertia":                  m.get("inertia"),
        }
    except Exception as e:
        return {"available": False, "message": f"MLflow unavailable: {e}"}


@router.get("/drift")
def latest_drift():
    """
    Return the most recent data drift report.
    Includes overall drift flag, share of drifted features, and per-feature stats.
    """
    report = get_latest_drift_report()
    if not report:
        return {
            "message": "No drift report available yet. Run /api/predictions/retrain first.",
            "dataset_drift": False,
            "alert": False,
        }
    return {
        **report,
        "threshold": DRIFT_ALERT_THRESHOLD,
    }


@router.get("/drift/history")
def drift_history(limit: int = Query(default=10, ge=1, le=50)):
    """Return the last N drift reports (newest first). Default: 10, max: 50."""
    return {"reports": get_drift_history(limit=limit), "threshold": DRIFT_ALERT_THRESHOLD}


@router.post("/drift/reset")
def reset_drift_reference(current_user: dict = Depends(require_role(["Admin", "Both"]))):
    """
    Delete the reference dataset so the next retrain establishes a new baseline.
    Admin only — use when the student population changes significantly.
    """
    removed = reset_reference()
    return {
        "success": removed,
        "message": (
            "Reference dataset deleted. The next retrain will set a new baseline."
            if removed else
            "No reference dataset found — nothing to reset."
        ),
    }


@router.post("/retrain")
def retrain(current_user: dict = Depends(require_role(["Admin", "Both"]))):
    """
    Re-run the multi-stage prediction pipeline (primary endpoint):
      Stage 1 → Random Forest pre-trained on UCI data.csv (3630 students)
      Stage 2 → Rule-based: PPM US count + RPD delay
      Stage 3 → Rule-based: Stage 2 + examiner score + thesis seminar delay
    Admin only.
    """
    result = train_and_predict_rf()
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("reason"))
    return result


@router.post("/retrain-kmeans")
def retrain_kmeans(current_user: dict = Depends(require_role(["Admin", "Both"]))):
    """
    Re-run the legacy K-Means clustering pipeline.
    Kept for comparison / benchmarking purposes.
    Admin only.
    """
    result = train_and_predict()
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("reason"))
    return result


@router.get("/stage")
def prediction_stage_summary():
    """
    Return how many students are predicted at each RF stage.
    Stage 1 = enrollment features only.
    Stage 2 = + RPD / PPM data.
    Stage 3 = + examiner report.
    """
    return get_stage_summary()


@router.get("/evaluation/uci")
def uci_holdout_evaluation():
    """
    Run 80/20 stratified holdout evaluation of all three stage RF models on UCI data.

    Each stage is trained on 80% of the UCI dataset (3630 students with known
    Graduate/Dropout outcomes) and evaluated on the remaining 20% held-out set.
    This produces ground-truth-validated metrics without requiring future student data.

    Returns per-stage: Accuracy, AUC-ROC, F1, Precision, Recall, Confusion Matrix,
    5-fold CV scores, feature importances, and cross-stage improvement deltas.
    """
    result = evaluate_on_uci()
    if not result.get("available"):
        raise HTTPException(
            status_code=503,
            detail=result.get("reason", "UCI data.csv not available in container.")
        )
    return result


@router.get("/{student_id}")
def get_prediction(student_id: int):
    """Return risk prediction for a single student."""
    result = get_prediction_by_student(student_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No prediction found for student_id {student_id}. "
                   "Run /api/predictions/retrain first."
        )
    return result
