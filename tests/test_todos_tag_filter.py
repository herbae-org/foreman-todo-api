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


def _create_tag(name: str) -> dict:
    return client.post("/tags", json={"name": name}).json()


def _mark_done(todo_id: int) -> None:
    client.patch(f"/todos/{todo_id}", json={"done": True})


def test_filter_by_single_tag() -> None:
    t1 = _create_todo("tagged")
    _create_todo("untagged")
    tag = _create_tag("work")
    client.post(f"/todos/{t1['id']}/tags", json={"tag_ids": [tag["id"]]})
    response = client.get("/todos", params={"tag_ids": [tag["id"]]})
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == t1["id"]


def test_filter_by_multiple_tags_or_semantics() -> None:
    t1 = _create_todo("a")
    t2 = _create_todo("b")
    _create_todo("c")
    tag1 = _create_tag("work")
    tag2 = _create_tag("home")
    client.post(f"/todos/{t1['id']}/tags", json={"tag_ids": [tag1["id"]]})
    client.post(f"/todos/{t2['id']}/tags", json={"tag_ids": [tag2["id"]]})
    response = client.get(
        "/todos", params={"tag_ids": [tag1["id"], tag2["id"]]}
    )
    data = response.json()
    assert data["total"] == 2
    ids = {item["id"] for item in data["items"]}
    assert ids == {t1["id"], t2["id"]}


def test_filter_tag_combined_with_done() -> None:
    t1 = _create_todo("done-tagged")
    t2 = _create_todo("pending-tagged")
    tag = _create_tag("work")
    client.post(f"/todos/{t1['id']}/tags", json={"tag_ids": [tag["id"]]})
    client.post(f"/todos/{t2['id']}/tags", json={"tag_ids": [tag["id"]]})
    _mark_done(t1["id"])
    response = client.get(
        "/todos", params={"tag_ids": [tag["id"]], "done": "true"}
    )
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == t1["id"]


def test_no_tag_filter_returns_all() -> None:
    _create_todo("a")
    _create_todo("b")
    response = client.get("/todos")
    assert response.json()["total"] == 2


def test_filter_unknown_tag_returns_empty() -> None:
    _create_todo("a")
    response = client.get("/todos", params={"tag_ids": [9999]})
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
