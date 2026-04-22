import pytest
from fastapi.testclient import TestClient

from todo_api import app as app_module
from todo_api.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_todos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_todos", [])


def _create_todo(title: str) -> dict:
    return client.post("/todos", json={"title": title}).json()


def test_patch_updates_title() -> None:
    todo = _create_todo("original")
    response = client.patch(f"/todos/{todo['id']}", json={"title": "new"})
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "new"
    assert data["done"] is False


def test_patch_marks_done() -> None:
    todo = _create_todo("task")
    response = client.patch(f"/todos/{todo['id']}", json={"done": True})
    assert response.status_code == 200
    data = response.json()
    assert data["done"] is True
    assert data["title"] == "task"


def test_patch_both_fields_at_once() -> None:
    todo = _create_todo("old")
    response = client.patch(f"/todos/{todo['id']}", json={"title": "x", "done": True})
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "x"
    assert data["done"] is True


def test_patch_empty_body_is_noop() -> None:
    todo = _create_todo("unchanged")
    response = client.patch(f"/todos/{todo['id']}", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "unchanged"
    assert data["done"] is False


def test_patch_missing_id_returns_404() -> None:
    response = client.patch("/todos/999", json={"title": "nope"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_patch_rejects_empty_title() -> None:
    todo = _create_todo("valid")
    response = client.patch(f"/todos/{todo['id']}", json={"title": ""})
    assert response.status_code == 422


def test_patch_rejects_extra_fields() -> None:
    todo = _create_todo("valid")
    response = client.patch(
        f"/todos/{todo['id']}", json={"created_at": "2020-01-01T00:00:00Z"}
    )
    assert response.status_code == 422


def test_patch_preserves_created_at() -> None:
    todo = _create_todo("keep time")
    original_created_at = todo["created_at"]
    response = client.patch(f"/todos/{todo['id']}", json={"title": "new title"})
    assert response.status_code == 200
    assert response.json()["created_at"] == original_created_at
