"""
ML Agent Tools — wrap ml_service query helpers as smolagents tools
so the AI agent can answer risk-related questions naturally.
"""
from smolagents import tool
from app.services.ml_service import (
    get_prediction_by_student,
    get_all_predictions,
    get_high_risk_students,
    get_risk_distribution,
    train_and_predict,
)
from app.tools.sanitizer import sanitize_tool_output
from app.database import SyncSessionLocal
from sqlalchemy import text


@tool
def get_student_risk_prediction(student_id: int) -> str:
    """
    Get the ML risk prediction for a specific student by their database student_id.
    Returns risk score (0-100), risk label (Low/Medium/High), and key risk factors.

    Args:
        student_id: The integer student_id from the database (NOT the student ID number).
    """
    pred = get_prediction_by_student(student_id)
    if not pred:
        return (
            f"No risk prediction found for student_id {student_id}. "
            "The ML model may not have been run yet. "
            "Ask the admin to retrain via POST /api/predictions/retrain."
        )

    factors = pred["key_risk_factors"]
    factors_str = "\n  - " + "\n  - ".join(factors) if factors else "  None identified"

    result = (
        f"Risk Prediction for {pred['student_name']} ({pred['student_id_number']})\n"
        f"  Programme  : {pred['program']} ({pred['degree_type']}, {pred['study_method']})\n"
        f"  Faculty    : {pred['faculty']}\n"
        f"  Risk Score : {pred['risk_score']:.1f} / 100\n"
        f"  Risk Label : {pred['risk_label']}\n"
        f"  Cluster    : Group {pred['cluster_id']}\n"
        f"  Key Factors:{factors_str}\n"
        f"  Last Updated: {pred['predicted_at']}"
    )
    return sanitize_tool_output(result)


@tool
def get_high_risk_students_list() -> str:
    """
    Return a list of all students currently predicted as HIGH risk of delayed graduation.
    Includes their risk score and top risk factors.
    """
    students = get_high_risk_students()
    if not students:
        return "No students are currently classified as High risk."

    lines = [f"High-Risk Students ({len(students)} total):\n"]
    for s in students:
        factors = s["key_risk_factors"]
        top_factor = factors[0] if factors else "No specific factor"
        lines.append(
            f"  [{s['risk_score']:.0f}/100] {s['student_name']} ({s['student_id_number']}) "
            f"— {s['degree_type']}, {s['study_method']} — Top risk: {top_factor}"
        )
    return sanitize_tool_output("\n".join(lines))


@tool
def get_risk_summary() -> str:
    """
    Get a summary of the risk prediction distribution across all students.
    Shows how many students are Low, Medium, and High risk.
    Useful for dashboard overview questions.
    """
    dist = get_risk_distribution()
    if not dist:
        return "No risk predictions available. The ML model has not been run yet."

    total = sum(dist.values())
    high   = dist.get("High",   0)
    medium = dist.get("Medium", 0)
    low    = dist.get("Low",    0)

    result = (
        f"Risk Prediction Summary ({total} students total):\n"
        f"  🔴 High Risk   : {high:3d} students ({high/total*100:.1f}%)\n"
        f"  🟡 Medium Risk : {medium:3d} students ({medium/total*100:.1f}%)\n"
        f"  🟢 Low Risk    : {low:3d} students ({low/total*100:.1f}%)\n"
    )
    return sanitize_tool_output(result)


@tool
def get_risk_predictions_by_label(risk_label: str) -> str:
    """
    Get all students with a specific risk label.
    Use this to answer questions like 'who is at medium risk?' or 'show me low risk students'.

    Args:
        risk_label: One of 'High', 'Medium', or 'Low' (case-sensitive).
    """
    valid = {"High", "Medium", "Low"}
    if risk_label not in valid:
        return f"Invalid risk_label '{risk_label}'. Must be one of: {', '.join(valid)}"

    all_preds = get_all_predictions()
    filtered = [p for p in all_preds if p["risk_label"] == risk_label]

    if not filtered:
        return f"No students currently classified as {risk_label} risk."

    lines = [f"{risk_label} Risk Students ({len(filtered)} total):\n"]
    for s in filtered:
        factors = s["key_risk_factors"]
        top = factors[0] if factors else "-"
        lines.append(
            f"  [{s['risk_score']:.0f}/100] {s['student_name']} ({s['student_id_number']}) "
            f"— {s['degree_type']}, {s['study_method']}"
        )
        lines.append(f"    Reason: {top}")
    return sanitize_tool_output("\n".join(lines))


@tool
def retrain_risk_model() -> str:
    """
    Re-run the ML risk prediction pipeline to refresh all predictions.
    Use this when asked to update predictions or after new data has been entered.
    Returns a summary of the new prediction distribution.
    """
    result = train_and_predict()
    if result.get("status") == "error":
        return f"ML pipeline failed: {result.get('reason', 'Unknown error')}"
    if result.get("status") == "skipped":
        return f"ML pipeline skipped: {result.get('reason')}"

    dist = result.get("distribution", {})
    return (
        f"Risk predictions updated successfully.\n"
        f"  Total students : {result['total_students']}\n"
        f"  High Risk      : {dist.get('High',   0)}\n"
        f"  Medium Risk    : {dist.get('Medium', 0)}\n"
        f"  Low Risk       : {dist.get('Low',    0)}\n"
    )
