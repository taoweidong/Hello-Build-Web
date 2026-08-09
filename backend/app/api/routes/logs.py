from fastapi import APIRouter, Query
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.core.response import ok
from app.models import ExecutionLog, Strategy, StrategyChangeLog, User

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/execution")
def execution_logs(session: SessionDep, current_user: CurrentUser,
                   date: str | None = None, version_id: int | None = None,
                   branch_id: int | None = None):
    logs = session.exec(
        select(ExecutionLog).order_by(ExecutionLog.at.desc()).limit(200)
    ).all()
    # 简易过滤：按 round 关联 strategy/branch/version
    items = [{"id": log.id, "round_id": log.round_id, "stage": log.stage,
              "event": log.event, "detail": log.detail, "at": log.at.isoformat()}
             for log in logs]
    return ok(items)


@router.get("/changes")
def change_logs(session: SessionDep, current_user: CurrentUser,
                from_: str | None = Query(None, alias="from"), to: str | None = Query(None)):
    changes = session.exec(
        select(StrategyChangeLog).order_by(StrategyChangeLog.at.desc()).limit(200)
    ).all()
    items = []
    for c in changes:
        strategy = session.get(Strategy, c.strategy_id)
        operator = session.get(User, c.operator)
        items.append({"id": c.id, "strategy_id": c.strategy_id,
                      "strategy_name": strategy.name if strategy else None,
                      "operator": operator.display_name if operator else str(c.operator),
                      "field": c.field, "old_value": c.old_value, "new_value": c.new_value,
                      "at": c.at.isoformat()})
    return ok(items)
