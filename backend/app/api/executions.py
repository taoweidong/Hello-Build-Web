from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from ..database import get_db
from ..security import get_current_user
from ..errors import ok, raise_forbidden, raise_duplicate
from ..models.strategy import Strategy, StrategyTemplate
from ..models.branch import Branch
from ..models.version import Version
from ..models.execution import ExecutionRound
from ..models.audit import ExecutionLog
from ..models.user import User
from ..adapters import push_adapter, notify_adapter

router = APIRouter()

class ConclusionReq(BaseModel):
    conclusion: str  # pass/fail
    note: str = ""

def _round_to_dict(r):
    return {"id": r.id, "strategy_id": r.strategy_id, "exec_date": r.exec_date,
            "strategy_name": r.strategy.name if r.strategy else None,
            "push_mode": r.strategy.push_mode if r.strategy else None,
            "push_start": r.push_start.isoformat() if r.push_start else None,
            "push_end": r.push_end.isoformat() if r.push_end else None,
            "build_start": r.build_start.isoformat(), "build_end": r.build_end.isoformat(),
            "smoke_start": r.smoke_start.isoformat(), "smoke_end": r.smoke_end.isoformat(),
            "analysis_start": r.analysis_start.isoformat(), "analysis_end": r.analysis_end.isoformat(),
            "conclusion": r.conclusion, "conclusion_note": r.conclusion_note,
            "push_status": r.push_status, "release_approved": r.release_approved}

@router.get("")
def list_executions(date: str = None, strategy_id: int = None, from_: str = Query(None, alias="from"),
                    to: str = Query(None), user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    q = db.query(ExecutionRound).options(joinedload(ExecutionRound.strategy)).order_by(ExecutionRound.exec_date.desc())
    if date:
        q = q.filter(ExecutionRound.exec_date == date)
    if strategy_id:
        q = q.filter(ExecutionRound.strategy_id == strategy_id)
    if from_:
        q = q.filter(ExecutionRound.exec_date >= from_)
    if to:
        q = q.filter(ExecutionRound.exec_date <= to)
    # PM 仅本版本
    if user.role == "pm":
        version = db.query(Version).filter(Version.pm_user_id == user.id).first()
        if version:
            q = q.join(Strategy).join(Branch).filter(Branch.version_id == version.id)
        else:
            return ok([])
    return ok([_round_to_dict(r) for r in q.limit(200).all()])

@router.get("/rounds/{round_id}")
def round_detail(round_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.get(ExecutionRound, round_id)
    if not r:
        return ok(None)
    logs = db.query(ExecutionLog).filter(ExecutionLog.round_id == round_id).order_by(ExecutionLog.at).all()
    return ok({"round": _round_to_dict(r), "logs": [{"stage": l.stage, "event": l.event,
                                                      "detail": l.detail, "at": l.at.isoformat()} for l in logs]})

@router.post("/rounds/{round_id}/conclusion")
def submit_conclusion(round_id: int, req: ConclusionReq, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    if user.role != "tester":
        raise_forbidden("仅防护网测试人员可录入结论")
    r = db.get(ExecutionRound, round_id)
    if not r:
        return ok({"id": round_id})
    if r.conclusion != "pending":
        raise_duplicate()
    r.conclusion = req.conclusion
    r.conclusion_by = user.id
    r.conclusion_note = req.note
    from datetime import datetime
    r.conclusion_at = datetime.utcnow()
    db.add(ExecutionLog(round_id=r.id, stage="conclusion", event="conclusion_submit",
                        detail=f"{req.conclusion} note={req.note}"))
    strategy = db.get(Strategy, r.strategy_id)
    if strategy.push_mode == "normal" and req.conclusion == "pass":
        # 正常模式：结论通过 → 自动推送（mock 留痕），推送占用结论后 20min
        ok_push = push_adapter.push(r.id, "normal")
        r.push_status = "success" if ok_push else "failed"
        from datetime import timedelta
        r.push_start = r.conclusion_at
        r.push_end = r.conclusion_at + timedelta(minutes=20)
        db.add(ExecutionLog(round_id=r.id, stage="push", event="push_trigger",
                            detail=f"normal mode result={'success' if ok_push else 'failed'}"))
    elif strategy.push_mode == "sync":
        # 同步模式：结论仅评估是否正式发布
        r.release_approved = (req.conclusion == "pass")
        db.add(ExecutionLog(round_id=r.id, stage="release", event="release_eval",
                            detail=f"sync mode release_approved={r.release_approved}"))
    db.commit()
    return ok(_round_to_dict(r))