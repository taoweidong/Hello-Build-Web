from fastapi.testclient import TestClient


def get_token_headers(client: TestClient, username: str, password: str = "123456") -> dict[str, str]:
    """登录并返回 Authorization 请求头"""
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败: {username} -> {r.text}"
    token = r.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}
