from datetime import datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from .models import Branch, Strategy, StrategyTemplate, Version
from .services import conflict, mutex, timeline

User = get_user_model()


class ModelTests(TestCase):
    def setUp(self):
        self.pm = User.objects.create_user(
            username="pm1", password="123456", role="pm"
        )
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")
        self.tmpl = StrategyTemplate.objects.create(
            name="晚间全量冒烟", smoke_minutes=480, analysis_minutes=120
        )

    def test_strategy_push_start_time_nullable(self):
        s = Strategy.objects.create(
            branch=self.branch, template=self.tmpl, name="27A-master-晚间",
            build_start_time="22:00", push_mode="normal", created_by=self.pm,
        )
        self.assertIsNone(s.push_start_time)

    def test_strategy_push_start_time_settable(self):
        s = Strategy.objects.create(
            branch=self.branch, template=self.tmpl, name="27A-master-晚间",
            build_start_time="22:00", push_start_time="20:00",
            push_mode="normal", created_by=self.pm,
        )
        self.assertEqual(s.push_start_time, "20:00")

    def test_branch_unique_per_version(self):
        # setUp 已创建 master，重复创建应触发唯一约束
        with self.assertRaises(IntegrityError):
            Branch.objects.create(version=self.version, name="master")

    def test_version_pm_unique(self):
        # setUp 已用 self.pm 绑定 27A，同一 pm 再绑定其他版本应触发唯一约束
        with self.assertRaises(IntegrityError):
            Version.objects.create(name="27B", pm_user=self.pm, status="active")


class TimelineTests(TestCase):
    def test_build_timeline_normal_push_null(self):
        tl = timeline.build_timeline("2026-08-10", "22:00", 480, 120, 30, 20, 20, "normal", push_start_time=None)
        self.assertIsNone(tl["push"])
        self.assertEqual(tl["build"]["start"], "2026-08-10T22:00:00")

    def test_build_timeline_fixed_push(self):
        tl = timeline.build_timeline("2026-08-10", "22:00", 480, 120, 30, 20, 20, "normal", push_start_time="20:00")
        self.assertIsNotNone(tl["push"])
        self.assertEqual(tl["push"]["start"], "2026-08-10T20:00:00")
        self.assertEqual(tl["push"]["end"], "2026-08-10T20:20:00")

    def test_mutex_same_version_diff_branch_overlap(self):
        intervals = [
            {"label": "A", "start": datetime(2026, 8, 10, 22, 0), "end": datetime(2026, 8, 10, 22, 30)},
            {"label": "B", "start": datetime(2026, 8, 10, 22, 10), "end": datetime(2026, 8, 10, 22, 40)},
        ]
        hits = mutex.find_overlaps(intervals)
        self.assertEqual(len(hits), 1)

    def test_mutex_no_overlap(self):
        intervals = [
            {"label": "A", "start": datetime(2026, 8, 10, 22, 0), "end": datetime(2026, 8, 10, 22, 30)},
            {"label": "B", "start": datetime(2026, 8, 10, 23, 0), "end": datetime(2026, 8, 10, 23, 30)},
        ]
        self.assertEqual(mutex.find_overlaps(intervals), [])


class ConflictTests(TestCase):
    def test_stage_conflict_same_overlap(self):
        from types import SimpleNamespace
        tmpl = SimpleNamespace(smoke_minutes=120, analysis_minutes=60)
        cand = [{"build_start_time": "22:00", "template": tmpl, "push_mode": "sync", "strategy_name": "A"}]
        existing = [{"build_start_time": "22:10", "template": tmpl, "push_mode": "sync", "strategy_name": "B"}]
        hits = conflict.detect_conflicts("2026-08-10", cand, existing, 30, 20, 20)
        self.assertGreaterEqual(len(hits), 1)

    def test_stage_no_conflict(self):
        from types import SimpleNamespace
        tmpl = SimpleNamespace(smoke_minutes=120, analysis_minutes=60)
        cand = [{"build_start_time": "22:00", "template": tmpl, "push_mode": "sync", "strategy_name": "A"}]
        existing = [{"build_start_time": "12:00", "template": tmpl, "push_mode": "sync", "strategy_name": "B"}]
        hits = conflict.detect_conflicts("2026-08-10", cand, existing, 30, 20, 20)
        self.assertEqual(hits, [])