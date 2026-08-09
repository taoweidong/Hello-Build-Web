from app.services.timeline import build_timeline, parse_build_start


def test_sync_push_before_build_20min():
    tl = build_timeline("2026-08-08", "22:00", 480, 120, push_mode="sync")
    assert tl["push"]["end"].strftime("%H:%M") == "21:40"
    assert tl["push"]["start"].strftime("%H:%M") == "21:20"
    assert tl["build"]["start"].strftime("%H:%M") == "22:00"


def test_normal_push_is_none():
    tl = build_timeline("2026-08-08", "22:00", 480, 120, push_mode="normal")
    assert tl["push"] is None


def test_analysis_crosses_midnight():
    tl = build_timeline("2026-08-08", "22:00", 480, 120, push_mode="normal")
    assert tl["analysis"]["end"].day == 9
    assert tl["analysis"]["end"].strftime("%H:%M") == "08:30"


def test_parse_build_start():
    assert parse_build_start("2026-08-08", "16:30").hour == 16
    assert parse_build_start("2026-08-08", "16:30").minute == 30
