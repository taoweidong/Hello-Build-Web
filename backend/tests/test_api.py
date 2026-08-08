from fastapi.testclient import TestClient


def _login(client: TestClient, username="pm27a", password="123456"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    return r.json()["data"]["token"]


def test_login_and_me(client):
    token = _login(client, "admin")
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["data"]["role"] == "admin"


def test_pm_cannot_edit_other_version(client):
    token = _login(client, "pm27a")  # 27A PM
    # 尝试编辑 27B 分支策略（branch_id=3 为 27B-master）
    r = client.get("/api/strategies", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    r2 = client.post("/api/strategies", json={
        "branch_id": 3, "template_id": 1, "name": "越权", "build_start_time": "10:00",
        "push_mode": "normal", "enabled": True
    }, headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 403


def test_conclusion_duplicate_rejected(client):
    token = _login(client, "tester")
    # 取一个 pending 轮次
    r = client.get("/api/executions", headers={"Authorization": f"Bearer {token}"})
    rounds = r.json()["data"]
    pending = next((x for x in rounds if x["conclusion"] == "pending"), None)
    assert pending is not None, "种子数据中应存在 pending 轮次"
    h = {"Authorization": f"Bearer {token}"}
    r1 = client.post(f"/api/executions/rounds/{pending['id']}/conclusion",
                     json={"conclusion": "pass", "note": "ok"}, headers=h)
    assert r1.status_code == 200
    r2 = client.post(f"/api/executions/rounds/{pending['id']}/conclusion",
                     json={"conclusion": "pass", "note": "again"}, headers=h)
    assert r2.status_code == 409