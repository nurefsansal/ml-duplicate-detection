from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.services.auth_service import authenticate_user, create_access_token

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(request: LoginRequest):
    if not authenticate_user(request.username, request.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanici adi veya sifre hatali",
        )

    token = create_access_token(request.username)
    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "user": {"username": request.username},
    }
