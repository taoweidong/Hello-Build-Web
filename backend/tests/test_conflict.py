from app.services.conflict import detect_conflicts
from types import SimpleNamespace

def _tmpl(smoke, analysis):
    return SimpleNamespace(smoke_minutes=smoke, analysis_minutes=analysis)

def test_no_conflict_same_branch_diff_time():
    cand = [{"build_start_time": "22:00", "template": _tmpl(480, 120), "push_mode": "sync", "strategy_name": "A"}]
    existing = [{"build_start_time": "12:00", "template": _tmpl(120, 60), "push_mode": "normal", "strategy_name": "B"}]
    assert detect_conflicts("2026-08-08", cand, existing) == []

def test_conflict_same_branch_overlap():
    cand = [{"build_start_time": "22:00", "template": _tmpl(480, 120), "push_mode": "sync", "strategy_name": "A"}]
    existing = [{"build_start_time": "21:00", "template": _tmpl(480, 120), "push_mode": "sync", "strategy_name": "B"}]
    # 21:00 构建的占用区间 20:20~次日07:30，与 A 的 21:20 起重叠
    assert len(detect_conflicts("2026-08-08", cand, existing)) >= 1