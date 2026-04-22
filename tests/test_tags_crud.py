import pytest
from fastapi.testclient import TestClient

from todo_api import db as db_module
from todo_api.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    db_module.init_schema(db_module.get_connection())


def _create_tag(name: str) -> dict:
    return client.post("/tags", json={"name": name}).json()


def _create_todo(title: str) -> dict:
    return client.post("/todos", json={"title": title}).json()


def test_create_tag_returns_201() -> None:
    response = client.post("/tags", json={"name": "work"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "work"
    assert "id" in data


def test_create_tag_duplicate_case_insensitive_returns_409() -> None:
    client.post("/tags", json={"name": "Work"})
    response = client.post("/tags", json={"name": "work"})
    assert response.status_code == 409
    assert response.json() == {"detail": "Tag already exists"}


def test_list_tags_returns_items_and_total() -> None:
    _create_tag("alpha")
    _create_tag("beta")
    response = client.get("/tags")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    names = [t["name"] for t in data["items"]]
    assert names == ["beta", "alpha"]


def test_list_tags_empty() -> None:
    response = client.get("/tags")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_delete_tag_returns_204() -> None:
    tag = _create_tag("delete-me")
    response = client.delete(f"/tags/{tag['id']}")
    assert response.status_code == 204


def test_delete_tag_missing_returns_404() -> None:
    response = client.delete("/tags/999")
    assert response.status_code == 404


def test_delete_tag_cascades_todo_tags() -> None:
    todo = _create_todo("tagged")
    tag = _create_tag("temp")
    client.post(f"/todos/{todo['id']}/tags", json={"tag_ids": [tag["id"]]})
    response = client.get(f"/todos/{todo['id']}")
    assert len(response.json()["tags"]) == 1

    client.delete(f"/tags/{tag['id']}")
    response = client.get(f"/todos/{todo['id']}")
    assert response.json()["tags"] == []
