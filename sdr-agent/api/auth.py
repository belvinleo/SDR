"""
Auth router — JWT login and signup.
POST /auth/signup  → creates user, returns access_token
POST /auth/login   → verifies credentials, returns access_token
"""
from __future__ import annotations
import os, structlog
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import jwt
import asyncpg
import bcrypt

from db.users import create_user, get_user_by_email

log = structlog.get_logger()
router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-secret-change-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash_password(password: str) -> str:
    safe_password = password[:72]
    return pwd_context.hash(safe_password)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_token(user_id: str, workspace_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": user_id,
        "workspace_id": workspace_id,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = ""
    company: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/signup")
async def signup(payload: SignupRequest):
    """Create a new account and return a JWT."""
    if len(payload.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    try:
        user = await create_user(
            email=str(payload.email),
            hashed_password=_hash_password(payload.password),
            full_name=payload.name,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    token = _create_token(str(user["id"]), str(user["workspace_id"]))
    log.info("auth.signup", email=payload.email, workspace_id=user["workspace_id"])
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login")
async def login(payload: LoginRequest):
    """Verify credentials and return a JWT."""
    user = await get_user_by_email(str(payload.email))

    if not user or not _verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = _create_token(str(user["id"]), str(user["workspace_id"]))
    log.info("auth.login", email=payload.email)
    return {"access_token": token, "token_type": "bearer"}

if not hasattr(bcrypt, "__about__"):
    bcrypt.__about__ = type("about", (), {"__version__": "4.0.0"})
