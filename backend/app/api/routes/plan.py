from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.core.response import ok
from app.models import Branch, ExecutionRound, Strategy, User, Version
from app.services.conflict import detect_conflicts
from app.services.timeline import build_timeline

router = APIRouter(tags=["plan"])


@router.get("/plan")
def get_plan(
    session: SessionDep,
    current_user: CurrentUser,
    date: str | None = Query(None),
    version_id: int | None = None,
    branch_id: int | None = None,
):
    """甘特看板聚合：版本→分支→策略→各阶段时间区间+冲突标记"""
    d = date or datetime.now(UTC).strftime("%Y-%m-%d")
    versions = session.exec(select(Version)).all()
    result = []
    for v in versions:
        if version_id and v.id != version_id:
            continue
        branches = session.exec(select(Branch).where(Branch.version_id == v.id)).all()
        branches = [b for b in branches if not branch_id or b.id == branch_id]
        pm = session.get(User, v.pm_user_id) if v.pm_user_id else None
        vb = {
            "version_id": v.id, "version_name": v.name,
            "pm_name": pm.display_name if pm else None, "branches": [],
        }
        for b in branches:
            strategies = session.exec(
                select(Strategy).where(
                    Strategy.branch_id == b.id, Strategy.enabled == True  # noqa: E712
                )
            ).all()
            # 同分支内 48h 窗口冲突检测，用于红色斜纹标记
            existing = [{"id": s.id, "build_start_time": s.build_start_time, "template": s.template,
                         "push_mode": s.push_mode, "strategy_name": s.name} for s in strategies]
            conflicts = detect_conflicts(d, [], existing, settings.build_minutes,
                                         settings.push_minutes, settings.sync_buffer_minutes)
            conflict_names = {c["strategy_name"] for c in conflicts}
            sb = {"branch_id": b.id, "branch_name": b.name, "strategies": []}
            for s in strategies:
                t = s.template
                assert t is not None
                tl = build_timeline(d, s.build_start_time, t.smoke_minutes, t.analysis_minutes,
                                    settings.build_minutes, settings.push_minutes,
                                    settings.sync_buffer_minutes, s.push_mode)
                round_rec = session.exec(
                    select(ExecutionRound).where(
                        ExecutionRound.strategy_id == s.id, ExecutionRound.exec_date == d
                    )
                ).first()
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
