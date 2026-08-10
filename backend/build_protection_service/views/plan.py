"""版本计划：版本→分支→策略→时间线。"""
from django.conf import settings
from django.db.models import OuterRef, Prefetch, Subquery

from ..api import ok
from ..models import Branch, ExecutionRound, Strategy, Version
from ..services.timeline import build_timeline
from . import authed_user, json_resp


def plan_view(request):
    user, resp = authed_user(request)
    if resp:
        return resp
    ds = request.GET.get("date", "2026-08-10")
    versions = Version.objects.select_related("pm_user").prefetch_related(
        Prefetch("branches", queryset=Branch.objects.all().order_by("name")),
        Prefetch(
            "branches__strategies",
            queryset=Strategy.objects.filter(enabled=True).select_related("template"),
            to_attr="enabled_strategies",
        ),
    ).all()

    # 批量取每个策略最近一个执行轮次的结论，避免逐策略 N+1
    latest = ExecutionRound.objects.filter(strategy_id=OuterRef("pk")).order_by("-exec_date")
    status_map = {
        c.strategy_id: c.conclusion or "pending"
        for c in ExecutionRound.objects.filter(id=Subquery(latest.values("id")[:1]))
    }

    result = []
    for v in versions:
        branches = []
        for b in v.branches.all():
            strategies = []
            for s in b.enabled_strategies:
                tl = build_timeline(
                    ds, s.build_start_time, s.template.smoke_minutes, s.template.analysis_minutes,
                    settings.BUILD_MINUTES, settings.PUSH_MINUTES, settings.SYNC_BUFFER_MINUTES,
                    s.push_mode, push_start_time=s.push_start_time,
                )
                strategies.append({
                    "id": s.id,
                    "name": s.name,
                    "push_mode": s.push_mode,
                    "build_start_time": s.build_start_time,
                    "push_start_time": s.push_start_time,
                    "enabled": s.enabled,
                    "conflict": False,
                    "timeline": tl,
                    "status": status_map.get(s.id),
                })
            branches.append({
                "branch_id": b.id,
                "branch_name": b.name,
                "strategies": strategies,
            })
        result.append({
            "version_id": v.id,
            "version_name": v.name,
            "pm_name": v.pm_user.display_name or v.pm_user.username,
            "branches": branches,
        })
    return json_resp(ok(result))