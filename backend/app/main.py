import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute
from sqlalchemy import inspect
from sqlmodel import Session, SQLModel
from starlette.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  确保所有 SQLModel 模型在初始化前已注册
from app.api.main import api_router
from app.core.config import settings
from app.core.db import engine, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # 开发兜底：未执行过 Alembic 迁移时（无 alembic_version 表）直接建表并写入初始数据。
    # 生产流程请使用 scripts/prestart（alembic upgrade head + initial_data）。
    if not inspect(engine).has_table("alembic_version"):
        logger.info("未检测到 alembic_version，使用 create_all + init_db 兜底初始化")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            init_db(session)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

# 放行前端跨域来源
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)
