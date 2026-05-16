"""
FastAPI main application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import os
import asyncio
from apscheduler.schedulers.background import BackgroundScheduler
from app.api import auth, chat, dashboard, predictions, students
from app.api.analytics_api import router as analytics_router
from app.services.scheduler_service import check_and_send_reminders
from app.services.ml_service import train_and_predict
from app.services.alert_service import check_and_push_alerts
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Postgraduate Monitoring System",
    description="AI-powered system for monitoring graduate student progress and sending reminders",
    version="1.0.0",
)

# CORS - allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://frontend:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "null",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(dashboard.router)
app.include_router(predictions.router)
app.include_router(students.router)
app.include_router(analytics_router)

# Scheduler for automatic reminders
scheduler = BackgroundScheduler()


@app.on_event("startup")
def startup_event():
    """Start the reminder scheduler and run initial ML prediction on startup."""
    # Reminder scheduler
    scheduler.add_job(
        check_and_send_reminders,
        "cron",
        hour=settings.REMINDER_CHECK_HOUR,
        minute=settings.REMINDER_CHECK_MINUTE,
        id="daily_reminder_check",
        replace_existing=True,
    )
    # Re-run ML predictions daily (e.g. 08:05 — after reminder check)
    scheduler.add_job(
        train_and_predict,
        "cron",
        hour=settings.REMINDER_CHECK_HOUR,
        minute=settings.REMINDER_CHECK_MINUTE + 5,
        id="daily_ml_retrain",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: asyncio.run(check_and_push_alerts()),
        "interval", minutes=30,
        id="alert_check", replace_existing=True,
    )
    scheduler.start()
    print(f"[STARTUP] Scheduler started - daily check at {settings.REMINDER_CHECK_HOUR}:{settings.REMINDER_CHECK_MINUTE:02d}")

    # Run ML prediction pipeline once at startup (non-blocking)
    import threading
    def _run_ml():
        import time
        time.sleep(5)   # give DB a moment to be ready
        result = train_and_predict()
        print(f"[STARTUP] ML pipeline: {result}")
    threading.Thread(target=_run_ml, daemon=True).start()


@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "datatrain-agent"}


@app.post("/api/test-email")
async def test_email(to: str, subject: str = "Test Email", body: str = "Hello from Postgraduate Monitoring System!"):
    """Quick email test endpoint - sends directly to any address via Mailpit."""
    from app.services.email_service import send_email
    success = await send_email(to, subject, body)
    return {"success": success, "to": to, "subject": subject}


@app.get("/benchmark", response_class=HTMLResponse)
def benchmark_page():
    """Serve the standalone Model Benchmark dashboard page."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "benchmark.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()
