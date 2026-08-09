from fastapi.testclient import TestClient


def test_list_executions(client: TestClient, admin_token_headers):
    r = client.get("/api/executions", headers=admin_token_headers)
    assert r.status_code == 200
    rounds = r.json()["data"]
    assert len(rounds) == 28  # 4 策略 x 近 7 天


def test_pm_only_sees_own_version(client: TestClient, pm_token_headers):
    r = client.get("/api/executions", headers=pm_token_headers)
    assert r.status_code == 200
    rounds = r.json()["data"]
    assert len(rounds) == 14  # 27A 两个策略 x 7 天
    names = {x["strategy_name"] for x in rounds}
    assert names == {"27A-master晚间全量", "27A-TR5午间快速"}


def test_conclusion_duplicate_rejected(client: TestClient, tester_token_headers):
    # 取一个 pending 轮次，重复录入结论应返回 409
    r = client.get("/api/executions", headers=tester_token_headers)
    rounds = r.json()["data"]
    pending = next((x for x in rounds if x["conclusion"] == "pending"), None)
    assert pending is not None, "种子数据中应存在 pending 轮次"
    r1 = client.post(f"/api/executions/rounds/{pending['id']}/conclusion",
                     json={"conclusion": "pass", "note": "ok"}, headers=tester_token_headers)
    assert r1.status_code == 200
    r2 = client.post(f"/api/executions/rounds/{pending['id']}/conclusion",
                     json={"conclusion": "pass", "note": "again"}, headers=tester_token_headers)
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == 40902


def test_conclusion_requires_tester_role(client: TestClient, admin_token_headers):
    r = client.get("/api/executions", headers=admin_token_headers)
    pending = next((x for x in r.json()["data"] if x["conclusion"] == "pending"), None)
    assert pending is not None
    r2 = client.post(f"/api/executions/rounds/{pending['id']}/conclusion",
                     json={"conclusion": "pass", "note": "ok"}, headers=admin_token_headers)
    assert r2.status_code == 403
