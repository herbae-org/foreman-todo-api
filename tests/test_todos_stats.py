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


def test_stats_empty_store() -> None:
    response = client.get("/todos/stats")
    assert response.status_code == 200
    assert response.json() == {"total": 0, "done": 0, "pending": 0}


def test_stats_after_posts() -> None:
    for i in range(5):
        _create_todo(f"item {i}")
    data = client.get("/todos/stats").json()
    assert data == {"total": 5, "done": 0, "pending": 5}


def test_stats_after_mixed() -> None:
    todos = [_create_todo(f"item {i}") for i in range(5)]
    _mark_done(todos[0]["id"])
    _mark_done(todos[1]["id"])
    data = client.get("/todos/stats").json()
    assert data == {"total": 5, "done": 2, "pending": 3}


@pytest.mark.parametrize(
    "total,done_count",
    [(0, 0), (1, 0), (1, 1), (5, 2), (10, 10)],
)
def test_stats_invariant(total: int, done_count: int) -> None:
    todos = [_create_todo(f"item {i}") for i in range(total)]
    for t in todos[:done_count]:
        _mark_done(t["id"])
    data = client.get("/todos/stats").json()
    assert data["total"] == data["done"] + data["pending"]
    assert data["total"] == total
    assert data["done"] == done_count
    assert data["pending"] == total - done_count
