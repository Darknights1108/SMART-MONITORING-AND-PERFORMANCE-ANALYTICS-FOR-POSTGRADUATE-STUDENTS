"""
Auth API endpoints - login, token refresh.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.services.auth_service import authenticate_user, create_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


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
