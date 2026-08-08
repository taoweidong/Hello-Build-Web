from datetime import datetime, timedelta
from ..config import settings

def parse_build_start(date: str, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.strptime(date, "%Y-%m-%d").replace(hour=h, minute=m)

def build_timeline(date: str, build_start_time: str, smoke_min: int, analysis_min: int,
                   build_min: int = None, push_min: int = None, sync_buffer: int = None,
                   push_mode: str = "normal"):
    """返回 dict：build/smoke/analysis 各阶段 start/end；sync 模式含 push；normal 模式 push 为 None（结论后触发）"""
    build_min = build_min or settings.build_minutes
    push_min = push_min or settings.push_minutes
    sync_buffer = sync_buffer or settings.sync_buffer_minutes
    T = parse_build_start(date, build_start_time)
    build_end = T + timedelta(minutes=build_min)
    smoke_end = build_end + timedelta(minutes=smoke_min)
    analysis_end = smoke_end + timedelta(minutes=analysis_min)
    tl = {
        "build": {"start": T, "end": build_end},
        "smoke": {"start": build_end, "end": smoke_end},
        "analysis": {"start": smoke_end, "end": analysis_end},
        "push": None,
    }
    if push_mode == "sync":
        tl["push"] = {"start": T - timedelta(minutes=push_min + sync_buffer),
                      "end": T - timedelta(minutes=sync_buffer)}
    return tl