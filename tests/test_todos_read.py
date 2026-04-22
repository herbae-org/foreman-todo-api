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


def test_list_empty_returns_zero_total() -> None:
    response = client.get("/todos")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_list_returns_total_regardless_of_pagination() -> None:
    for i in range(5):
        _create_todo(f"todo {i}")
    response = client.get("/todos", params={"limit": 2})
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5


def test_list_orders_by_id_desc() -> None:
    _create_todo("a")
    _create_todo("b")
    _create_todo("c")
    response = client.get("/todos")
    titles = [item["title"] for item in response.json()["items"]]
    assert titles == ["c", "b", "a"]


def test_list_default_limit_is_20() -> None:
    for i in range(25):
        _create_todo(f"todo {i}")
    response = client.get("/todos")
    data = response.json()
    assert len(data["items"]) == 20
    assert data["total"] == 25


def test_list_offset_skips_items() -> None:
    for i in range(5):
        _create_todo(f"todo {i}")
    response = client.get("/todos", params={"offset": 2, "limit": 10})
    data = response.json()
    assert len(data["items"]) == 3
    ids = [item["id"] for item in data["items"]]
    assert ids == [3, 2, 1]


def test_list_rejects_limit_zero() -> None:
    response = client.get("/todos", params={"limit": 0})
    assert response.status_code == 422


def test_list_rejects_limit_over_100() -> None:
    response = client.get("/todos", params={"limit": 101})
    assert response.status_code == 422


def test_list_rejects_negative_offset() -> None:
    response = client.get("/todos", params={"offset": -1})
    assert response.status_code == 422


def test_get_by_id_returns_item() -> None:
    _create_todo("buy milk")
    response = client.get("/todos/1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["title"] == "buy milk"
    assert data["done"] is False


def test_get_by_id_returns_404_when_missing() -> None:
    response = client.get("/todos/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_get_by_id_returns_422_on_non_integer() -> None:
    response = client.get("/todos/abc")
    assert response.status_code == 422
