"""
Auth API endpoints - login, token refresh.
Also exports reusable FastAPI dependencies: get_current_user, require_role.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from app.services.auth_service import authenticate_user, create_token
from app.services.auth_service import decode_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

_bearer = HTTPBearer(auto_error=False)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    """FastAPI dependency — validates Bearer JWT and returns the decoded payload."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_role(allowed_roles: list[str]):
    """FastAPI dependency factory — ensures user has one of the allowed roles."""
    def _check(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return _check


class LoginRequest(BaseModel):
    staff_id: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    user = authenticate_user(req.staff_id, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid staff ID or password",
        )

    token = create_token(user["supervisor_id"], user["staff_id"], user["role"])

    return LoginResponse(
        access_token=token,
        user={
            "supervisor_id": user["supervisor_id"],
            "staff_id": user["staff_id"],
            "name": user["name"],
            "role": user["role"],
        },
    )
