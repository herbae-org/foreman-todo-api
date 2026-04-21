from fastapi.testclient import TestClient

from todo_api.app import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_route_returns_404() -> None:
    response = client.get("/nonexistent")
    assert response.status_code == 404
