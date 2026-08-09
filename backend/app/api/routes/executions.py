from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from sqlmodel import select

from app.adapters import push_adapter
from app.api.deps import CurrentUser, SessionDep
from app.core.response import ok, raise_duplicate, raise_forbidden
from app.crud import get_pm_bound_version
from app.models import ConclusionCreate, ExecutionLog, ExecutionRound, Strategy

router = APIRouter(prefix="/executions", tags=["executions"])


def _round_to_dict(r: ExecutionRound) -> dict:
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
def list_executions(session: SessionDep, current_user: CurrentUser,
                    date: str | None = None, strategy_id: int | None = None,
                    from_: str | None = Query(None, alias="from"), to: str | None = Query(None)):
    rounds = session.exec(
        select(ExecutionRound).order_by(ExecutionRound.exec_date.desc())
    ).all()
    if date:
        rounds = [r for r in rounds if r.exec_date == date]
    if strategy_id:
        rounds = [r for r in rounds if r.strategy_id == strategy_id]
    if from_:
        rounds = [r for r in rounds if r.exec_date >= from_]
    if to:
        rounds = [r for r in rounds if r.exec_date <= to]
    # PM 仅本版本
    if current_user.role == "pm":
        version = get_pm_bound_version(session=session, user_id=current_user.id)
        if version:
            rounds = [r for r in rounds
                      if r.strategy and r.strategy.branch
                      and r.strategy.branch.version_id == version.id]
        else:
            return ok([])
    return ok([_round_to_dict(r) for r in rounds[:200]])


@router.get("/rounds/{round_id}")
def round_detail(round_id: int, session: SessionDep, current_user: CurrentUser):
    r = session.get(ExecutionRound, round_id)
    if not r:
        return ok(None)
    logs = session.exec(
        select(ExecutionLog)
        .where(ExecutionLog.round_id == round_id)
        .order_by(ExecutionLog.at)
    ).all()
    return ok({"round": _round_to_dict(r),
               "logs": [{"stage": log.stage, "event": log.event,
                         "detail": log.detail, "at": log.at.isoformat()} for log in logs]})


@router.post("/rounds/{round_id}/conclusion")
def submit_conclusion(round_id: int, req: ConclusionCreate, session: SessionDep,
                      current_user: CurrentUser):
    if current_user.role != "tester":
        raise_forbidden("仅防护网测试人员可录入结论")
    r = session.get(ExecutionRound, round_id)
    if not r:
        return ok({"id": round_id})
    if r.conclusion != "pending":
        raise_duplicate()
    r.conclusion = req.conclusion
    r.conclusion_by = current_user.id
    r.conclusion_note = req.note
    r.conclusion_at = datetime.now(UTC).replace(tzinfo=None)
    session.add(ExecutionLog(round_id=r.id, stage="conclusion", event="conclusion_submit",
                             detail=f"{req.conclusion} note={req.note}"))
    strategy = session.get(Strategy, r.strategy_id)
    if strategy and strategy.push_mode == "normal" and req.conclusion == "pass":
        # 正常模式：结论通过 → 自动推送（mock 留痕），推送占用结论后 20min
        ok_push = push_adapter.push(r.id, "normal")
        r.push_status = "success" if ok_push else "failed"
        r.push_start = r.conclusion_at
        r.push_end = r.conclusion_at + timedelta(minutes=20)
        session.add(ExecutionLog(round_id=r.id, stage="push", event="push_trigger",
                                 detail=f"normal mode result={'success' if ok_push else 'failed'}"))
    elif strategy and strategy.push_mode == "sync":
        # 同步模式：结论仅评估是否正式发布
        r.release_approved = (req.conclusion == "pass")
        session.add(ExecutionLog(round_id=r.id, stage="release", event="release_eval",
                                 detail=f"sync mode release_approved={r.release_approved}"))
    session.commit()
    return ok(_round_to_dict(r))
