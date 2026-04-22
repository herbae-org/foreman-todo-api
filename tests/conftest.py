import uuid

import pytest
from fastapi.testclient import TestClient

from todo_api import db as db_module
from todo_api import rate_limit
from todo_api.app import app


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    conn = db_module.get_connection()
    db_module.init_schema(conn)
    conn.close()
    rate_limit.reset_buckets()


@pytest.fixture
def auth_headers():
    client = TestClient(app)
    email = f"test-user-{uuid.uuid4()}@example.com"
    client.post("/auth/register", json={"email": email, "password": "testpass123"})
    resp = client.post("/auth/login", json={"email": email, "password": "testpass123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
