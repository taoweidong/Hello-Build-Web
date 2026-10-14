"""时间线推导：构建/冒烟/分析/推送各阶段起止。

有 push_start_time → 推送固定为 push_start_time ~ +push_minutes；
空 → normal 模式推送为 null；sync 模式推送在构建前预留 sync_buffer。
"""
import re
from datetime import date, datetime, timedelta


def parse_cd(ds: str) -> date:
    return datetime.strptime(ds, "%Y-%m-%d").date()


def valid_hhmm(hhmm) -> bool:
    """严格校验 HH:MM：小时 0-23、分钟 0-59，拦截 "99:99" 之类正则放行的非法值。

    前置 isascii（R4-B12/B4-12）：正则 \\d 会匹配 Unicode 全角数字（"２２:００"），
    与 parsing.parse_int 的 isascii 硬化口径对齐；全角时间串入库后按字符串
    排序的 Strategy（ordering=build_start_time）会错位。
    """
    if not isinstance(hhmm, str) or not hhmm.isascii():
        return False
    if not re.fullmatch(r"\d{2}:\d{2}", hhmm):
        return False
    h, m = hhmm.split(":")
    return int(h) <= 23 and int(m) <= 59


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