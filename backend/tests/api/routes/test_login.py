from fastapi.testclient import TestClient


def test_login_success_and_me(client: TestClient, admin_token_headers):
    r = client.get("/api/auth/me", headers=admin_token_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["role"] == "admin"
    assert data["username"] == "admin"


def test_login_returns_pm_bound_version(client: TestClient, pm_token_headers):
    r = client.get("/api/auth/me", headers=pm_token_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["role"] == "pm"
    assert data["bound_version_name"] == "27A"


def test_login_wrong_password(client: TestClient):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == 40101


def test_login_empty_param(client: TestClient):
    r = client.post("/api/auth/login", json={"username": "", "password": ""})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == 42201


def test_me_requires_token(client: TestClient):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_logout(client: TestClient, admin_token_headers):
    r = client.post("/api/auth/logout", headers=admin_token_headers)
    assert r.status_code == 200
    assert r.json()["code"] == 0
