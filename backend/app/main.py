"""
FastAPI main application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from app.api import auth, chat, dashboard
from app.services.scheduler_service import check_and_send_reminders
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="DataTrain - Postgraduate Student Management Agent",
    description="AI-powered system for monitoring graduate student progress and sending reminders",
    version="1.0.0",
)

# CORS - allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000", "http://localhost:5500", "http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(dashboard.router)

# Scheduler for automatic reminders
scheduler = BackgroundScheduler()


@app.on_event("startup")
def startup_event():
    """Start the reminder scheduler on app startup."""
    scheduler.add_job(
        check_and_send_reminders,
        "cron",
        hour=settings.REMINDER_CHECK_HOUR,
        minute=settings.REMINDER_CHECK_MINUTE,
        id="daily_reminder_check",
        replace_existing=True,
    )
    scheduler.start()
    print(f"[STARTUP] Scheduler started - daily check at {settings.REMINDER_CHECK_HOUR}:{settings.REMINDER_CHECK_MINUTE:02d}")


@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "datatrain-agent"}


@app.post("/api/test-email")
async def test_email(to: str, subject: str = "Test Email", body: str = "Hello from DataTrain!"):
    """Quick email test endpoint - sends directly to any address via Mailpit."""
    from app.services.email_service import send_email
    success = await send_email(to, subject, body)
    return {"success": success, "to": to, "subject": subject}
