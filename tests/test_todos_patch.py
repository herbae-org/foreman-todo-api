from fastapi.testclient import TestClient

from todo_api.app import app

client = TestClient(app)


def _create_todo(title: str, headers: dict) -> dict:
    return client.post("/todos", json={"title": title}, headers=headers).json()


def test_patch_updates_title(auth_headers) -> None:
    todo = _create_todo("original", auth_headers)
    response = client.patch(f"/todos/{todo['id']}", json={"title": "new"}, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "new"
    assert data["done"] is False


def test_patch_marks_done(auth_headers) -> None:
    todo = _create_todo("task", auth_headers)
    response = client.patch(f"/todos/{todo['id']}", json={"done": True}, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["done"] is True
    assert data["title"] == "task"


def test_patch_both_fields_at_once(auth_headers) -> None:
    todo = _create_todo("old", auth_headers)
    response = client.patch(
        f"/todos/{todo['id']}", json={"title": "x", "done": True}, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "x"
    assert data["done"] is True


def test_patch_empty_body_is_noop(auth_headers) -> None:
    todo = _create_todo("unchanged", auth_headers)
    response = client.patch(f"/todos/{todo['id']}", json={}, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "unchanged"
    assert data["done"] is False


def test_patch_missing_id_returns_404(auth_headers) -> None:
    response = client.patch("/todos/999", json={"title": "nope"}, headers=auth_headers)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_patch_rejects_empty_title(auth_headers) -> None:
    todo = _create_todo("valid", auth_headers)
    response = client.patch(f"/todos/{todo['id']}", json={"title": ""}, headers=auth_headers)
    assert response.status_code == 422


def test_patch_rejects_extra_fields(auth_headers) -> None:
    todo = _create_todo("valid", auth_headers)
    response = client.patch(
        f"/todos/{todo['id']}",
        json={"created_at": "2020-01-01T00:00:00Z"},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_patch_preserves_created_at(auth_headers) -> None:
    todo = _create_todo("keep time", auth_headers)
    original_created_at = todo["created_at"]
    response = client.patch(
        f"/todos/{todo['id']}", json={"title": "new title"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["created_at"] == original_created_at
