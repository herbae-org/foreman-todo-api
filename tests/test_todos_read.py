from fastapi.testclient import TestClient

from todo_api.app import app

client = TestClient(app)


def _create_todo(title: str, headers: dict) -> dict:
    return client.post("/todos", json={"title": title}, headers=headers).json()


def test_list_empty_returns_zero_total(auth_headers) -> None:
    response = client.get("/todos", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_list_returns_total_regardless_of_pagination(auth_headers) -> None:
    for i in range(5):
        _create_todo(f"todo {i}", auth_headers)
    response = client.get("/todos", params={"limit": 2}, headers=auth_headers)
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5


def test_list_orders_by_id_desc(auth_headers) -> None:
    _create_todo("a", auth_headers)
    _create_todo("b", auth_headers)
    _create_todo("c", auth_headers)
    response = client.get("/todos", headers=auth_headers)
    titles = [item["title"] for item in response.json()["items"]]
    assert titles == ["c", "b", "a"]


def test_list_default_limit_is_20(auth_headers) -> None:
    for i in range(25):
        _create_todo(f"todo {i}", auth_headers)
    response = client.get("/todos", headers=auth_headers)
    data = response.json()
    assert len(data["items"]) == 20
    assert data["total"] == 25


def test_list_offset_skips_items(auth_headers) -> None:
    for i in range(5):
        _create_todo(f"todo {i}", auth_headers)
    response = client.get("/todos", params={"offset": 2, "limit": 10}, headers=auth_headers)
    data = response.json()
    assert len(data["items"]) == 3
    ids = [item["id"] for item in data["items"]]
    assert ids == [3, 2, 1]


def test_list_rejects_limit_zero(auth_headers) -> None:
    response = client.get("/todos", params={"limit": 0}, headers=auth_headers)
    assert response.status_code == 422


def test_list_rejects_limit_over_100(auth_headers) -> None:
    response = client.get("/todos", params={"limit": 101}, headers=auth_headers)
    assert response.status_code == 422


def test_list_rejects_negative_offset(auth_headers) -> None:
    response = client.get("/todos", params={"offset": -1}, headers=auth_headers)
    assert response.status_code == 422


def test_get_by_id_returns_item(auth_headers) -> None:
    _create_todo("buy milk", auth_headers)
    response = client.get("/todos/1", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["title"] == "buy milk"
    assert data["done"] is False


def test_get_by_id_returns_404_when_missing(auth_headers) -> None:
    response = client.get("/todos/999", headers=auth_headers)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_get_by_id_returns_422_on_non_integer(auth_headers) -> None:
    response = client.get("/todos/abc", headers=auth_headers)
    assert response.status_code == 422
