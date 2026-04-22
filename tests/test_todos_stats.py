import pytest
from fastapi.testclient import TestClient

from todo_api.app import app

client = TestClient(app)


def _create_todo(title: str, headers: dict) -> dict:
    return client.post("/todos", json={"title": title}, headers=headers).json()


def _mark_done(todo_id: int, headers: dict) -> None:
    client.patch(f"/todos/{todo_id}", json={"done": True}, headers=headers)


def test_stats_empty_store(auth_headers) -> None:
    response = client.get("/todos/stats", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"total": 0, "done": 0, "pending": 0}


def test_stats_after_posts(auth_headers) -> None:
    for i in range(5):
        _create_todo(f"item {i}", auth_headers)
    data = client.get("/todos/stats", headers=auth_headers).json()
    assert data == {"total": 5, "done": 0, "pending": 5}


def test_stats_after_mixed(auth_headers) -> None:
    todos = [_create_todo(f"item {i}", auth_headers) for i in range(5)]
    _mark_done(todos[0]["id"], auth_headers)
    _mark_done(todos[1]["id"], auth_headers)
    data = client.get("/todos/stats", headers=auth_headers).json()
    assert data == {"total": 5, "done": 2, "pending": 3}


@pytest.mark.parametrize(
    "total,done_count",
    [(0, 0), (1, 0), (1, 1), (5, 2), (10, 10)],
)
def test_stats_invariant(total: int, done_count: int, auth_headers) -> None:
    todos = [_create_todo(f"item {i}", auth_headers) for i in range(total)]
    for t in todos[:done_count]:
        _mark_done(t["id"], auth_headers)
    data = client.get("/todos/stats", headers=auth_headers).json()
    assert data["total"] == data["done"] + data["pending"]
    assert data["total"] == total
    assert data["done"] == done_count
    assert data["pending"] == total - done_count
