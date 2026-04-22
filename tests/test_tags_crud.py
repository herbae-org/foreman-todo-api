from fastapi.testclient import TestClient

from todo_api.app import app

client = TestClient(app)


def _create_tag(name: str, headers: dict) -> dict:
    return client.post("/tags", json={"name": name}, headers=headers).json()


def _create_todo(title: str, headers: dict) -> dict:
    return client.post("/todos", json={"title": title}, headers=headers).json()


def test_create_tag_returns_201(auth_headers) -> None:
    response = client.post("/tags", json={"name": "work"}, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "work"
    assert "id" in data


def test_create_tag_duplicate_case_insensitive_returns_409(auth_headers) -> None:
    client.post("/tags", json={"name": "Work"}, headers=auth_headers)
    response = client.post("/tags", json={"name": "work"}, headers=auth_headers)
    assert response.status_code == 409
    assert response.json() == {"detail": "Tag already exists"}


def test_list_tags_returns_items_and_total(auth_headers) -> None:
    _create_tag("alpha", auth_headers)
    _create_tag("beta", auth_headers)
    response = client.get("/tags", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    names = [t["name"] for t in data["items"]]
    assert names == ["beta", "alpha"]


def test_list_tags_empty(auth_headers) -> None:
    response = client.get("/tags", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_delete_tag_returns_204(auth_headers) -> None:
    tag = _create_tag("delete-me", auth_headers)
    response = client.delete(f"/tags/{tag['id']}", headers=auth_headers)
    assert response.status_code == 204


def test_delete_tag_missing_returns_404(auth_headers) -> None:
    response = client.delete("/tags/999", headers=auth_headers)
    assert response.status_code == 404


def test_delete_tag_cascades_todo_tags(auth_headers) -> None:
    todo = _create_todo("tagged", auth_headers)
    tag = _create_tag("temp", auth_headers)
    client.post(
        f"/todos/{todo['id']}/tags",
        json={"tag_ids": [tag["id"]]},
        headers=auth_headers,
    )
    response = client.get(f"/todos/{todo['id']}", headers=auth_headers)
    assert len(response.json()["tags"]) == 1

    client.delete(f"/tags/{tag['id']}", headers=auth_headers)
    response = client.get(f"/todos/{todo['id']}", headers=auth_headers)
    assert response.json()["tags"] == []
