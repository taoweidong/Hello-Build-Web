"""周视图：指定周的开始日期 + 版本 → 分支策略排布。"""
from datetime import datetime, timedelta

from django.db.models import Prefetch
from django.utils import timezone

from ..api import ok
from ..models import Branch, Strategy, Version
from . import authed_user, fail_resp, json_resp, parse_int
from ..errors import CODE_UNPROCESSABLE


_WEEKDAY_ZH = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def _weekdays(week_start):
    start = datetime.strptime(week_start, "%Y-%m-%d").date()
    return [
        {"date": (start + timedelta(days=i)).strftime("%Y-%m-%d"),
         "weekday": _WEEKDAY_ZH[(start + timedelta(days=i)).weekday()]}
        for i in range(7)
    ]


def weekly_view(request):
    user, resp = authed_user(request)
    if resp:
        return resp
    week_start = request.GET.get("week_start", _default_monday())
    raw_version_id = request.GET.get("version_id")
    version = None
    versions = list(Version.objects.select_related("pm_user").all())
    if raw_version_id:
        # 非数字 version_id 直接 422，避免 filter(id="abc") 抛 ValueError 变成 500
        version_id = parse_int(raw_version_id)
        if version_id is None:
            return fail_resp(CODE_UNPROCESSABLE, "version_id 应为整数")
        version = Version.objects.filter(id=version_id).first()
    try:
        days = _weekdays(week_start)
    except ValueError:
        return fail_resp(CODE_UNPROCESSABLE, "week_start 格式应为 YYYY-MM-DD")
    branches = []
    strategies = []
    if version:
        qs = Branch.objects.filter(version=version).order_by("name").prefetch_related(
            Prefetch(
                "strategies",
                queryset=Strategy.objects.filter(enabled=True)
                    .select_related("template")
                    .order_by("build_start_time"),
                to_attr="enabled_strategies",
            )
        )
        for b in qs:
            branches.append({"branch_id": b.id, "branch_name": b.name})
            for s in b.enabled_strategies:
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
        "days": days,
        "version": {"version_id": version.id, "version_name": version.name} if version else None,
        "versions": [{"version_id": v.id, "version_name": v.name} for v in versions],
        "branches": branches,
        "strategies": strategies,
    }))


def _default_monday():
    today = timezone.localdate()
    return (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")