"""互斥检测：同版本跨分支构建阶段时间重叠。"""
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

# 目标区间在 find_overlaps 结果中的哨兵标签（不会与 "分支/策略名" 形态的标签冲突）
_TARGET_LABEL = "__target__"


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
                      exclude_strategy_id=None, ds=None):
    """校验同版本其它启用策略的构建阶段是否与目标构建区间重叠。返回命中列表。

    ds 为基准日期（"YYYY-MM-DD"），缺省取当天；仅用于相对时间比较，不影响重叠结果。
    区间比较复用 find_overlaps（同一重叠语义，消除两份内联实现）；
    输出保持 {strategy, overlap_start, overlap_end} 契约（extra.mutex 直接回传前端）。
    """
    from django.conf import settings
    from django.utils import timezone as dj_timezone
    from ..models import Strategy
    from .config import get_config
    from .timeline import parse_cd, parse_hhmm

    build_minutes = get_config("build_minutes", settings.BUILD_MINUTES)

    if ds is None:
        ds = dj_timezone.localdate().strftime("%Y-%m-%d")
    base = parse_cd(ds)
    target_start = parse_hhmm(base, build_start_time)
    intervals = [{
        "label": _TARGET_LABEL,
        "start": target_start,
        "end": target_start + timedelta(minutes=build_min),
    }]

    query = Strategy.objects.select_related("branch", "template").filter(
        branch__version_id=version_id, enabled=True
    )
    if exclude_strategy_id:
        query = query.exclude(id=exclude_strategy_id)

    for s in query:
        try:
            s_start = parse_hhmm(base, s.build_start_time)
        except (ValueError, TypeError) as exc:
            logger.warning("策略 %s 构建时间非法，跳过互斥校验：%s", s.name, exc)
            continue
        intervals.append({
            "label": f"{s.branch.name}/{s.name}",
            "start": s_start,
            "end": s_start + timedelta(minutes=build_minutes),
        })

    hits = []
    for ov in find_overlaps(intervals):
        if _TARGET_LABEL not in (ov["first"], ov["second"]):
            continue  # 既有策略之间的相互重叠不属于本校验范围
        hits.append({
            "strategy": ov["second"] if ov["first"] == _TARGET_LABEL else ov["first"],
            "overlap_start": ov["overlap_start"],
            "overlap_end": ov["overlap_end"],
        })
    return hits
