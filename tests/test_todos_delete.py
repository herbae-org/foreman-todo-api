from fastapi.testclient import TestClient

from todo_api.app import app

client = TestClient(app)


def _create_todo(title: str, headers: dict) -> dict:
    return client.post("/todos", json={"title": title}, headers=headers).json()


def test_delete_removes_item(auth_headers) -> None:
    todo = _create_todo("doomed", auth_headers)
    response = client.delete(f"/todos/{todo['id']}", headers=auth_headers)
    assert response.status_code == 204
    get_response = client.get(f"/todos/{todo['id']}", headers=auth_headers)
    assert get_response.status_code == 404


def test_delete_returns_204_empty_body(auth_headers) -> None:
    todo = _create_todo("doomed", auth_headers)
    response = client.delete(f"/todos/{todo['id']}", headers=auth_headers)
    assert response.status_code == 204
    assert response.content == b""


def test_delete_missing_returns_404(auth_headers) -> None:
    response = client.delete("/todos/999", headers=auth_headers)
    assert response.status_code == 404


def test_delete_reduces_total(auth_headers) -> None:
    _create_todo("a", auth_headers)
    _create_todo("b", auth_headers)
    _create_todo("c", auth_headers)
    client.delete("/todos/1", headers=auth_headers)
    response = client.get("/todos", headers=auth_headers)
    assert response.json()["total"] == 2
