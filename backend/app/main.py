from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import Base, engine
from . import models  # 触发模型注册
from .api import auth, plan, strategies, executions, admin, logs

app = FastAPI(title="构建策略配置系统", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(plan.router, prefix="/api", tags=["plan"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["strategies"])
app.include_router(executions.router, prefix="/api/executions", tags=["executions"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])