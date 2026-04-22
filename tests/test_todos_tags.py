from fastapi.testclient import TestClient

from todo_api.app import app

client = TestClient(app)


def _create_todo(title: str, headers: dict) -> dict:
    return client.post("/todos", json={"title": title}, headers=headers).json()


def _create_tag(name: str, headers: dict) -> dict:
    return client.post("/tags", json={"name": name}, headers=headers).json()


def test_assign_tags_returns_todo_with_tags(auth_headers) -> None:
    todo = _create_todo("task", auth_headers)
    t1 = _create_tag("work", auth_headers)
    t2 = _create_tag("urgent", auth_headers)
    response = client.post(
        f"/todos/{todo['id']}/tags",
        json={"tag_ids": [t1["id"], t2["id"]]},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    tag_names = sorted(t["name"] for t in data["tags"])
    assert tag_names == ["urgent", "work"]


def test_assign_tags_idempotent(auth_headers) -> None:
    todo = _create_todo("task", auth_headers)
    tag = _create_tag("work", auth_headers)
    client.post(
        f"/todos/{todo['id']}/tags",
        json={"tag_ids": [tag["id"]]},
        headers=auth_headers,
    )
    response = client.post(
        f"/todos/{todo['id']}/tags",
        json={"tag_ids": [tag["id"]]},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert len(response.json()["tags"]) == 1


def test_remove_tag_returns_204(auth_headers) -> None:
    todo = _create_todo("task", auth_headers)
    tag = _create_tag("work", auth_headers)
    client.post(
        f"/todos/{todo['id']}/tags",
        json={"tag_ids": [tag["id"]]},
        headers=auth_headers,
    )
    response = client.delete(
        f"/todos/{todo['id']}/tags/{tag['id']}", headers=auth_headers
    )
    assert response.status_code == 204
    get_resp = client.get(f"/todos/{todo['id']}", headers=auth_headers)
    assert get_resp.json()["tags"] == []


def test_remove_tag_nonexistent_link_returns_404(auth_headers) -> None:
    todo = _create_todo("task", auth_headers)
    _create_tag("work", auth_headers)
    response = client.delete(f"/todos/{todo['id']}/tags/999", headers=auth_headers)
    assert response.status_code == 404


def test_assign_unknown_tag_returns_400(auth_headers) -> None:
    todo = _create_todo("task", auth_headers)
    response = client.post(
        f"/todos/{todo['id']}/tags",
        json={"tag_ids": [999]},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Unknown tag_id: 999"}


def test_assign_tags_unknown_todo_returns_404(auth_headers) -> None:
    tag = _create_tag("work", auth_headers)
    response = client.post(
        "/todos/999/tags",
        json={"tag_ids": [tag["id"]]},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_delete_todo_cascades_todo_tags(auth_headers) -> None:
    todo = _create_todo("doomed", auth_headers)
    tag = _create_tag("temp", auth_headers)
    client.post(
        f"/todos/{todo['id']}/tags",
        json={"tag_ids": [tag["id"]]},
        headers=auth_headers,
    )
    client.delete(f"/todos/{todo['id']}", headers=auth_headers)
    get_resp = client.get(f"/todos/{todo['id']}", headers=auth_headers)
    assert get_resp.status_code == 404


def test_new_todo_has_empty_tags(auth_headers) -> None:
    response = client.post(
        "/todos", json={"title": "fresh"}, headers=auth_headers
    )
    assert response.status_code == 201
    assert response.json()["tags"] == []
