"""互斥检测：同版本跨分支构建阶段时间重叠。"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def find_overlaps(intervals):
    """intervals: [{label,start,end}]，返回重叠对列表。"""
    hits = []
    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            a, b = intervals[i], intervals[j]
            if a["start"] < b["end"] and b["start"] < a["end"]:
                hits.append({
                    "first": a["label"],
                    "second": b["label"],
                    "overlap_start": max(a["start"], b["start"]).strftime("%Y-%m-%dT%H:%M:%S"),
                    "overlap_end": min(a["end"], b["end"]).strftime("%Y-%m-%dT%H:%M:%S"),
                })
    return hits


def check_build_mutex(version_id, build_start_time, build_min,
                      exclude_strategy_id=None):
    """校验同版本其它启用策略的构建阶段是否与目标构建区间重叠。返回命中列表。"""
    from django.conf import settings
    from ..models import Strategy
    from .timeline import build_timeline, parse_cd, parse_hhmm

    base = parse_cd("2026-08-10")
    target_start = parse_hhmm(base, build_start_time)
    target_end = target_start + timedelta(minutes=build_min)

    query = Strategy.objects.select_related("branch", "template").filter(
        branch__version_id=version_id, enabled=True
    )
    if exclude_strategy_id:
        query = query.exclude(id=exclude_strategy_id)

    hits = []
    for s in query:
        try:
            tl = build_timeline(
                "2026-08-10", s.build_start_time,
                s.template.smoke_minutes, s.template.analysis_minutes,
                settings.BUILD_MINUTES, settings.PUSH_MINUTES,
                settings.SYNC_BUFFER_MINUTES, s.push_mode,
                push_start_time=s.push_start_time,
            )
        except (ValueError, TypeError, AttributeError) as exc:
            logger.warning("策略 %s 时间线推导失败，跳过互斥校验：%s", s.name, exc)
            continue
        s_start = _parse_iso(tl["build"]["start"])
        s_end = _parse_iso(tl["build"]["end"])
        if s_start < target_end and target_start < s_end:
            hits.append({
                "strategy": f"{s.branch.name}/{s.name}",
                "overlap_start": max(s_start, target_start).strftime("%Y-%m-%dT%H:%M:%S"),
                "overlap_end": min(s_end, target_end).strftime("%Y-%m-%dT%H:%M:%S"),
            })
    return hits


def _parse_iso(iso_str):
    return datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%S")