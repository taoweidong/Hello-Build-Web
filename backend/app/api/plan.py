from datetime import datetime, date as date_mod, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from ..database import get_db
from ..security import get_current_user
from ..errors import ok
from ..models.version import Version
from ..models.branch import Branch
from ..models.strategy import Strategy, StrategyTemplate
from ..models.user import User
from ..services.timeline import build_timeline
from ..services.conflict import detect_conflicts
from ..config import settings
from ..models.execution import ExecutionRound

router = APIRouter()

@router.get("/plan")
def get_plan(date: str = Query(None), version_id: int = None, branch_id: int = None,
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """甘特看板聚合：版本→分支→策略→各阶段时间区间+冲突标记"""
    d = date or date_mod.today().strftime("%Y-%m-%d")
    versions = db.query(Version).options(joinedload(Version.branches)).all()
    result = []
    for v in versions:
        if version_id and v.id != version_id:
            continue
        branches = [b for b in v.branches if not branch_id or b.id == branch_id]
        pm = db.get(User, v.pm_user_id) if v.pm_user_id else None
        vb = {"version_id": v.id, "version_name": v.name,
              "pm_name": pm.display_name if pm else None, "branches": []}
        for b in branches:
            strategies = db.query(Strategy).filter(Strategy.branch_id == b.id, Strategy.enabled == True).options(joinedload(Strategy.template)).all()
            # 同分支内 48h 窗口冲突检测，用于红色斜纹标记
            existing = [{"id": s.id, "build_start_time": s.build_start_time, "template": s.template,
                         "push_mode": s.push_mode, "strategy_name": s.name} for s in strategies]
            conflicts = detect_conflicts(d, [], existing, settings.build_minutes,
                                         settings.push_minutes, settings.sync_buffer_minutes)
            conflict_names = {c["strategy_name"] for c in conflicts}
            sb = {"branch_id": b.id, "branch_name": b.name, "strategies": []}
            for s in strategies:
                t = s.template
                tl = build_timeline(d, s.build_start_time, t.smoke_minutes, t.analysis_minutes,
                                    settings.build_minutes, settings.push_minutes,
                                    settings.sync_buffer_minutes, s.push_mode)
                round_rec = db.query(ExecutionRound).filter(ExecutionRound.strategy_id == s.id,
                                                            ExecutionRound.exec_date == d).first()
                sb["strategies"].append({
                    "id": s.id, "name": s.name, "push_mode": s.push_mode,
                    "build_start_time": s.build_start_time, "enabled": s.enabled,
                    "conflict": s.name in conflict_names,
                    "timeline": {
                        "push": {"start": tl["push"]["start"].isoformat(), "end": tl["push"]["end"].isoformat()} if tl["push"] else None,
                        "build": {"start": tl["build"]["start"].isoformat(), "end": tl["build"]["end"].isoformat()},
                        "smoke": {"start": tl["smoke"]["start"].isoformat(), "end": tl["smoke"]["end"].isoformat()},
                        "analysis": {"start": tl["analysis"]["start"].isoformat(), "end": tl["analysis"]["end"].isoformat()},
                    },
                    "status": round_rec.conclusion if round_rec else "pending",
                })
            vb["branches"].append(sb)
        result.append(vb)
    return ok(result)