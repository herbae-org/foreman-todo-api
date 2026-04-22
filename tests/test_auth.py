import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from todo_api import db as db_module
from todo_api.app import app
from todo_api.auth import JWT_ALGORITHM, JWT_SECRET

client = TestClient(app)


def _register(email: str, password: str = "testpass123"):
    return client.post("/auth/register", json={"email": email, "password": password})


def _login(email: str, password: str = "testpass123"):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_register_creates_user() -> None:
    email = f"user-{uuid.uuid4()}@example.com"
    resp = _register(email)
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == email
    assert "id" in data
    assert "created_at" in data
    datetime.fromisoformat(data["created_at"])
    assert "password" not in data
    assert "password_hash" not in data


def test_register_rejects_duplicate_email() -> None:
    email = f"dup-{uuid.uuid4()}@example.com"
    _register(email)
    resp = _register(email)
    assert resp.status_code == 409
    assert resp.json() == {"detail": "Email already registered"}


def test_register_rejects_invalid_email() -> None:
    resp = _register("not-an-email")
    assert resp.status_code == 422


def test_register_rejects_short_password() -> None:
    email = f"short-{uuid.uuid4()}@example.com"
    resp = _register(email, password="1234567")
    assert resp.status_code == 422


def test_login_returns_token() -> None:
    email = f"login-{uuid.uuid4()}@example.com"
    _register(email)
    resp = _login(email)
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 3600


def test_login_wrong_password_returns_401() -> None:
    email = f"wrong-{uuid.uuid4()}@example.com"
    _register(email)
    resp = _login(email, password="wrongpassword")
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid credentials"}


def test_login_unknown_user_returns_401() -> None:
    resp = _login("nonexistent@example.com", password="whatever123")
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid credentials"}


def test_me_returns_current_user() -> None:
    email = f"me-{uuid.uuid4()}@example.com"
    _register(email)
    token = _login(email).json()["access_token"]
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == email
    assert "id" in data
    assert "created_at" in data


def test_me_unauthorized_without_header() -> None:
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_me_unauthorized_with_malformed_token() -> None:
    resp = client.get(
        "/auth/me", headers={"Authorization": "Bearer not.a.jwt"}
    )
    assert resp.status_code == 401


def test_me_unauthorized_with_expired_token() -> None:
    expired_payload = {
        "sub": "1",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=10),
    }
    token = jwt.encode(expired_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    resp = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401


async def test_password_is_bcrypt_hashed_in_db() -> None:
    email = f"hash-{uuid.uuid4()}@example.com"
    password = "testpass123"
    _register(email, password)
    conn = await db_module.get_connection()
    try:
        cursor = await conn.execute(
            "SELECT password_hash FROM users WHERE email = ?", (email,)
        )
        row = await cursor.fetchone()
    finally:
        await conn.close()
    assert row is not None
    assert row["password_hash"].startswith("$2b$")
    assert row["password_hash"] != password
