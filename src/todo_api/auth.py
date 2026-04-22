from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Header, HTTPException, WebSocket, status
from fastapi.exceptions import WebSocketException

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

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=JWT_EXPIRY_SECONDS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> int:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    return int(payload["sub"])


async def get_current_user(authorization: str | None = Header(default=None)) -> int:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    token = authorization.removeprefix("Bearer ")
    try:
        user_id = decode_token(token)
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    conn = await get_connection()
    try:
        cursor = await conn.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
    finally:
        await conn.close()
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return user_id


def decode_token_from_ws_headers(ws: WebSocket) -> int:
    auth = ws.headers.get("authorization")
    if not auth or not auth.startswith("Bearer "):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    try:
        return decode_token(auth.removeprefix("Bearer "))
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
