from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..security import get_current_user
from ..errors import ok
from ..models.audit import ExecutionLog, StrategyChangeLog
from ..models.user import User

router = APIRouter()

@router.get("/execution")
def execution_logs(date: str = None, version_id: int = None, branch_id: int = None,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(ExecutionLog).order_by(ExecutionLog.at.desc())
    # 简易过滤：按 round 关联 strategy/branch/version
    items = [{"id": l.id, "round_id": l.round_id, "stage": l.stage, "event": l.event,
              "detail": l.detail, "at": l.at.isoformat()} for l in q.limit(200).all()]
    return ok(items)

@router.get("/changes")
def change_logs(from_: str = Query(None, alias="from"), to: str = Query(None),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(StrategyChangeLog).order_by(StrategyChangeLog.at.desc())
    items = [{"id": c.id, "strategy_id": c.strategy_id, "operator": c.operator,
              "field": c.field, "old_value": c.old_value, "new_value": c.new_value,
              "at": c.at.isoformat()} for c in q.limit(200).all()]
    return ok(items)