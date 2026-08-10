"""周视图：指定周的开始日期 + 版本 → 分支策略排布。"""
from datetime import datetime, timedelta

from ..api import ok
from ..models import Branch, Version
from . import authed_user, json_resp


def _weekdays(week_start):
    start = datetime.strptime(week_start, "%Y-%m-%d").date()
    return [
        {"date": (start + timedelta(days=i)).strftime("%Y-%m-%d"),
         "weekday": (start + timedelta(days=i)).strftime("%A")}
        for i in range(7)
    ]


def weekly_view(request):
    user, resp = authed_user(request)
    if resp:
        return resp
    week_start = request.GET.get("week_start", _default_monday())
    version_id = request.GET.get("version_id")
    version = None
    versions = list(Version.objects.select_related("pm_user").all())
    if version_id:
        version = Version.objects.filter(id=version_id).first()
    branches = []
    strategies = []
    if version:
        for b in version.branches.all().order_by("name"):
            branches.append({"branch_id": b.id, "branch_name": b.name})
        qs = Branch.objects.filter(version=version).prefetch_related("strategies__template")
        for b in qs:
            for s in b.strategies.filter(enabled=True).select_related("template").order_by("build_start_time"):
                strategies.append({
                    "strategy_id": s.id,
                    "strategy_name": s.name,
                    "branch_id": b.id,
                    "branch_name": b.name,
                    "build_start_time": s.build_start_time,
                    "push_start_time": s.push_start_time,
                    "template_name": s.template.name,
                })
    return json_resp(ok({
        "week_start": week_start,
        "days": _weekdays(week_start),
        "version": {"version_id": version.id, "version_name": version.name} if version else None,
        "versions": [{"version_id": v.id, "version_name": v.name} for v in versions],
        "branches": branches,
        "strategies": strategies,
    }))


def _default_monday():
    today = datetime.now().date()
    return (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")