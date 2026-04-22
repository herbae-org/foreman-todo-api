from datetime import datetime

from fastapi.testclient import TestClient

from todo_api.app import app

client = TestClient(app)


def test_create_todo_returns_201_with_payload(auth_headers) -> None:
    response = client.post("/todos", json={"title": "buy milk"}, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 1
    assert data["title"] == "buy milk"
    assert data["done"] is False
    datetime.fromisoformat(data["created_at"])


def test_create_todo_assigns_incrementing_ids(auth_headers) -> None:
    r1 = client.post("/todos", json={"title": "first"}, headers=auth_headers)
    r2 = client.post("/todos", json={"title": "second"}, headers=auth_headers)
    assert r1.json()["id"] == 1
    assert r2.json()["id"] == 2


def test_create_todo_rejects_missing_title(auth_headers) -> None:
    response = client.post("/todos", json={}, headers=auth_headers)
    assert response.status_code == 422


def test_create_todo_rejects_empty_title(auth_headers) -> None:
    response = client.post("/todos", json={"title": ""}, headers=auth_headers)
    assert response.status_code == 422


def test_create_todo_rejects_overlong_title(auth_headers) -> None:
    response = client.post("/todos", json={"title": "x" * 201}, headers=auth_headers)
    assert response.status_code == 422
