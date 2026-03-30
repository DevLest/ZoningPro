from fastapi.testclient import TestClient

from app.main import app


def _login(client: TestClient) -> None:
    r = client.post(
        "/login",
        data={"username": "admin", "password": "admin", "next": "/"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_dashboard_requires_login():
    with TestClient(app, follow_redirects=False) as client:
        r = client.get("/")
    assert r.status_code == 303
    assert "login" in (r.headers.get("location") or "")


def test_dashboard_ok_after_login():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    assert r.status_code == 200
    assert b"Project Overview" in r.content


def test_users_panel_admin():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/users")
    assert r.status_code == 200
    assert b"Users" in r.content
    assert b"admin" in r.content


def test_permissions_page_admin():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/permissions")
    assert r.status_code == 200
    assert b"Role permissions" in r.content


def test_locational_clearance_list_admin():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/locational-clearance/")
    assert r.status_code == 200
    assert b"Locational clearance" in r.content
