from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from ..database import get_db
from ..security import get_current_user
from ..errors import ok, raise_forbidden, raise_conflict, raise_param
from ..models.version import Version
from ..models.branch import Branch
from ..models.strategy import Strategy, StrategyTemplate
from ..models.audit import StrategyChangeLog
from ..services.conflict import detect_conflicts
from ..services.timeline import build_timeline
from ..config import settings
from ..models.user import User

router = APIRouter()

class StrategyReq(BaseModel):
    branch_id: int
    template_id: int
    name: str
    build_start_time: str  # "HH:MM"
    push_mode: str  # normal/sync
    enabled: bool = True

def _check_pm_owns_version(user, branch_id, db):
    """PM 只能操作所属版本的分支策略"""
    if user.role != "pm":
        return
    branch = db.get(Branch, branch_id)
    version = db.get(Version, branch.version_id) if branch else None
    if not version or version.pm_user_id != user.id:
        raise_forbidden("仅能配置本版本分支的策略")

def _preview_or_create(db, user, req, strategy_id=None):
    branch = db.get(Branch, req.branch_id)
    if not branch:
        raise_param("分支不存在")
    _check_pm_owns_version(user, req.branch_id, db)
    template = db.get(StrategyTemplate, req.template_id)
    if not template:
        raise_param("模板不存在")
    # 48h 冲突检测（同分支内）
    date = "2026-08-08"  # 用参考日期做相对排布检测
    existing = db.query(Strategy).filter(Strategy.branch_id == req.branch_id).all()
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
def list_strategies(version_id: int = None, branch_id: int = None,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Strategy).options(joinedload(Strategy.branch), joinedload(Strategy.template))
    if branch_id:
        q = q.filter(Strategy.branch_id == branch_id)
    elif version_id:
        q = q.join(Branch).filter(Branch.version_id == version_id)
    items = []
    for s in q.all():
        items.append({"id": s.id, "branch_id": s.branch_id, "branch_name": s.branch.name,
                      "version_id": s.branch.version_id, "template_id": s.template_id,
                      "template_name": s.template.name, "name": s.name,
                      "build_start_time": s.build_start_time, "push_mode": s.push_mode,
                      "enabled": s.enabled})
    return ok(items)

@router.post("/preview")
def preview_strategy(req: StrategyReq, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    conflicts, timeline = _preview_or_create(db, user, req)
    return ok({"conflicts": conflicts, "timeline": {
        k: ({f: v[f].isoformat() for f in ("start", "end")} if v else None)
        for k, v in timeline.items()}})

@router.post("")
def create_strategy(req: StrategyReq, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    conflicts, _ = _preview_or_create(db, user, req)
    if conflicts:
        raise_conflict("策略时间冲突，无法保存", conflicts)
    s = Strategy(branch_id=req.branch_id, template_id=req.template_id, name=req.name,
                 build_start_time=req.build_start_time, push_mode=req.push_mode,
                 enabled=req.enabled, created_by=user.id)
    db.add(s); db.commit(); db.refresh(s)
    return ok({"id": s.id})

@router.patch("/{strategy_id}")
def update_strategy(strategy_id: int, req: StrategyReq, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    s = db.get(Strategy, strategy_id)
    if not s:
        raise_param("策略不存在")
    _check_pm_owns_version(user, s.branch_id, db)
    conflicts, _ = _preview_or_create(db, user, req, strategy_id)
    if conflicts:
        raise_conflict("策略时间冲突，无法保存", conflicts)
    # 写变更日志
    for field, old, new in [("build_start_time", s.build_start_time, req.build_start_time),
                            ("push_mode", s.push_mode, req.push_mode),
                            ("name", s.name, req.name)]:
        if old != new:
            db.add(StrategyChangeLog(strategy_id=s.id, operator=user.id, field=field,
                                     old_value=str(old), new_value=str(new)))
    s.branch_id = req.branch_id; s.template_id = req.template_id; s.name = req.name
    s.build_start_time = req.build_start_time; s.push_mode = req.push_mode; s.enabled = req.enabled
    db.commit()
    return ok({"id": s.id})

@router.patch("/{strategy_id}/toggle")
def toggle_strategy(strategy_id: int, enabled: bool, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    s = db.get(Strategy, strategy_id)
    if not s:
        raise_param("策略不存在")
    _check_pm_owns_version(user, s.branch_id, db)
    s.enabled = enabled
    db.add(StrategyChangeLog(strategy_id=s.id, operator=user.id, field="enabled",
                             old_value=str(not enabled), new_value=str(enabled)))
    db.commit()
    return ok({"id": s.id, "enabled": s.enabled})