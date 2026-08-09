from fastapi import APIRouter

from app.api.routes import admin, executions, login, logs, plan, strategies

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(plan.router)
api_router.include_router(strategies.router)
api_router.include_router(executions.router)
api_router.include_router(admin.router)
api_router.include_router(logs.router)
