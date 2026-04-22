from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Header, HTTPException
from passlib.context import CryptContext

from todo_api.db import get_connection

_TESTING = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ

if _TESTING:
    JWT_SECRET: str = os.environ.get("TODO_JWT_SECRET", "test-secret-do-not-use-in-production")
elif "TODO_JWT_SECRET" in os.environ:
    JWT_SECRET = os.environ["TODO_JWT_SECRET"]
else:
    raise RuntimeError("TODO_JWT_SECRET environment variable is required")

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_SECONDS = 3600

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=JWT_EXPIRY_SECONDS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> int:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    return int(payload["sub"])


def get_current_user(authorization: str | None = Header(default=None)) -> int:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    token = authorization.removeprefix("Bearer ")
    try:
        user_id = decode_token(token)
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    conn = get_connection()
    row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return user_id
