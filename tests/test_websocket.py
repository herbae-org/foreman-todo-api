import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from todo_api.app import app
from todo_api.auth import JWT_ALGORITHM, JWT_SECRET
from todo_api.events import bus


def _register_and_login(client: TestClient) -> tuple[int, dict[str, str]]:
    email = f"ws-{uuid.uuid4()}@example.com"
    reg = client.post("/auth/register", json={"email": email, "password": "testpass123"})
    user_id = reg.json()["id"]
    resp = client.post("/auth/login", json={"email": email, "password": "testpass123"})
    token = resp.json()["access_token"]
    return user_id, {"Authorization": f"Bearer {token}"}


def test_ws_rejects_missing_auth():
    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/todos"):
            pass


def test_ws_rejects_invalid_token():
    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect(
            "/ws/todos", headers={"Authorization": "Bearer not.a.jwt"}
        ):
            pass


def test_ws_rejects_expired_token():
    client = TestClient(app)
    payload = {
        "sub": "1",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=60),
    }
    expired_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    with pytest.raises(Exception):
        with client.websocket_connect(
            "/ws/todos", headers={"Authorization": f"Bearer {expired_token}"}
        ):
            pass


def test_ws_accepts_valid_token_and_sends_hello():
    client = TestClient(app)
    user_id, headers = _register_and_login(client)
    with client.websocket_connect("/ws/todos", headers=headers) as ws:
        hello = ws.receive_json()
        assert hello == {"type": "hello", "user_id": user_id}


def test_ws_receives_created_on_post():
    client = TestClient(app)
    user_id, headers = _register_and_login(client)
    with client.websocket_connect("/ws/todos", headers=headers) as ws:
        ws.receive_json()  # hello

        resp = client.post("/todos", json={"title": "ws test"}, headers=headers)
        assert resp.status_code == 201
        todo = resp.json()

        event = ws.receive_json()
        assert event["type"] == "created"
        assert event["todo"]["id"] == todo["id"]
        assert event["todo"]["title"] == "ws test"


def test_ws_receives_updated_on_patch():
    client = TestClient(app)
    user_id, headers = _register_and_login(client)
    with client.websocket_connect("/ws/todos", headers=headers) as ws:
        ws.receive_json()  # hello

        resp = client.post("/todos", json={"title": "original"}, headers=headers)
        todo_id = resp.json()["id"]
        ws.receive_json()  # created event

        client.patch(f"/todos/{todo_id}", json={"title": "updated"}, headers=headers)

        event = ws.receive_json()
        assert event["type"] == "updated"
        assert event["todo"]["title"] == "updated"


def test_ws_receives_deleted_on_delete():
    client = TestClient(app)
    user_id, headers = _register_and_login(client)
    with client.websocket_connect("/ws/todos", headers=headers) as ws:
        ws.receive_json()  # hello

        resp = client.post("/todos", json={"title": "to-delete"}, headers=headers)
        todo = resp.json()
        ws.receive_json()  # created event

        client.delete(f"/todos/{todo['id']}", headers=headers)

        event = ws.receive_json()
        assert event["type"] == "deleted"
        assert event["todo"]["id"] == todo["id"]
        assert event["todo"]["title"] == "to-delete"


def test_ws_isolates_by_user():
    client = TestClient(app)
    _, headers_a = _register_and_login(client)
    _, headers_b = _register_and_login(client)

    with client.websocket_connect("/ws/todos", headers=headers_a) as ws:
        ws.receive_json()  # hello

        # User B creates a todo — user A should NOT see it
        client.post("/todos", json={"title": "b's todo"}, headers=headers_b)

        # User A creates a todo — user A SHOULD see it
        client.post("/todos", json={"title": "a's todo"}, headers=headers_a)

        event = ws.receive_json()
        assert event["type"] == "created"
        assert event["todo"]["title"] == "a's todo"


def test_ws_receives_tag_events():
    client = TestClient(app)
    user_id, headers = _register_and_login(client)

    tag_resp = client.post("/tags", json={"name": "urgent"}, headers=headers)
    tag_id = tag_resp.json()["id"]

    with client.websocket_connect("/ws/todos", headers=headers) as ws:
        ws.receive_json()  # hello

        resp = client.post("/todos", json={"title": "tagged"}, headers=headers)
        todo_id = resp.json()["id"]
        created = ws.receive_json()
        assert created["type"] == "created"

        client.post(
            f"/todos/{todo_id}/tags", json={"tag_ids": [tag_id]}, headers=headers
        )
        updated = ws.receive_json()
        assert updated["type"] == "updated"
        assert any(t["id"] == tag_id for t in updated["todo"]["tags"])


def test_ws_cleanup_on_disconnect():
    client = TestClient(app)
    user_id, headers = _register_and_login(client)

    with client.websocket_connect("/ws/todos", headers=headers) as ws:
        ws.receive_json()  # hello
        assert bus.subscriber_count(user_id) == 1

    assert bus.subscriber_count(user_id) == 0
