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

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "change-this-in-production-use-a-long-random-string"
)

ALGORITHM = "HS256"

TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480")
)

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# ── Schemas ───────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str
    role: str


class UserInfo(BaseModel):
    email: str
    role: str


# ── JWT Helpers ───────────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = (
        datetime.now(timezone.utc)
        + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    )

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


# ── OAuth2 ────────────────────────────────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ── Current User Dependency ───────────────────────────────────────────────────

def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)]
) -> UserInfo:

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        email = payload.get("sub")
        role = payload.get("role")

        if not email:
            raise credentials_exception

        return UserInfo(
            email=email,
            role=role
        )

    except JWTError:
        raise credentials_exception


# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: Annotated[
        OAuth2PasswordRequestForm,
        Depends()
    ]
):
    """
    Accepts username (email) + password.
    Returns JWT access token.
    """

    email = form_data.username.lower().strip()
    password = form_data.password

    if (
        email != ADMIN_EMAIL.lower()
        or password != ADMIN_PASSWORD
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        {
            "sub": ADMIN_EMAIL,
            "role": "admin",
        }
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        email=ADMIN_EMAIL,
        role="admin",
    )


@router.get("/me", response_model=UserInfo)
def me(
    current_user: Annotated[
        UserInfo,
        Depends(get_current_user)
    ]
):
    """
    Returns currently authenticated user.
    """
    return current_user