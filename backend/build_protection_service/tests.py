import unittest
from datetime import datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

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


class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")

    def test_login_returns_token_and_user(self):
        resp = self.client.post("/api/auth/login", {"username": "pm1", "password": "123456"}, format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json().get("data", {})
        self.assertIn("token", data)
        self.assertEqual(data["user"]["role"], "pm")

    def test_login_wrong_password_401(self):
        resp = self.client.post("/api/auth/login", {"username": "pm1", "password": "wrong"}, format="json")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], 40101)

    def test_me_with_token_returns_payload(self):
        token = self._login("pm1")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = self.client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 200)
        data = resp.json().get("data", {})
        self.assertEqual(data["username"], "pm1")
        self.assertEqual(data["role"], "pm")

    def test_me_with_invalid_token_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not.a.token")
        resp = self.client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], 40100)

    def test_me_requires_auth(self):
        resp = self.client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], 40100)

    @unittest.skip("Task 9 实现 /api/admin/users 后启用")
    def test_pm_cannot_access_admin_only(self):
        token = self._login("pm1")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = self.client.get("/api/admin/users")
        self.assertEqual(resp.status_code, 403)

    def _login(self, username):
        resp = self.client.post("/api/auth/login", {"username": username, "password": "123456"}, format="json")
        return resp.json()["data"]["token"]


class StrategyApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.b1 = Branch.objects.create(version=self.version, name="master")
        self.b2 = Branch.objects.create(version=self.version, name="TR5")
        self.tmpl = StrategyTemplate.objects.create(name="晚间全量冒烟", smoke_minutes=480, analysis_minutes=120)
        self.token = self._login("pm1")

    def _login(self, username):
        resp = self.client.post("/api/auth/login", {"username": username, "password": "123456"}, format="json")
        return resp.json()["data"]["token"]

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_create_strategy_with_push_start_time(self):
        self._auth(self.token)
        resp = self.client.post("/api/strategies", {
            "branch_id": self.b1.id, "template_id": self.tmpl.id,
            "name": "27A-master-晚间", "build_start_time": "22:00",
            "push_start_time": "20:00", "push_mode": "normal", "enabled": True,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["code"], 0)
        self.assertEqual(resp.json()["data"]["push_start_time"], "20:00")

    def test_mutex_conflict_40902(self):
        Strategy.objects.create(
            branch=self.b1, template=self.tmpl, name="existing",
            build_start_time="22:00", push_mode="normal", created_by=self.pm,
        )
        self._auth(self.token)
        resp = self.client.post("/api/strategies", {
            "branch_id": self.b2.id, "template_id": self.tmpl.id,
            "name": "new", "build_start_time": "22:10",
            "push_mode": "normal", "enabled": True,
        }, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)

    def test_stage_conflict_40901(self):
        self._auth(self.token)
        self.client.post("/api/strategies", {
            "branch_id": self.b1.id, "template_id": self.tmpl.id,
            "name": "A", "build_start_time": "22:00", "push_mode": "normal", "enabled": True,
        }, format="json")
        resp = self.client.post("/api/strategies", {
            "branch_id": self.b1.id, "template_id": self.tmpl.id,
            "name": "B", "build_start_time": "22:30", "push_mode": "normal", "enabled": True,
        }, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40901)

    def test_admin_can_create_for_any_version(self):
        self._auth(self._login("admin"))
        resp = self.client.post("/api/strategies", {
            "branch_id": self.b1.id, "template_id": self.tmpl.id,
            "name": "admin-new", "build_start_time": "23:00", "push_mode": "normal", "enabled": True,
        }, format="json")
        self.assertEqual(resp.status_code, 200)

    def test_get_strategies_includes_push_start_time(self):
        self._auth(self.token)
        Strategy.objects.create(
            branch=self.b1, template=self.tmpl, name="s1", build_start_time="22:00",
            push_start_time="20:00", push_mode="normal", created_by=self.pm,
        )
        resp = self.client.get("/api/strategies", {"version_id": self.version.id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"][0]["push_start_time"], "20:00")

    def test_delete_strategy(self):
        self._auth(self.token)
        s = Strategy.objects.create(
            branch=self.b1, template=self.tmpl, name="del", build_start_time="23:00",
            push_mode="normal", created_by=self.pm,
        )
        resp = self.client.delete(f"/api/strategies/{s.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Strategy.objects.filter(id=s.id).exists())

    def test_create_without_build_start_time_defaults_to_2200(self):
        # 客户端省略 build_start_time 应回落 22:00 而非抛 500
        self._auth(self.token)
        resp = self.client.post("/api/strategies", {
            "branch_id": self.b1.id, "template_id": self.tmpl.id,
            "name": "default-2200", "push_mode": "normal", "enabled": True,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["code"], 0)
        self.assertEqual(resp.json()["data"]["build_start_time"], "22:00")

    def test_create_invalid_build_start_time_422(self):
        self._auth(self.token)
        resp = self.client.post("/api/strategies", {
            "branch_id": self.b1.id, "template_id": self.tmpl.id,
            "name": "bad-time", "build_start_time": "abc",
            "push_mode": "normal", "enabled": True,
        }, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_create_invalid_push_start_time_422(self):
        self._auth(self.token)
        resp = self.client.post("/api/strategies", {
            "branch_id": self.b1.id, "template_id": self.tmpl.id,
            "name": "bad-push", "build_start_time": "22:00",
            "push_start_time": "not-a-time", "push_mode": "normal", "enabled": True,
        }, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_preview_rejects_non_post(self):
        self._auth(self.token)
        resp = self.client.get("/api/strategies/preview")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)


class PlanApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.b1 = Branch.objects.create(version=self.version, name="master")
        self.tmpl = StrategyTemplate.objects.create(
            name="晚间全量冒烟", smoke_minutes=480, analysis_minutes=120
        )
        self.token = self._login("pm1")

    def _login(self, username):
        resp = self.client.post(
            "/api/auth/login", {"username": username, "password": "123456"}, format="json"
        )
        return resp.json()["data"]["token"]

    def test_plan_returns_push_start_time_and_timeline(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
        Strategy.objects.create(
            branch=self.b1, template=self.tmpl, name="s1", build_start_time="22:00",
            push_start_time="20:00", push_mode="normal", created_by=self.pm,
        )
        resp = self.client.get("/api/plan", {"date": "2026-08-10"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        ver = next(v for v in data if v["version_id"] == self.version.id)
        br = ver["branches"][0]
        st = br["strategies"][0]
        self.assertEqual(st["push_start_time"], "20:00")
        self.assertIsNotNone(st["timeline"]["push"])
        self.assertEqual(st["timeline"]["build"]["start"], "2026-08-10T22:00:00")


class WeeklyApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.b1 = Branch.objects.create(version=self.version, name="master")
        self.b2 = Branch.objects.create(version=self.version, name="TR5")
        self.tmpl = StrategyTemplate.objects.create(name="晚间全量冒烟", smoke_minutes=480, analysis_minutes=120)
        self.token = self._login()

    def _login(self):
        resp = self.client.post("/api/auth/login", {"username": "pm1", "password": "123456"}, format="json")
        return resp.json()["data"]["token"]

    def test_weekly_returns_week_info_and_days(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
        Strategy.objects.create(
            branch=self.b1, template=self.tmpl, name="27A-master-晚间",
            build_start_time="22:00", push_mode="normal", created_by=self.pm,
        )
        Strategy.objects.create(
            branch=self.b2, template=self.tmpl, name="27A-TR5-晚间",
            build_start_time="23:00", push_mode="normal", created_by=self.pm,
        )
        resp = self.client.get("/api/weekly", {"week_start": "2026-08-10", "version_id": self.version.id})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data["days"]), 7)
        self.assertEqual(data["days"][0]["date"], "2026-08-10")
        self.assertGreaterEqual(len(data["branches"]), 2)
        self.assertGreaterEqual(len(data["strategies"]), 2)

    def test_weekly_invalid_week_start_422(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
        resp = self.client.get("/api/weekly", {"week_start": "2026/08/10", "version_id": self.version.id})
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)