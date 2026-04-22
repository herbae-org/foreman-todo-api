import uuid

from fastapi.testclient import TestClient

from todo_api import db as db_module
from todo_api.app import app

client = TestClient(app)


def _make_user() -> dict:
    email = f"user-{uuid.uuid4()}@example.com"
    client.post("/auth/register", json={"email": email, "password": "testpass123"})
    resp = client.post("/auth/login", json={"email": email, "password": "testpass123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_todo(title: str, headers: dict) -> dict:
    return client.post("/todos", json={"title": title}, headers=headers).json()


def _create_tag(name: str, headers: dict) -> dict:
    return client.post("/tags", json={"name": name}, headers=headers).json()


def test_users_cannot_see_others_todos() -> None:
    h_a = _make_user()
    h_b = _make_user()
    _create_todo("secret", h_a)
    resp = client.get("/todos", headers=h_b)
    assert resp.json() == {"items": [], "total": 0}


def test_users_cannot_fetch_others_todos_by_id() -> None:
    h_a = _make_user()
    h_b = _make_user()
    todo = _create_todo("secret", h_a)
    resp = client.get(f"/todos/{todo['id']}", headers=h_b)
    assert resp.status_code == 404


def test_users_cannot_patch_others_todos() -> None:
    h_a = _make_user()
    h_b = _make_user()
    todo = _create_todo("secret", h_a)
    resp = client.patch(
        f"/todos/{todo['id']}", json={"title": "hacked"}, headers=h_b
    )
    assert resp.status_code == 404


def test_users_cannot_delete_others_todos() -> None:
    h_a = _make_user()
    h_b = _make_user()
    todo = _create_todo("secret", h_a)
    resp = client.delete(f"/todos/{todo['id']}", headers=h_b)
    assert resp.status_code == 404


def test_users_cannot_see_others_tags() -> None:
    h_a = _make_user()
    h_b = _make_user()
    _create_tag("private", h_a)
    resp = client.get("/tags", headers=h_b)
    assert resp.json() == {"items": [], "total": 0}


def test_users_cannot_attach_others_tags() -> None:
    h_a = _make_user()
    h_b = _make_user()
    tag = _create_tag("a-tag", h_a)
    todo = _create_todo("b-todo", h_b)
    resp = client.post(
        f"/todos/{todo['id']}/tags",
        json={"tag_ids": [tag["id"]]},
        headers=h_b,
    )
    assert resp.status_code == 400
    assert "Unknown tag_id" in resp.json()["detail"]


def test_tag_name_can_collide_across_users() -> None:
    h_a = _make_user()
    h_b = _make_user()
    r1 = client.post("/tags", json={"name": "work"}, headers=h_a)
    r2 = client.post("/tags", json={"name": "work"}, headers=h_b)
    assert r1.status_code == 201
    assert r2.status_code == 201


def test_deleting_user_cascades_todos_and_tags() -> None:
    h = _make_user()
    _create_todo("t1", h)
    _create_todo("t2", h)
    _create_tag("tag1", h)

    conn = db_module.get_connection()
    user_row = conn.execute("SELECT id FROM users ORDER BY id DESC LIMIT 1").fetchone()
    user_id = user_row["id"]

    assert conn.execute("SELECT COUNT(*) FROM todos WHERE user_id = ?", (user_id,)).fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM tags WHERE user_id = ?", (user_id,)).fetchone()[0] == 1

    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM todos WHERE user_id = ?", (user_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM tags WHERE user_id = ?", (user_id,)).fetchone()[0] == 0
    conn.close()
