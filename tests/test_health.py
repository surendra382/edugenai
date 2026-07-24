from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.main import app


def test_health_endpoint_returns_ok():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_creates_sqlite_db():
    db_path = Path(settings.database_url.removeprefix("sqlite:///"))

    with TestClient(app):
        pass

    assert db_path.exists()
