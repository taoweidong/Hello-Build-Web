"""版本计划：版本→分支→策略→时间线。"""
from django.conf import settings
from django.db.models import OuterRef, Prefetch, Subquery
from django.utils import timezone

from ..api import ok
from ..models import Branch, ExecutionRound, Strategy, Version
from ..services.config import get_config
from ..services.conflict import detect_conflicts
from ..services.timeline import build_timeline
from . import authed_user, json_resp


def _conflicted_ids(items, build_minutes, push_minutes, sync_buffer_minutes, ds):
    """两两比较同分支策略的阶段（冒烟/分析）时间，返回相互重叠的策略 id 集合。"""
    conflicted = set()
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            hits = detect_conflicts(ds, [items[i]], [items[j]],
                                    build_minutes, push_minutes, sync_buffer_minutes)
            if hits:
                conflicted.add(items[i]["id"])
                conflicted.add(items[j]["id"])
    return conflicted


def plan_view(request):
    user, resp = authed_user(request)
    if resp:
        return resp
    ds = request.GET.get("date") or timezone.localdate().strftime("%Y-%m-%d")
    versions = Version.objects.select_related("pm_user").prefetch_related(
        Prefetch("branches", queryset=Branch.objects.all().order_by("name")),
        Prefetch(
            "branches__strategies",
            queryset=Strategy.objects.filter(enabled=True).select_related("template"),
            to_attr="enabled_strategies",
        ),
    ).all()

    # 批量取每个策略最近一个执行轮次的结论（按 exec_date 最新），避免逐策略 N+1。
    # 在 Strategy 上 annotate：外层即 Strategy，OuterRef("pk") 关联其主键，
    # 内层 ExecutionRound.strategy_id == 该 Strategy.id（此前误在 ExecutionRound 外层
    # 用 OuterRef("pk") 关联轮次 id，导致 status 恒为空）。
    latest_round = ExecutionRound.objects.filter(
        strategy_id=OuterRef("pk")
    ).order_by("-exec_date", "-id")
    status_map = {
        s.id: (s.latest_conclusion or "pending")
        for s in Strategy.objects.annotate(
            latest_conclusion=Subquery(latest_round.values("conclusion")[:1])
        )
    }

    build_minutes = get_config("build_minutes", settings.BUILD_MINUTES)
    push_minutes = get_config("push_minutes", settings.PUSH_MINUTES)
    sync_buffer_minutes = get_config("sync_buffer_minutes", settings.SYNC_BUFFER_MINUTES)

    result = []
    for v in versions:
        branches = []
        for b in v.branches.all():
            enabled = b.enabled_strategies
            raw = [{
                "id": s.id,
                "strategy_name": s.name,
                "build_start_time": s.build_start_time,
                "template": s.template,
                "push_mode": s.push_mode,
                "push_start_time": s.push_start_time,
            } for s in enabled]
            conflicted = _conflicted_ids(raw, build_minutes, push_minutes,
                                         sync_buffer_minutes, ds)
            strategies = []
            for s in enabled:
                tl = build_timeline(
                    ds, s.build_start_time, s.template.smoke_minutes, s.template.analysis_minutes,
                    build_minutes, push_minutes, sync_buffer_minutes,
                    s.push_mode, push_start_time=s.push_start_time,
                )
                strategies.append({
                    "id": s.id,
                    "name": s.name,
                    "push_mode": s.push_mode,
                    "build_start_time": s.build_start_time,
                    "push_start_time": s.push_start_time,
                    "enabled": s.enabled,
                    "conflict": s.id in conflicted,
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
