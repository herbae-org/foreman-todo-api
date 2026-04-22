import pytest
from fastapi.testclient import TestClient

from todo_api import db as db_module
from todo_api.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    db_module.init_schema(db_module.get_connection())


def _create_todo(title: str) -> dict:
    return client.post("/todos", json={"title": title}).json()


def _create_tag(name: str) -> dict:
    return client.post("/tags", json={"name": name}).json()


def test_assign_tags_returns_todo_with_tags() -> None:
    todo = _create_todo("task")
    t1 = _create_tag("work")
    t2 = _create_tag("urgent")
    response = client.post(
        f"/todos/{todo['id']}/tags", json={"tag_ids": [t1["id"], t2["id"]]}
    )
    assert response.status_code == 200
    data = response.json()
    tag_names = sorted(t["name"] for t in data["tags"])
    assert tag_names == ["urgent", "work"]


def test_assign_tags_idempotent() -> None:
    todo = _create_todo("task")
    tag = _create_tag("work")
    client.post(f"/todos/{todo['id']}/tags", json={"tag_ids": [tag["id"]]})
    response = client.post(
        f"/todos/{todo['id']}/tags", json={"tag_ids": [tag["id"]]}
    )
    assert response.status_code == 200
    assert len(response.json()["tags"]) == 1


def test_remove_tag_returns_204() -> None:
    todo = _create_todo("task")
    tag = _create_tag("work")
    client.post(f"/todos/{todo['id']}/tags", json={"tag_ids": [tag["id"]]})
    response = client.delete(f"/todos/{todo['id']}/tags/{tag['id']}")
    assert response.status_code == 204
    get_resp = client.get(f"/todos/{todo['id']}")
    assert get_resp.json()["tags"] == []


def test_remove_tag_nonexistent_link_returns_404() -> None:
    todo = _create_todo("task")
    _create_tag("work")
    response = client.delete(f"/todos/{todo['id']}/tags/999")
    assert response.status_code == 404


def test_assign_unknown_tag_returns_400() -> None:
    todo = _create_todo("task")
    response = client.post(
        f"/todos/{todo['id']}/tags", json={"tag_ids": [999]}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Unknown tag_id: 999"}


def test_assign_tags_unknown_todo_returns_404() -> None:
    tag = _create_tag("work")
    response = client.post(
        "/todos/999/tags", json={"tag_ids": [tag["id"]]}
    )
    assert response.status_code == 404


def test_delete_todo_cascades_todo_tags() -> None:
    todo = _create_todo("doomed")
    tag = _create_tag("temp")
    client.post(f"/todos/{todo['id']}/tags", json={"tag_ids": [tag["id"]]})
    client.delete(f"/todos/{todo['id']}")
    get_resp = client.get(f"/todos/{todo['id']}")
    assert get_resp.status_code == 404


def test_new_todo_has_empty_tags() -> None:
    response = client.post("/todos", json={"title": "fresh"})
    assert response.status_code == 201
    assert response.json()["tags"] == []
