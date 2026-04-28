"""
Predictions API — exposes ML risk prediction results.

Endpoints:
  GET  /api/predictions/              — all students with risk scores
  GET  /api/predictions/distribution  — label counts (for dashboard charts)
  GET  /api/predictions/{student_id}  — single student prediction
  POST /api/predictions/retrain       — re-run the ML pipeline (admin only)
"""
from fastapi import APIRouter, HTTPException, Depends
from app.services.ml_service import (
    get_all_predictions,
    get_prediction_by_student,
    get_risk_distribution,
    train_and_predict,
)
from app.api.auth import require_role   # reuse existing auth dependency

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


@router.post("/retrain")
def retrain(current_user: dict = Depends(require_role(["Admin", "Both"]))):
    """
    Re-run the full ML pipeline.
    Admin only — triggers on demand (e.g., after new PPM data is entered).
    """
    result = train_and_predict()
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("reason"))
    return result
