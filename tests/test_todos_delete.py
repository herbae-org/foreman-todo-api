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


def test_delete_removes_item() -> None:
    todo = _create_todo("doomed")
    response = client.delete(f"/todos/{todo['id']}")
    assert response.status_code == 204
    get_response = client.get(f"/todos/{todo['id']}")
    assert get_response.status_code == 404


def test_delete_returns_204_empty_body() -> None:
    todo = _create_todo("doomed")
    response = client.delete(f"/todos/{todo['id']}")
    assert response.status_code == 204
    assert response.content == b""


def test_delete_missing_returns_404() -> None:
    response = client.delete("/todos/999")
    assert response.status_code == 404


def test_delete_reduces_total() -> None:
    _create_todo("a")
    _create_todo("b")
    _create_todo("c")
    client.delete("/todos/1")
    response = client.get("/todos")
    assert response.json()["total"] == 2
