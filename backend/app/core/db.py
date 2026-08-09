from sqlmodel import Session, create_engine

from app import crud
from app.core.config import settings

# SQLite 需要 check_same_thread=False 以支持多线程访问
_connect_args = (
    {"check_same_thread": False}
    if settings.SQLALCHEMY_DATABASE_URI.startswith("sqlite")
    else {}
)
engine = create_engine(
    str(settings.SQLALCHEMY_DATABASE_URI), connect_args=_connect_args
)


# 确保在初始化数据库前所有 SQLModel 模型已被导入（app.models）
# 否则 SQLModel 可能无法正确初始化关系
# 详情参见：https://github.com/fastapi/full-stack-fastapi-template/issues/28


def init_db(session: Session) -> None:
    # 表结构应通过 Alembic 迁移创建（scripts/prestart 执行 alembic upgrade head）
    # 如果不想使用迁移，可以取消下面一行的注释直接建表
    # from sqlmodel import SQLModel
    # SQLModel.metadata.create_all(engine)

    # 首位管理员（FIRST_SUPERUSER）与业务演示种子数据（幂等）：
    # 用户表为空时写入全部主数据，否则仅补全审计日志
    crud.seed_demo_data(session=session)
