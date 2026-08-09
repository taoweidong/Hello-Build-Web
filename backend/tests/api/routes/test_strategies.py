from fastapi.testclient import TestClient


def test_plan_aggregate_structure(client: TestClient, admin_token_headers):
    r = client.get("/api/plan", headers=admin_token_headers)
    assert r.status_code == 200
    versions = r.json()["data"]
    assert len(versions) == 3
    names = {v["version_name"] for v in versions}
    assert names == {"27A", "27B", "26B"}
    # 每个策略包含四阶段时间线
    first_strategy = versions[0]["branches"][0]["strategies"][0]
    assert set(first_strategy["timeline"].keys()) == {"push", "build", "smoke", "analysis"}


def test_list_strategies(client: TestClient, pm_token_headers):
    r = client.get("/api/strategies", headers=pm_token_headers)
    assert r.status_code == 200
    assert len(r.json()["data"]) == 4


def test_pm_cannot_edit_other_version(client: TestClient, pm_token_headers):
    # pm27a 尝试编辑 27B 分支策略（branch_id=3 为 27B-master）
    r = client.post("/api/strategies", json={
        "branch_id": 3, "template_id": 1, "name": "越权", "build_start_time": "10:00",
        "push_mode": "normal", "enabled": True
    }, headers=pm_token_headers)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == 40301


def test_preview_returns_timeline(client: TestClient, admin_token_headers):
    r = client.post("/api/strategies/preview", json={
        "branch_id": 3, "template_id": 2, "name": "预览", "build_start_time": "09:00",
        "push_mode": "normal", "enabled": True
    }, headers=admin_token_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["timeline"]["build"]["start"].endswith("09:00:00")
