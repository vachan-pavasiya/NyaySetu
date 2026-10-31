"""Health endpoint unit test.

Role: Verifies FastAPI application startup, database connection, and config values.
"""

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_health_check_returns_200_and_expected_structure():
    """Verify that /health responds with 200 OK and connected database."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["s3_bucket"] == "indian-high-court-judgments"
    assert data["service_lag_days"] == 30
    assert "timestamp" in data
