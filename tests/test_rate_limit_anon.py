import uuid

from fastapi import Request
from fastapi.testclient import TestClient

from todo_api import rate_limit
from todo_api.app import app

client = TestClient(app)


def _unique_email() -> str:
    return f"anon-{uuid.uuid4()}@example.com"


def test_register_limited_to_10_per_minute_per_ip() -> None:
    for i in range(10):
        resp = client.post(
            "/auth/register",
            json={"email": _unique_email(), "password": "testpass123"},
        )
        assert resp.status_code in (201, 409), f"Request {i+1}: {resp.status_code}"
    resp = client.post(
        "/auth/register",
        json={"email": _unique_email(), "password": "testpass123"},
    )
    assert resp.status_code == 429


def test_login_shares_bucket_with_register() -> None:
    for i in range(5):
        client.post(
            "/auth/register",
            json={"email": _unique_email(), "password": "testpass123"},
        )
    email = _unique_email()
    client.post("/auth/register", json={"email": email, "password": "testpass123"})
    rate_limit.reset_buckets()
    for i in range(5):
        client.post(
            "/auth/register",
            json={"email": _unique_email(), "password": "testpass123"},
        )
    for i in range(5):
        client.post(
            "/auth/login",
            json={"email": email, "password": "testpass123"},
        )
    resp = client.post(
        "/auth/login",
        json={"email": email, "password": "testpass123"},
    )
    assert resp.status_code == 429


def test_different_ips_have_independent_buckets() -> None:
    fake_ip = ["10.0.0.1"]

    def override_anon_rate_limit(request: Request) -> str:
        host = fake_ip[0]
        bucket = rate_limit._get_bucket(
            f"ip:{host}", rate_limit._ANON_CAPACITY, rate_limit._ANON_REFILL
        )
        if not bucket.consume():
            from fastapi import HTTPException
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": rate_limit._retry_after(rate_limit._ANON_REFILL)},
            )
        return host

    app.dependency_overrides[rate_limit.anon_rate_limit] = override_anon_rate_limit
    try:
        for _ in range(10):
            client.post(
                "/auth/register",
                json={"email": _unique_email(), "password": "testpass123"},
            )
        resp = client.post(
            "/auth/register",
            json={"email": _unique_email(), "password": "testpass123"},
        )
        assert resp.status_code == 429

        fake_ip[0] = "10.0.0.2"
        resp = client.post(
            "/auth/register",
            json={"email": _unique_email(), "password": "testpass123"},
        )
        assert resp.status_code == 201
    finally:
        app.dependency_overrides.pop(rate_limit.anon_rate_limit, None)


def test_429_response_includes_retry_after() -> None:
    for _ in range(10):
        client.post(
            "/auth/register",
            json={"email": _unique_email(), "password": "testpass123"},
        )
    resp = client.post(
        "/auth/register",
        json={"email": _unique_email(), "password": "testpass123"},
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    val = int(resp.headers["Retry-After"])
    assert val >= 1
