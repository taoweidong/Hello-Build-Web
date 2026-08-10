"""阶段冲突检测：同分支内冒烟/分析阶段与其它策略重叠（推送除外）。"""
from datetime import datetime

from .timeline import build_timeline


def detect_conflicts(ds, candidates, existing, build_min, push_min, sync_buffer):
    """candidates/existing: [{build_start_time, template, push_mode, strategy_name, push_start_time}]。

    返回 [{strategy_name, overlap_start, overlap_end}]（重叠的冒烟/分析阶段）。
    """
    def _stages(item):
        return build_timeline(
            ds, item["build_start_time"], item["template"].smoke_minutes,
            item["template"].analysis_minutes, build_min, push_min, sync_buffer,
            item["push_mode"], push_start_time=item.get("push_start_time"),
        )

    cand_stages = [{"name": c["strategy_name"], "tl": _stages(c)} for c in candidates]
    results = []
    for c in cand_stages:
        for e in existing:
            etl = _stages(e)
            for key in ("smoke", "analysis"):
                if not etl[key] or not c["tl"][key]:
                    continue
                a_s, a_e = _parse(c["tl"][key]["start"]), _parse(c["tl"][key]["end"])
                b_s, b_e = _parse(etl[key]["start"]), _parse(etl[key]["end"])
                if a_s < b_e and b_s < a_e:
                    results.append({
                        "strategy_name": e["strategy_name"],
                        "overlap_start": max(a_s, b_s).strftime("%Y-%m-%dT%H:%M:%S"),
                        "overlap_end": min(a_e, b_e).strftime("%Y-%m-%dT%H:%M:%S"),
                    })
    return results


def _parse(iso_str):
    return datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%S")