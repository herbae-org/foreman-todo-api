import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from todo_api import rate_limit
from todo_api.app import app

client = TestClient(app)


def _make_user() -> dict:
    email = f"rl-{uuid.uuid4()}@example.com"
    client.post("/auth/register", json={"email": email, "password": "testpass123"})
    resp = client.post("/auth/login", json={"email": email, "password": "testpass123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_authed_user_gets_60_requests_per_minute() -> None:
    headers = _make_user()
    for i in range(60):
        resp = client.get("/todos", headers=headers)
        assert resp.status_code == 200, f"Request {i+1} failed with {resp.status_code}"


def test_authed_user_hits_429_on_61st() -> None:
    headers = _make_user()
    for _ in range(60):
        client.get("/todos", headers=headers)
    resp = client.get("/todos", headers=headers)
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert resp.headers["Retry-After"].isdigit()


def test_two_users_have_independent_buckets() -> None:
    headers_a = _make_user()
    headers_b = _make_user()
    for _ in range(60):
        client.get("/todos", headers=headers_a)
    assert client.get("/todos", headers=headers_a).status_code == 429
    assert client.get("/todos", headers=headers_b).status_code == 200


def test_bucket_resets_on_refill() -> None:
    headers = _make_user()
    for _ in range(60):
        client.get("/todos", headers=headers)
    assert client.get("/todos", headers=headers).status_code == 429

    mono = [0.0]
    original_consume = rate_limit.TokenBucket.consume

    def patched_consume(self, n=1, now=None):
        return original_consume(self, n, now=mono[0])

    mono[0] = 1e9
    with patch.object(rate_limit.TokenBucket, "consume", patched_consume):
        resp = client.get("/todos", headers=headers)
    assert resp.status_code == 200


def test_health_is_not_rate_limited() -> None:
    for _ in range(100):
        resp = client.get("/health")
        assert resp.status_code == 200
