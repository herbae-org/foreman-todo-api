from fastapi.testclient import TestClient

from todo_api.app import app

client = TestClient(app)


def _create_todo(title: str, headers: dict) -> dict:
    return client.post("/todos", json={"title": title}, headers=headers).json()


def _mark_done(todo_id: int, headers: dict) -> None:
    client.patch(f"/todos/{todo_id}", json={"done": True}, headers=headers)


def test_filter_done_true(auth_headers) -> None:
    t1 = _create_todo("a", auth_headers)
    t2 = _create_todo("b", auth_headers)
    _create_todo("c", auth_headers)
    _mark_done(t1["id"], auth_headers)
    _mark_done(t2["id"], auth_headers)
    response = client.get("/todos", params={"done": "true"}, headers=auth_headers)
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 2


def test_filter_done_false(auth_headers) -> None:
    t1 = _create_todo("a", auth_headers)
    t2 = _create_todo("b", auth_headers)
    _create_todo("c", auth_headers)
    _mark_done(t1["id"], auth_headers)
    _mark_done(t2["id"], auth_headers)
    response = client.get("/todos", params={"done": "false"}, headers=auth_headers)
    data = response.json()
    assert len(data["items"]) == 1
    assert data["total"] == 1


def test_filter_omitted_returns_all(auth_headers) -> None:
    t1 = _create_todo("a", auth_headers)
    t2 = _create_todo("b", auth_headers)
    _create_todo("c", auth_headers)
    _mark_done(t1["id"], auth_headers)
    _mark_done(t2["id"], auth_headers)
    response = client.get("/todos", headers=auth_headers)
    data = response.json()
    assert len(data["items"]) == 3
    assert data["total"] == 3


def test_filter_preserves_order(auth_headers) -> None:
    t1 = _create_todo("a", auth_headers)
    t2 = _create_todo("b", auth_headers)
    _create_todo("c", auth_headers)
    _mark_done(t1["id"], auth_headers)
    _mark_done(t2["id"], auth_headers)
    response = client.get("/todos", params={"done": "true"}, headers=auth_headers)
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == sorted(ids, reverse=True)


def test_filter_interacts_with_pagination(auth_headers) -> None:
    todos = [_create_todo(f"item {i}", auth_headers) for i in range(5)]
    for t in todos[:3]:
        _mark_done(t["id"], auth_headers)
    response = client.get(
        "/todos", params={"done": "true", "limit": 2}, headers=auth_headers
    )
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 3


def test_filter_invalid_value_returns_422(auth_headers) -> None:
    response = client.get("/todos", params={"done": "maybe"}, headers=auth_headers)
    assert response.status_code == 422
