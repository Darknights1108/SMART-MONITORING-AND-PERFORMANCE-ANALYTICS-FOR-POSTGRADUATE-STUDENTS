"""
Authentication service - JWT token management and password hashing.
"""
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import text
from app.database import SyncSessionLocal
from app.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(supervisor_id: int, staff_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": str(supervisor_id),
        "staff_id": staff_id,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """FastAPI dependency to get the current authenticated user."""
    return decode_token(credentials.credentials)


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency to require admin role."""
    if current_user["role"] not in ("Admin", "Both"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def authenticate_user(staff_id: str, password: str) -> dict | None:
    """Authenticate a user by staff_id and password."""
    db = SyncSessionLocal()
    try:
        user = db.execute(text("""
            SELECT supervisor_id, staff_id, name, email, role, password_hash, is_active
            FROM supervisor
            WHERE staff_id = :sid
        """), {"sid": staff_id}).fetchone()

        if not user:
            return None
        if not user[6]:  # is_active
            return None
        if not verify_password(password, user[5]):
            return None

        return {
            "supervisor_id": user[0],
            "staff_id": user[1],
            "name": user[2],
            "email": user[3],
            "role": user[4],
        }
    finally:
        db.close()
