from fastapi.testclient import TestClient

from app.main import app


def test_dashboard_ok():
    with TestClient(app) as client:
        r = client.get("/")
    assert r.status_code == 200
    assert b"Applications" in r.content
