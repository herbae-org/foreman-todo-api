from fastapi.testclient import TestClient

from todo_api.app import app

client = TestClient(app)


def _create_todo(title: str, headers: dict) -> dict:
    return client.post("/todos", json={"title": title}, headers=headers).json()


def _create_tag(name: str, headers: dict) -> dict:
    return client.post("/tags", json={"name": name}, headers=headers).json()


def _mark_done(todo_id: int, headers: dict) -> None:
    client.patch(f"/todos/{todo_id}", json={"done": True}, headers=headers)


def test_filter_by_single_tag(auth_headers) -> None:
    t1 = _create_todo("tagged", auth_headers)
    _create_todo("untagged", auth_headers)
    tag = _create_tag("work", auth_headers)
    client.post(
        f"/todos/{t1['id']}/tags",
        json={"tag_ids": [tag["id"]]},
        headers=auth_headers,
    )
    response = client.get(
        "/todos", params={"tag_ids": [tag["id"]]}, headers=auth_headers
    )
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == t1["id"]


def test_filter_by_multiple_tags_or_semantics(auth_headers) -> None:
    t1 = _create_todo("a", auth_headers)
    t2 = _create_todo("b", auth_headers)
    _create_todo("c", auth_headers)
    tag1 = _create_tag("work", auth_headers)
    tag2 = _create_tag("home", auth_headers)
    client.post(
        f"/todos/{t1['id']}/tags",
        json={"tag_ids": [tag1["id"]]},
        headers=auth_headers,
    )
    client.post(
        f"/todos/{t2['id']}/tags",
        json={"tag_ids": [tag2["id"]]},
        headers=auth_headers,
    )
    response = client.get(
        "/todos",
        params={"tag_ids": [tag1["id"], tag2["id"]]},
        headers=auth_headers,
    )
    data = response.json()
    assert data["total"] == 2
    ids = {item["id"] for item in data["items"]}
    assert ids == {t1["id"], t2["id"]}


def test_filter_tag_combined_with_done(auth_headers) -> None:
    t1 = _create_todo("done-tagged", auth_headers)
    t2 = _create_todo("pending-tagged", auth_headers)
    tag = _create_tag("work", auth_headers)
    client.post(
        f"/todos/{t1['id']}/tags",
        json={"tag_ids": [tag["id"]]},
        headers=auth_headers,
    )
    client.post(
        f"/todos/{t2['id']}/tags",
        json={"tag_ids": [tag["id"]]},
        headers=auth_headers,
    )
    _mark_done(t1["id"], auth_headers)
    response = client.get(
        "/todos",
        params={"tag_ids": [tag["id"]], "done": "true"},
        headers=auth_headers,
    )
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == t1["id"]


def test_no_tag_filter_returns_all(auth_headers) -> None:
    _create_todo("a", auth_headers)
    _create_todo("b", auth_headers)
    response = client.get("/todos", headers=auth_headers)
    assert response.json()["total"] == 2


def test_filter_unknown_tag_returns_empty(auth_headers) -> None:
    _create_todo("a", auth_headers)
    response = client.get(
        "/todos", params={"tag_ids": [9999]}, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
