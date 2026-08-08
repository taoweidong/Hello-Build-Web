# pytest 全局配置：使用独立临时数据库，避免污染真实开发库
import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 在导入业务模块前，将 database 模块切换到独立测试库
import app.database as db

_tmp = tempfile.mkdtemp(prefix="build_strategy_test_")
_TEST_DB = os.path.join(_tmp, "test.db")
db.engine = create_engine(f"sqlite:///{_TEST_DB}", connect_args={"check_same_thread": False})
db.SessionLocal = sessionmaker(bind=db.engine, autoflush=False, autocommit=False)


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    """建表并写入种子数据（每个测试会话一次）。"""
    from app import models  # noqa: F401  触发模型注册
    db.Base.metadata.create_all(bind=db.engine)
    from app.seed.seed import seed
    seed()
    yield


@pytest.fixture(scope="session")
def client(_setup_db):
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)