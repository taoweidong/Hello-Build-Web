"""时间线推导：构建/冒烟/分析/推送各阶段起止。

有 push_start_time → 推送固定为 push_start_time ~ +push_minutes；
空 → normal 模式推送为 null；sync 模式推送在构建前预留 sync_buffer。
"""
from datetime import date, datetime, timedelta


def parse_cd(ds: str) -> date:
    return datetime.strptime(ds, "%Y-%m-%d").date()


def parse_hhmm(base: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(base, datetime.min.time().replace(hour=h, minute=m))


def build_timeline(ds, build_start_time, smoke_min, analysis_min,
                   build_min, push_min, sync_buffer, push_mode, push_start_time=None):
    base = parse_cd(ds)
    build_start = parse_hhmm(base, build_start_time)
    build_end = build_start + timedelta(minutes=build_min)
    smoke_start = build_end
    smoke_end = smoke_start + timedelta(minutes=smoke_min)
    analysis_start = smoke_end
    analysis_end = analysis_start + timedelta(minutes=analysis_min)

    push = None
    if push_start_time:
        push_start = parse_hhmm(base, push_start_time)
        push_end = push_start + timedelta(minutes=push_min)
        push = {"start": _iso(push_start), "end": _iso(push_end)}
    elif push_mode == "sync":
        push_start = build_start - timedelta(minutes=push_min + sync_buffer)
        push_end = build_start - timedelta(minutes=sync_buffer)
        push = {"start": _iso(push_start), "end": _iso(push_end)}

    return {
        "push": push,
        "build": {"start": _iso(build_start), "end": _iso(build_end)},
        "smoke": {"start": _iso(smoke_start), "end": _iso(smoke_end)},
        "analysis": {"start": _iso(analysis_start), "end": _iso(analysis_end)},
    }


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")