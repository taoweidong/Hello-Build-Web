import os
import tempfile
from collections.abc import Generator

# 在导入业务模块前切换到独立临时数据库，避免污染真实开发库
_tmp = tempfile.mkdtemp(prefix="build_strategy_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'test.db')}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from app.core.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session]:
    """建表并写入种子数据（每个测试会话一次）。"""
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        init_db(session)
        yield session


@pytest.fixture(scope="module")
def client() -> Generator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token_headers(client: TestClient) -> dict[str, str]:
    from tests.utils.utils import get_token_headers

    return get_token_headers(client=client, username="admin")


@pytest.fixture(scope="module")
def pm_token_headers(client: TestClient) -> dict[str, str]:
    from tests.utils.utils import get_token_headers

    return get_token_headers(client=client, username="pm27a")


@pytest.fixture(scope="module")
def tester_token_headers(client: TestClient) -> dict[str, str]:
    from tests.utils.utils import get_token_headers

    return get_token_headers(client=client, username="tester")
