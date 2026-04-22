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


def _mark_done(todo_id: int) -> None:
    client.patch(f"/todos/{todo_id}", json={"done": True})


def test_filter_done_true() -> None:
    t1 = _create_todo("a")
    t2 = _create_todo("b")
    _create_todo("c")
    _mark_done(t1["id"])
    _mark_done(t2["id"])
    response = client.get("/todos", params={"done": "true"})
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 2


def test_filter_done_false() -> None:
    t1 = _create_todo("a")
    t2 = _create_todo("b")
    _create_todo("c")
    _mark_done(t1["id"])
    _mark_done(t2["id"])
    response = client.get("/todos", params={"done": "false"})
    data = response.json()
    assert len(data["items"]) == 1
    assert data["total"] == 1


def test_filter_omitted_returns_all() -> None:
    t1 = _create_todo("a")
    t2 = _create_todo("b")
    _create_todo("c")
    _mark_done(t1["id"])
    _mark_done(t2["id"])
    response = client.get("/todos")
    data = response.json()
    assert len(data["items"]) == 3
    assert data["total"] == 3


def test_filter_preserves_order() -> None:
    t1 = _create_todo("a")
    t2 = _create_todo("b")
    _create_todo("c")
    _mark_done(t1["id"])
    _mark_done(t2["id"])
    response = client.get("/todos", params={"done": "true"})
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == sorted(ids, reverse=True)


def test_filter_interacts_with_pagination() -> None:
    todos = [_create_todo(f"item {i}") for i in range(5)]
    for t in todos[:3]:
        _mark_done(t["id"])
    response = client.get("/todos", params={"done": "true", "limit": 2})
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 3


def test_filter_invalid_value_returns_422() -> None:
    response = client.get("/todos", params={"done": "maybe"})
    assert response.status_code == 422
