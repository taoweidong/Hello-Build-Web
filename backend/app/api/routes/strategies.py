from fastapi import APIRouter
from sqlmodel import Session, select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.core.response import ok, raise_conflict, raise_forbidden, raise_param
from app.models import Branch, Strategy, StrategyChangeLog, StrategyCreate, StrategyTemplate, User, Version
from app.services.conflict import detect_conflicts
from app.services.timeline import build_timeline

router = APIRouter(prefix="/strategies", tags=["strategies"])


def _check_pm_owns_version(session: Session, user: User, branch_id: int) -> None:
    """PM 只能操作所属版本的分支策略"""
    if user.role != "pm":
        return
    branch = session.get(Branch, branch_id)
    version = session.get(Version, branch.version_id) if branch else None
    if not version or version.pm_user_id != user.id:
        raise_forbidden("仅能配置本版本分支的策略")


def _preview_or_create(session: Session, user: User, req: StrategyCreate,
                       strategy_id: int | None = None):
    branch = session.get(Branch, req.branch_id)
    if not branch:
        raise_param("分支不存在")
    _check_pm_owns_version(session, user, req.branch_id)
    template = session.get(StrategyTemplate, req.template_id)
    if not template:
        raise_param("模板不存在")
    # 48h 冲突检测（同分支内）
    date = "2026-08-08"  # 用参考日期做相对排布检测
    existing = session.exec(
        select(Strategy).where(Strategy.branch_id == req.branch_id)
    ).all()
    if strategy_id:
        existing = [e for e in existing if e.id != strategy_id]
    candidates = [{"build_start_time": req.build_start_time, "template": template,
                   "push_mode": req.push_mode, "strategy_name": req.name}]
    ex_list = [{"build_start_time": e.build_start_time, "template": e.template,
                "push_mode": e.push_mode, "strategy_name": e.name} for e in existing]
    conflicts = detect_conflicts(date, candidates, ex_list, settings.build_minutes,
                                 settings.push_minutes, settings.sync_buffer_minutes)
    timeline = build_timeline(date, req.build_start_time, template.smoke_minutes,
                              template.analysis_minutes, settings.build_minutes,
                              settings.push_minutes, settings.sync_buffer_minutes, req.push_mode)
    return conflicts, timeline


@router.get("")
def list_strategies(session: SessionDep, current_user: CurrentUser,
                    version_id: int | None = None, branch_id: int | None = None):
    strategies = session.exec(select(Strategy)).all()
    if branch_id:
        strategies = [s for s in strategies if s.branch_id == branch_id]
    elif version_id:
        strategies = [s for s in strategies
                      if s.branch and s.branch.version_id == version_id]
    items = []
    for s in strategies:
        version = session.get(Version, s.branch.version_id) if s.branch else None
        items.append({"id": s.id, "branch_id": s.branch_id,
                      "branch_name": s.branch.name if s.branch else None,
                      "version_id": s.branch.version_id if s.branch else None,
                      "version_name": version.name if version else None,
                      "template_id": s.template_id,
                      "template_name": s.template.name if s.template else None,
                      "name": s.name,
                      "build_start_time": s.build_start_time, "push_mode": s.push_mode,
                      "enabled": s.enabled})
    return ok(items)


@router.post("/preview")
def preview_strategy(req: StrategyCreate, session: SessionDep, current_user: CurrentUser):
    conflicts, timeline = _preview_or_create(session, current_user, req)
    return ok({"conflicts": conflicts, "timeline": {
        k: ({f: v[f].isoformat() for f in ("start", "end")} if v else None)
        for k, v in timeline.items()}})


@router.post("")
def create_strategy(req: StrategyCreate, session: SessionDep, current_user: CurrentUser):
    conflicts, _ = _preview_or_create(session, current_user, req)
    if conflicts:
        raise_conflict("策略时间冲突，无法保存", conflicts)
    s = Strategy(branch_id=req.branch_id, template_id=req.template_id, name=req.name,
                 build_start_time=req.build_start_time, push_mode=req.push_mode,
                 enabled=req.enabled, created_by=current_user.id)
    session.add(s)
    session.commit()
    session.refresh(s)
    return ok({"id": s.id})


@router.patch("/{strategy_id}")
def update_strategy(strategy_id: int, req: StrategyCreate, session: SessionDep,
                    current_user: CurrentUser):
    s = session.get(Strategy, strategy_id)
    if not s:
        raise_param("策略不存在")
    _check_pm_owns_version(session, current_user, s.branch_id)
    conflicts, _ = _preview_or_create(session, current_user, req, strategy_id)
    if conflicts:
        raise_conflict("策略时间冲突，无法保存", conflicts)
    # 写变更日志
    for field, old, new in [("build_start_time", s.build_start_time, req.build_start_time),
                            ("push_mode", s.push_mode, req.push_mode),
                            ("name", s.name, req.name)]:
        if old != new:
            session.add(StrategyChangeLog(strategy_id=s.id, operator=current_user.id,
                                          field=field, old_value=str(old), new_value=str(new)))
    s.branch_id = req.branch_id
    s.template_id = req.template_id
    s.name = req.name
    s.build_start_time = req.build_start_time
    s.push_mode = req.push_mode
    s.enabled = req.enabled
    session.commit()
    return ok({"id": s.id})


@router.patch("/{strategy_id}/toggle")
def toggle_strategy(strategy_id: int, enabled: bool, session: SessionDep,
                    current_user: CurrentUser):
    s = session.get(Strategy, strategy_id)
    if not s:
        raise_param("策略不存在")
    _check_pm_owns_version(session, current_user, s.branch_id)
    s.enabled = enabled
    session.add(StrategyChangeLog(strategy_id=s.id, operator=current_user.id, field="enabled",
                                  old_value=str(not enabled), new_value=str(enabled)))
    session.commit()
    return ok({"id": s.id, "enabled": s.enabled})
