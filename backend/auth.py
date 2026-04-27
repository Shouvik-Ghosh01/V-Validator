"""
auth.py
FastAPI authentication router.

Routes:
  POST /auth/login   → returns { access_token, token_type }
  GET  /auth/me      → returns current user info (protected)

JWT tokens expire after ACCESS_TOKEN_EXPIRE_MINUTES (default 480 = 8 hours).
Secret key should be set via JWT_SECRET_KEY env variable in production.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from dotenv import load_dotenv

from database import get_users_collection, verify_password

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

SECRET_KEY  = os.getenv("JWT_SECRET_KEY", "change-this-in-production-use-a-long-random-string")
ALGORITHM   = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))  # 8 hours

# ── Schemas ───────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str
    role: str


class UserInfo(BaseModel):
    email: str
    role: str


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ── OAuth2 scheme (reads Bearer token from Authorization header) ──────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> UserInfo:
    """
    FastAPI dependency — inject into any protected route:
        current_user: Annotated[UserInfo, Depends(get_current_user)]
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str | None = payload.get("sub")
        if not email:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Verify user still exists and is active in DB
    user = get_users_collection().find_one({"email": email, "active": True})
    if not user:
        raise credentials_exception

    return UserInfo(email=user["email"], role=user["role"])


# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """
    Accepts username (email) + password as form fields.
    Returns a JWT access token on success.
    """
    users = get_users_collection()
    user = users.find_one({"email": form_data.username.lower().strip(), "active": True})

    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({"sub": user["email"], "role": user["role"]})

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        email=user["email"],
        role=user["role"],
    )


@router.get("/me", response_model=UserInfo)
def me(current_user: Annotated[UserInfo, Depends(get_current_user)]):
    """Returns the currently authenticated user's info."""
    return current_user
