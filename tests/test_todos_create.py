from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from todo_api import app as app_module
from todo_api.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_todos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_todos", [])


def test_create_todo_returns_201_with_payload() -> None:
    response = client.post("/todos", json={"title": "buy milk"})
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 1
    assert data["title"] == "buy milk"
    assert data["done"] is False
    datetime.fromisoformat(data["created_at"])


def test_create_todo_assigns_incrementing_ids() -> None:
    r1 = client.post("/todos", json={"title": "first"})
    r2 = client.post("/todos", json={"title": "second"})
    assert r1.json()["id"] == 1
    assert r2.json()["id"] == 2


def test_create_todo_rejects_missing_title() -> None:
    response = client.post("/todos", json={})
    assert response.status_code == 422


def test_create_todo_rejects_empty_title() -> None:
    response = client.post("/todos", json={"title": ""})
    assert response.status_code == 422


def test_create_todo_rejects_overlong_title() -> None:
    response = client.post("/todos", json={"title": "x" * 201})
    assert response.status_code == 422
