from fastapi.testclient import TestClient

from backend.api.app.main import app


def test_health_endpoint_is_container_safe():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    assert "/Users/" not in response.text
