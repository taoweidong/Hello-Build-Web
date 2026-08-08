from datetime import datetime, timedelta
from .timeline import parse_build_start, build_timeline

def _occupancy_for(date: str, build_start_time: str, smoke_min: int, analysis_min: int,
                   push_mode: str, build_min=30, push_min=20, sync_buffer=20):
    tl = build_timeline(date, build_start_time, smoke_min, analysis_min,
                        build_min, push_min, sync_buffer, push_mode)
    start = tl["push"]["start"] if tl["push"] else tl["build"]["start"]
    end = tl["analysis"]["end"]
    return start, end

def detect_conflicts(date: str, candidates, existing, build_min=30, push_min=20, sync_buffer=20):
    """candidates: [{build_start_time, template, push_mode, strategy_name}]
       existing: [{id, build_start_time, template, push_mode, strategy_name}]
       在 48h 窗口（date-1 到 date+1）内检测同分支策略占用区间是否交错。
       返回冲突列表 [{strategy_name, overlap_start, overlap_end}]"""
    window_day = datetime.strptime(date, "%Y-%m-%d")
    conflicts = []
    all_items = [(c, c["strategy_name"]) for c in candidates] + \
                [(e, e["strategy_name"]) for e in existing]
    for i in range(len(all_items)):
        for j in range(i + 1, len(all_items)):
            a, an = all_items[i]; b, bn = all_items[j]
            for d_off in (-1, 0, 1):
                d = (window_day + timedelta(days=d_off)).strftime("%Y-%m-%d")
                a_tl = build_timeline(d, a["build_start_time"], a["template"].smoke_minutes,
                                      a["template"].analysis_minutes, build_min, push_min,
                                      sync_buffer, a["push_mode"])
                b_tl = build_timeline(d, b["build_start_time"], b["template"].smoke_minutes,
                                      b["template"].analysis_minutes, build_min, push_min,
                                      sync_buffer, b["push_mode"])
                a_start = a_tl["push"]["start"] if a_tl["push"] else a_tl["build"]["start"]
                a_end = a_tl["analysis"]["end"]
                b_start = b_tl["push"]["start"] if b_tl["push"] else b_tl["build"]["start"]
                b_end = b_tl["analysis"]["end"]
                if a_start < b_end and b_start < a_end:
                    conflicts.append({"strategy_name": bn, "overlap_start": max(a_start, b_start),
                                      "overlap_end": min(a_end, b_end)})
    return conflicts