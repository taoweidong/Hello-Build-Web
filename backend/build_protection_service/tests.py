import unittest
from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    Branch,
    BranchProject,
    ExecutionLog,
    ExecutionRound,
    Instance,
    Project,
    RuntimeConfig,
    SecurityLog,
    SlotBooking,
    SlotTemplate,
    Strategy,
    StrategyTemplate,
    Version,
)
from .services import config as svc_config
from .services import conflict, mutex, timeline
from .services.branch_config import start_instance as svc_start, stop_instance as svc_stop

User = get_user_model()


class ConfigAwareTestCase(TestCase):
    """共享基类：重置运行期配置覆盖层，避免残留值污染其他用例。"""

    def setUp(self):
        svc_config.reset_config()


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

    def test_login_payload_contains_bound_version_for_pm(self):
        """PM 登录载荷必须携带绑定版本 id/name（反向 OneToOne 无自动 *_id 属性，回归防护）。"""
        version = Version.objects.create(name="28A", pm_user=self.pm, status="active")
        resp = self.client.post("/api/auth/login", {"username": "pm1", "password": "123456"}, format="json")
        self.assertEqual(resp.status_code, 200)
        user = resp.json()["data"]["user"]
        self.assertEqual(user["bound_version_id"], version.id)
        self.assertEqual(user["bound_version_name"], "28A")

    def test_login_payload_bound_version_none_for_admin(self):
        resp = self.client.post("/api/auth/login", {"username": "admin", "password": "123456"}, format="json")
        self.assertEqual(resp.status_code, 200)
        user = resp.json()["data"]["user"]
        self.assertIsNone(user["bound_version_id"])

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


class StrategyApiTests(ConfigAwareTestCase):
    def setUp(self):
        super().setUp()
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

    def test_create_out_of_range_time_422(self):
        # 回归：曾放行 "99:99" 导致服务层抛 ValueError 500
        self._auth(self.token)
        for bad in ("99:99", "24:00", "22:75", "7:00"):
            resp = self.client.post("/api/strategies", {
                "branch_id": self.b1.id, "template_id": self.tmpl.id,
                "name": f"bad-{bad}", "build_start_time": bad,
                "push_mode": "normal", "enabled": True,
            }, format="json")
            self.assertEqual(resp.status_code, 422, msg=bad)
            self.assertEqual(resp.json()["code"], 42201, msg=bad)


class PlanApiTests(ConfigAwareTestCase):
    def setUp(self):
        super().setUp()
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

    def test_plan_default_date_is_today(self):
        # 回归：曾默认魔法日期 "2026-08-10"，现在应为当天
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
        Strategy.objects.create(
            branch=self.b1, template=self.tmpl, name="s1", build_start_time="22:00",
            push_mode="normal", created_by=self.pm,
        )
        resp = self.client.get("/api/plan")
        self.assertEqual(resp.status_code, 200)
        st = resp.json()["data"][0]["branches"][0]["strategies"][0]
        today = timezone.localdate().strftime("%Y-%m-%d")
        self.assertEqual(st["timeline"]["build"]["start"], f"{today}T22:00:00")

    def test_plan_marks_conflicting_strategies(self):
        # 阶段重叠的策略应双双向标红（数据经 ORM 直建绕过 API 层 40901 拦截）
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
        Strategy.objects.create(branch=self.b1, template=self.tmpl, name="A",
                                build_start_time="22:00", push_mode="normal", created_by=self.pm)
        Strategy.objects.create(branch=self.b1, template=self.tmpl, name="B",
                                build_start_time="22:30", push_mode="normal", created_by=self.pm)
        resp = self.client.get("/api/plan", {"date": "2026-08-10"})
        by_name = {s["name"]: s for s in resp.json()["data"][0]["branches"][0]["strategies"]}
        self.assertTrue(by_name["A"]["conflict"])
        self.assertTrue(by_name["B"]["conflict"])

    def test_plan_no_conflict_marks_false(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
        Strategy.objects.create(branch=self.b1, template=self.tmpl, name="早班",
                                build_start_time="08:00", push_mode="normal", created_by=self.pm)
        Strategy.objects.create(branch=self.b1, template=self.tmpl, name="晚班",
                                build_start_time="22:00", push_mode="normal", created_by=self.pm)
        resp = self.client.get("/api/plan", {"date": "2026-08-10"})
        for s in resp.json()["data"][0]["branches"][0]["strategies"]:
            self.assertFalse(s["conflict"], msg=s["name"])


class WeeklyApiTests(ConfigAwareTestCase):
    def setUp(self):
        super().setUp()
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


class AdminApiTests(ConfigAwareTestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.token = self._login("admin")

    def _login(self, username):
        resp = self.client.post("/api/auth/login", {"username": username, "password": "123456"}, format="json")
        return resp.json()["data"]["token"]

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_create_version_and_branch(self):
        self._auth(self.token)
        resp = self.client.post("/api/admin/versions", {"name": "28A", "pm_user_id": self.pm.id, "status": "active"}, format="json")
        self.assertEqual(resp.status_code, 200)
        vid = resp.json()["data"]["id"]
        resp2 = self.client.post(f"/api/admin/versions/{vid}/branches", {"name": "master"}, format="json")
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()["data"]["name"], "master")

    def test_pm_cannot_access_admin_user_list(self):
        self._auth(self._login("pm1"))
        resp = self.client.get("/api/admin/users")
        self.assertEqual(resp.status_code, 403)

    def test_admin_config_update(self):
        self._auth(self.token)
        resp = self.client.put("/api/admin/config", {"build_minutes": 45}, format="json")
        self.assertEqual(resp.status_code, 200)

    def test_admin_strategy_crud(self):
        # 管理员创建/查询/启停/更新/删除策略，且拒绝非 admin
        self._auth(self.token)
        v = Version.objects.create(name="29A", pm_user=self.pm, status="active")
        b = Branch.objects.create(version=v, name="master")
        t = StrategyTemplate.objects.create(name="晚间全量", smoke_minutes=480, analysis_minutes=120)
        # 非 admin 禁止访问
        self._auth(self._login("pm1"))
        resp = self.client.get("/api/admin/strategies")
        self.assertEqual(resp.status_code, 403)
        # admin 创建
        self._auth(self.token)
        resp = self.client.post("/api/admin/strategies", {
            "branch_id": b.id, "template_id": t.id, "name": "29A-master-晚间",
            "build_start_time": "22:00", "push_start_time": "20:00",
            "push_mode": "normal", "enabled": False,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        sid = resp.json()["data"]["id"]
        self.assertEqual(resp.json()["data"]["push_start_time"], "20:00")
        # 列表
        resp = self.client.get("/api/admin/strategies", {"version_id": v.id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["data"]), 1)
        # 启停：无参数 toggle 为翻转语义（enabled=False -> True -> False）
        resp = self.client.patch(f"/api/admin/strategies/{sid}/toggle")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["data"]["enabled"])
        resp = self.client.patch(f"/api/admin/strategies/{sid}/toggle")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["data"]["enabled"])
        # 更新
        resp = self.client.patch(f"/api/admin/strategies/{sid}", {"name": "renamed"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["name"], "renamed")
        # 删除
        resp = self.client.delete(f"/api/admin/strategies/{sid}")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Strategy.objects.filter(id=sid).exists())


class ExecutionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.tester = User.objects.create_user(username="tester", password="123456", role="tester")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.b1 = Branch.objects.create(version=self.version, name="master")
        self.tmpl = StrategyTemplate.objects.create(name="t", smoke_minutes=480, analysis_minutes=120)
        self.s = Strategy.objects.create(branch=self.b1, template=self.tmpl, name="s1",
                                         build_start_time="22:00", push_mode="normal", created_by=self.pm)
        self.round = ExecutionRound.objects.create(strategy=self.s, exec_date="2026-08-10")

    def _login(self, username):
        resp = self.client.post("/api/auth/login", {"username": username, "password": "123456"}, format="json")
        return resp.json()["data"]["token"]

    def test_executions_list(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._login('pm1')}")
        resp = self.client.get("/api/executions")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()["data"]), 1)

    def test_tester_submits_conclusion(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._login('tester')}")
        resp = self.client.post(f"/api/executions/rounds/{self.round.id}/conclusion",
                                {"conclusion": "pass", "note": "ok"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.round.refresh_from_db()
        self.assertEqual(self.round.conclusion, "pass")

    def test_logs_execution(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._login('pm1')}")
        resp = self.client.get("/api/logs/execution")
        self.assertEqual(resp.status_code, 200)


class SeedTests(TestCase):
    def test_seed_creates_admin_and_demo_data(self):
        User.objects.all().delete()
        call_command("seed")
        self.assertTrue(User.objects.filter(username="admin", role="admin").exists())
        # 精确断言演示数据规模，seed 变更时能暴露差异
        self.assertEqual(Version.objects.filter(name="27A").count(), 1)
        self.assertEqual(Version.objects.count(), 3)
        # 三个版本各 3 条分支（27A/27B/26B），保证版本策略全景页各版本数据饱满
        self.assertEqual(Branch.objects.count(), 9)
        self.assertEqual(StrategyTemplate.objects.count(), 3)
        self.assertEqual(SlotTemplate.objects.count(), 4)
        self.assertEqual(Strategy.objects.count(), 23)
        self.assertEqual(
            set(Strategy.objects.values_list("name", flat=True)),
            {
                "27A-master-晚间全量",
                "27A-master-午间快速",
                "27A-TR5-晚间全量",
                "27B-master-晚间全量",
                "27A-master-早间回归",
                "27A-TR5-午间快速",
                "27A-TR5-夜间补测",
                "27A-TR6-午间快速",
                "27A-TR6-同步推送验证",
                "27A-TR6-晚间全量",
                "27B-master-早间快速",
                "27B-master-午间快速",
                "27B-TR5-午间快速",
                "27B-TR5-晚间全量",
                "27B-TR6-同步推送验证",
                "27B-TR6-晚间全量",
                "26B-master-晚间全量",
                "26B-master-同步推送",
                "26B-master-早间回归",
                "26B-TR5-午间快速",
                "26B-TR5-夜间补测",
                "26B-TR5-晚间全量",
                "26B-TR6-午间快速",
            },
        )

    def test_seed_idempotent_when_run_twice(self):
        User.objects.all().delete()
        call_command("seed")
        call_command("seed")
        # 重复运行不报错、不重复
        self.assertEqual(Version.objects.count(), 3)
        self.assertEqual(Branch.objects.count(), 9)
        self.assertEqual(Strategy.objects.count(), 23)
        self.assertEqual(SlotTemplate.objects.count(), 4)
        booking_count = SlotBooking.objects.count()
        self.assertGreater(booking_count, 0)
        call_command("seed")
        self.assertEqual(SlotBooking.objects.count(), booking_count)


class ReportApiTests(ConfigAwareTestCase):
    """验证报告 API：tester/builder 可写，仅作者可改/发，发布为模拟推送。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        self.tester = User.objects.create_user(username="tester1", password="123456", role="tester")
        self.tester2 = User.objects.create_user(username="tester2", password="123456", role="tester")
        self.builder = User.objects.create_user(username="builder1", password="123456", role="builder")
        self.integrator = User.objects.create_user(username="intg1", password="123456", role="integrator")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")
        self.tmpl = StrategyTemplate.objects.create(name="晚间全量冒烟", smoke_minutes=480, analysis_minutes=120)
        self.strategy = Strategy.objects.create(
            branch=self.branch, template=self.tmpl, name="27A-master-晚间",
            build_start_time="22:00", push_mode="normal", created_by=self.pm,
        )
        self.token = self._login("tester1")

    def _login(self, username):
        resp = self.client.post("/api/auth/login", {"username": username, "password": "123456"}, format="json")
        return resp.json()["data"]["token"]

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def _valid(self, **overrides):
        payload = {
            "title": "27A 冒烟验证报告",
            "version_name": "27A",
            "strategy_name": "27A-master-晚间",
            "conclusion": "pass",
            "environment": "测试环境",
            "summary": "冒烟用例全部通过，无阻塞问题。",
            "risks": "",
            "remark": "",
        }
        payload.update(overrides)
        return payload

    def test_writer_roles_can_create_report(self):
        # tester 与 builder 均可新建（草稿态）
        self._auth(self.token)
        resp = self.client.post("/api/reports", self._valid(), format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["status"], "draft")
        self.assertEqual(data["conclusion"], "pass")
        self.assertEqual(data["version_name"], "27A")
        self.assertEqual(data["strategy_name"], "27A-master-晚间")
        self.assertEqual(data["created_by_username"], "tester1")
        self._auth(self._login("builder1"))
        resp = self.client.post("/api/reports", self._valid(title="builder 报告"), format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["title"], "builder 报告")

    def test_non_writer_cannot_create_report(self):
        for username in ("pm1", "admin", "intg1"):
            self._auth(self._login(username))
            resp = self.client.post("/api/reports", self._valid(), format="json")
            self.assertEqual(resp.status_code, 403)
            self.assertEqual(resp.json()["code"], 40301)

    def test_create_validation_422(self):
        self._auth(self.token)
        cases = [
            (self._valid(title=""), "标题不能为空"),
            (self._valid(conclusion=""), "结论必须为"),
            (self._valid(conclusion="blocker"), "结论必须为"),
            (self._valid(summary=""), "验证内容不能为空"),
        ]
        for payload, expect in cases:
            resp = self.client.post("/api/reports", payload, format="json")
            self.assertEqual(resp.status_code, 422)
            self.assertEqual(resp.json()["code"], 42201)
            self.assertIn(expect, resp.json()["message"])

    def test_version_strategy_must_be_paired(self):
        self._auth(self.token)
        # 只选版本不选策略
        resp = self.client.post("/api/reports", self._valid(strategy_name=""), format="json")
        self.assertEqual(resp.status_code, 422)
        # 只选策略不选版本
        resp = self.client.post("/api/reports", self._valid(version_name=""), format="json")
        self.assertEqual(resp.status_code, 422)
        # 策略不属于所选版本（27B 的策略配 27A 的版本）
        pm27b = User.objects.create_user(username="pm27b", password="123456", role="pm")
        v2 = Version.objects.create(name="27B", pm_user=pm27b, status="active")
        b2 = Branch.objects.create(version=v2, name="master")
        Strategy.objects.create(branch=b2, template=self.tmpl, name="27B-master-晚间",
                                build_start_time="23:00", push_mode="normal", created_by=self.pm)
        resp = self.client.post("/api/reports", self._valid(strategy_name="27B-master-晚间"), format="json")
        self.assertEqual(resp.status_code, 422)

    def test_list_and_detail(self):
        self._auth(self.token)
        r1 = self.client.post("/api/reports", self._valid(), format="json").json()["data"]
        self.client.post("/api/reports", self._valid(title="第二份", conclusion="risk"), format="json")
        resp = self.client.get("/api/reports")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["data"]), 2)
        resp = self.client.get(f"/api/reports/{r1['id']}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["title"], "27A 冒烟验证报告")

    def test_list_filters(self):
        self._auth(self.token)
        r = self.client.post("/api/reports", self._valid(), format="json").json()["data"]
        self.client.post("/api/reports", self._valid(title="27B 回归报告", conclusion="fail"), format="json")
        # keyword 命中标题
        resp = self.client.get("/api/reports", {"keyword": "27B"})
        self.assertEqual(len(resp.json()["data"]), 1)
        self.assertEqual(resp.json()["data"][0]["title"], "27B 回归报告")
        # keyword 命中 ID（字符串）
        resp = self.client.get("/api/reports", {"keyword": str(r["id"])})
        self.assertEqual(len(resp.json()["data"]), 1)
        # status / version_name / 未命中
        resp = self.client.get("/api/reports", {"status": "draft"})
        self.assertEqual(len(resp.json()["data"]), 2)
        resp = self.client.get("/api/reports", {"version_name": "27A"})
        self.assertEqual(len(resp.json()["data"]), 2)
        resp = self.client.get("/api/reports", {"keyword": "不存在的关键词"})
        self.assertEqual(len(resp.json()["data"]), 0)

    def test_update_only_by_author(self):
        self._auth(self.token)
        r = self.client.post("/api/reports", self._valid(), format="json").json()["data"]
        # 非作者 tester2 修改被拒
        self._auth(self._login("tester2"))
        resp = self.client.put(f"/api/reports/{r['id']}", self._valid(title="篡改"), format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], 40301)
        # pm 修改被拒
        self._auth(self._login("pm1"))
        resp = self.client.put(f"/api/reports/{r['id']}", self._valid(title="pm 篡改"), format="json")
        self.assertEqual(resp.status_code, 403)
        # 作者修改成功
        self._auth(self.token)
        resp = self.client.put(f"/api/reports/{r['id']}", self._valid(title="修订后标题", conclusion="risk"), format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["title"], "修订后标题")
        self.assertEqual(data["conclusion"], "risk")
        self.assertEqual(data["status"], "draft")

    def test_detail_not_found_404(self):
        self._auth(self.token)
        resp = self.client.get("/api/reports/99999")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["code"], 40401)

    def test_publish_flow(self):
        self._auth(self.token)
        r = self.client.post("/api/reports", self._valid(), format="json").json()["data"]
        resp = self.client.post(
            f"/api/reports/{r['id']}/publish",
            {"screenshot": "data:image/png;base64," + "A" * 100},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["status"], "published")
        self.assertEqual(data["publish_count"], 1)
        self.assertIsNotNone(data["published_at"])
        # 报告状态已更新
        resp = self.client.get(f"/api/reports/{r['id']}")
        rep = resp.json()["data"]
        self.assertEqual(rep["status"], "published")
        self.assertEqual(rep["publish_count"], 1)
        self.assertIsNotNone(rep["published_at"])

    def test_publish_requires_author_and_screenshot(self):
        self._auth(self.token)
        r = self.client.post("/api/reports", self._valid(), format="json").json()["data"]
        # 非作者发布被拒
        self._auth(self._login("builder1"))
        resp = self.client.post(f"/api/reports/{r['id']}/publish", {"screenshot": "x"}, format="json")
        self.assertEqual(resp.status_code, 403)
        # pm 发布被拒
        self._auth(self._login("pm1"))
        resp = self.client.post(f"/api/reports/{r['id']}/publish", {"screenshot": "x"}, format="json")
        self.assertEqual(resp.status_code, 403)
        # 缺少截图
        self._auth(self.token)
        resp = self.client.post(f"/api/reports/{r['id']}/publish", {}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        # 截图超 2MB
        huge = "A" * (2 * 1024 * 1024 + 1)
        resp = self.client.post(f"/api/reports/{r['id']}/publish", {"screenshot": huge}, format="json")
        self.assertEqual(resp.status_code, 422)

    def test_published_editable_but_conclusion_locked(self):
        self._auth(self.token)
        r = self.client.post("/api/reports", self._valid(), format="json").json()["data"]
        img = "data:image/png;base64,AAAA"
        self.client.post(f"/api/reports/{r['id']}/publish", {"screenshot": img}, format="json")
        # 发布后仍可修改非结论字段
        resp = self.client.put(f"/api/reports/{r['id']}", self._valid(title="发布后修订"), format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["title"], "发布后修订")
        self.assertEqual(data["status"], "published")
        # 发布后修改最终结论被拒
        resp = self.client.put(f"/api/reports/{r['id']}", self._valid(conclusion="fail"), format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        self.assertIn("最终结论不可修改", resp.json()["message"])
        # 结论仍保持原值
        rep = self.client.get(f"/api/reports/{r['id']}").json()["data"]
        self.assertEqual(rep["conclusion"], "pass")
        self.assertEqual(rep["publish_count"], 1)

    def test_republish_marks_updated(self):
        self._auth(self.token)
        r = self.client.post("/api/reports", self._valid(), format="json").json()["data"]
        img = "data:image/png;base64,AAAA"
        # 首次发布：非更新报告
        resp = self.client.post(f"/api/reports/{r['id']}/publish", {"screenshot": img}, format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["publish_count"], 1)
        self.assertFalse(data["is_updated"])
        self.assertEqual(data["update_count"], 0)
        # 修改后重复发布：标记为更新报告，发布次数累计
        self.client.put(f"/api/reports/{r['id']}", self._valid(title="修正后标题"), format="json")
        resp = self.client.post(f"/api/reports/{r['id']}/publish", {"screenshot": img}, format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["status"], "published")
        self.assertEqual(data["publish_count"], 2)
        self.assertTrue(data["is_updated"])
        self.assertEqual(data["update_count"], 1)
        # 发布留痕两条：最近的为更新发布，最早的为发布报告
        logs = self.client.get(f"/api/reports/{r['id']}/revisions").json()["data"]
        pub_logs = [log for log in logs if log["action"] == "publish"]
        self.assertEqual(len(pub_logs), 2)
        self.assertEqual(pub_logs[0]["field_name"], "更新发布")
        self.assertEqual(pub_logs[1]["field_name"], "发布报告")

    def test_revision_logs_ordered_desc(self):
        self._auth(self.token)
        r = self.client.post("/api/reports", self._valid(), format="json").json()["data"]
        rid = r["id"]
        # 修改标题与验证内容 → 两条 update 留痕
        self.client.put(
            f"/api/reports/{rid}",
            self._valid(title="修正标题", summary="补充问题记录"),
            format="json",
        )
        self.client.post(
            f"/api/reports/{rid}/publish",
            {"screenshot": "data:image/png;base64,AAAA"},
            format="json",
        )
        resp = self.client.get(f"/api/reports/{rid}/revisions")
        self.assertEqual(resp.status_code, 200)
        logs = resp.json()["data"]
        # 时间倒序：最近的发布在最前，创建在最末
        self.assertEqual(logs[0]["action"], "publish")
        self.assertEqual(logs[0]["action_label"], "发布")
        self.assertEqual(logs[-1]["action"], "create")
        self.assertEqual(logs[-1]["field_name"], "创建报告")
        # 修改记录含字段/前后内容/操作人，按时间倒序
        update_logs = [log for log in logs if log["action"] == "update"]
        labels = [log["field_name"] for log in update_logs]
        self.assertEqual(labels[0], "验证内容")
        self.assertEqual(labels[1], "标题")
        title_log = next(log for log in update_logs if log["field_name"] == "标题")
        self.assertEqual(title_log["before_value"], "27A 冒烟验证报告")
        self.assertEqual(title_log["after_value"], "修正标题")
        self.assertEqual(title_log["operator_username"], "tester1")
        self.assertIsNotNone(title_log["created_at"])
        self.assertEqual(title_log["report_id"], rid)

    def test_reports_requires_auth(self):
        resp = self.client.get("/api/reports")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], 40100)

class AdminTemplateApiTests(ConfigAwareTestCase):
    """管理端模板 CRUD：GET 允许 admin+pm，写操作仅 admin；删除被引用模板拦截 40903。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")
        self.token = self._login("admin")

    def _login(self, username):
        resp = self.client.post("/api/auth/login", {"username": username, "password": "123456"}, format="json")
        return resp.json()["data"]["token"]

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_template_crud_flow(self):
        self._auth(self.token)
        resp = self.client.post("/api/admin/templates", {
            "name": "晚间全量", "smoke_minutes": 480, "analysis_minutes": 120, "description": "d",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        tid = resp.json()["data"]["id"]
        # pm 可读不可写
        self._auth(self._login("pm1"))
        resp = self.client.get("/api/admin/templates")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(t["id"] == tid for t in resp.json()["data"]))
        resp = self.client.post("/api/admin/templates", {"name": "pm-tpl"}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], 40301)
        # admin 更新
        self._auth(self.token)
        resp = self.client.patch(f"/api/admin/templates/{tid}", {"name": "改名", "smoke_minutes": 90}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["name"], "改名")
        self.assertEqual(resp.json()["data"]["smoke_minutes"], 90)
        # admin 删除（无引用）
        resp = self.client.delete(f"/api/admin/templates/{tid}")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(StrategyTemplate.objects.filter(id=tid).exists())

    def test_delete_referenced_template_40903(self):
        # 回归：曾误捕 IntegrityError，删除被 PROTECT 引用的模板实际抛 ProtectedError → 500
        self._auth(self.token)
        resp = self.client.post("/api/admin/templates", {"name": "被引用", "smoke_minutes": 60}, format="json")
        tid = resp.json()["data"]["id"]
        tmpl = StrategyTemplate.objects.get(id=tid)
        strategy = Strategy.objects.create(
            branch=self.branch, template=tmpl, name="s1",
            build_start_time="22:00", push_mode="normal", created_by=self.pm,
        )
        resp = self.client.delete(f"/api/admin/templates/{tid}")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40903)
        self.assertIn("正在被策略引用", resp.json()["message"])
        self.assertTrue(StrategyTemplate.objects.filter(id=tid).exists())
        # 解除引用后可正常删除
        strategy.delete()
        resp = self.client.delete(f"/api/admin/templates/{tid}")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(StrategyTemplate.objects.filter(id=tid).exists())

    def test_template_requires_auth(self):
        resp = self.client.get("/api/admin/templates")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], 40100)


class LogoutTests(TestCase):
    """登出拉黑：同 token 登出后立即失效，并记录带用户名的安全日志。"""

    def setUp(self):
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")

    def _login(self):
        resp = self.client.post("/api/auth/login", {"username": "pm1", "password": "123456"}, format="json")
        return resp.json()["data"]["token"]

    def test_logout_revokes_token(self):
        token = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        resp = self.client.post("/api/auth/logout")
        self.assertEqual(resp.status_code, 200)
        # 同一 token 登出后立即失效
        resp = self.client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], 40100)

    def test_logout_writes_security_log_with_username(self):
        # 回归：曾读 request.user（恒为 AnonymousUser）导致登出日志无用户名
        token = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.client.post("/api/auth/logout")
        log = SecurityLog.objects.filter(action="logout").latest("created_at")
        self.assertEqual(log.username, "pm1")

    def test_logout_without_token_still_ok(self):
        resp = self.client.post("/api/auth/logout")
        self.assertEqual(resp.status_code, 200)

    def test_logout_with_garbage_token_still_ok(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not.a.token")
        resp = self.client.post("/api/auth/logout")
        self.assertEqual(resp.status_code, 200)


class LoginRateLimitTests(TestCase):
    """登录防爆破：连续失败 5 次锁定 15 分钟（42901），成功登录清零。"""

    def setUp(self):
        self.client = APIClient()
        User.objects.create_user(username="rl_pm", password="123456", role="pm")
        cache.clear()

    def tearDown(self):
        # 失败计数存进程级 cache，用后清理避免污染其他用例
        cache.clear()

    def test_lockout_after_five_failures(self):
        for _ in range(5):
            resp = self.client.post("/api/auth/login", {"username": "rl_pm", "password": "bad"}, format="json")
            self.assertEqual(resp.status_code, 401)
        # 锁定后即使密码正确也拒绝
        resp = self.client.post("/api/auth/login", {"username": "rl_pm", "password": "123456"}, format="json")
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.json()["code"], 42901)
        self.assertTrue(SecurityLog.objects.filter(action="login_locked", username="rl_pm").exists())

    def test_success_resets_counter(self):
        for _ in range(4):
            self.client.post("/api/auth/login", {"username": "rl_pm", "password": "bad"}, format="json")
        resp = self.client.post("/api/auth/login", {"username": "rl_pm", "password": "123456"}, format="json")
        self.assertEqual(resp.status_code, 200)
        # 计数已清零：再失败一次不影响后续正常登录
        self.client.post("/api/auth/login", {"username": "rl_pm", "password": "bad"}, format="json")
        resp = self.client.post("/api/auth/login", {"username": "rl_pm", "password": "123456"}, format="json")
        self.assertEqual(resp.status_code, 200)

    def test_missing_fields_422(self):
        resp = self.client.post("/api/auth/login", {"username": ""}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)


class AdminVersionUserApiTests(ConfigAwareTestCase):
    """admin 版本 PUT / 用户 PATCH（含最后一个 admin 保护）与日志查询端点。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.pm2 = User.objects.create_user(username="pm2", password="123456", role="pm")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.token = self._login("admin")

    def _login(self, username):
        resp = self.client.post("/api/auth/login", {"username": username, "password": "123456"}, format="json")
        return resp.json()["data"]["token"]

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_update_version_rename_dup_40902(self):
        Version.objects.create(name="27B", pm_user=self.pm2, status="active")
        self._auth(self.token)
        resp = self.client.put(f"/api/admin/versions/{self.version.id}", {"name": "27B"}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)

    def test_update_version_status_and_pm(self):
        self._auth(self.token)
        resp = self.client.put(f"/api/admin/versions/{self.version.id}", {
            "status": "archived", "pm_user_id": self.pm2.id,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, "archived")
        self.assertEqual(self.version.pm_user_id, self.pm2.id)

    def test_update_version_invalid_status_422(self):
        self._auth(self.token)
        resp = self.client.put(f"/api/admin/versions/{self.version.id}", {"status": "bogus"}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_update_user_role_and_password(self):
        self._auth(self.token)
        resp = self.client.patch(f"/api/admin/users/{self.pm.id}", {
            "role": "tester", "password": "newpass123", "is_active": "false",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.pm.refresh_from_db()
        self.assertEqual(self.pm.role, "tester")
        self.assertFalse(self.pm.is_active)
        self.assertTrue(self.pm.check_password("newpass123"))
        # 停用账号登录被拒 403
        resp = self.client.post("/api/auth/login", {"username": "pm1", "password": "newpass123"}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], 40301)

    def test_last_admin_cannot_be_demoted_or_disabled(self):
        self._auth(self.token)
        resp = self.client.patch(f"/api/admin/users/{self.admin.id}", {"is_active": False}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)
        resp = self.client.patch(f"/api/admin/users/{self.admin.id}", {"role": "builder"}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertEqual(self.admin.role, "admin")

    def test_admin_logs_endpoints(self):
        self._auth(self.token)
        # 产生一条管理日志（更新配置）与一条安全日志（登录）
        self.client.put("/api/admin/config", {"build_minutes": 40}, format="json")
        resp = self.client.get("/api/admin/logs/operations")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(item["action"] == "update_config" for item in resp.json()["data"]))
        resp = self.client.get("/api/admin/logs/security")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(item["action"] == "login_success" for item in resp.json()["data"]))


class LogsEndpointsTests(ConfigAwareTestCase):
    """/api/logs/changes 与 /api/executions/rounds/<rid>。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")
        self.tmpl = StrategyTemplate.objects.create(name="t", smoke_minutes=60, analysis_minutes=30)
        self.strategy = Strategy.objects.create(
            branch=self.branch, template=self.tmpl, name="s1",
            build_start_time="22:00", push_mode="normal", created_by=self.pm)
        self.round = ExecutionRound.objects.create(strategy=self.strategy, exec_date="2026-08-10")

    def _login(self, username):
        resp = self.client.post("/api/auth/login", {"username": username, "password": "123456"}, format="json")
        return resp.json()["data"]["token"]

    def test_change_logs_after_strategy_update(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._login('pm1')}")
        resp = self.client.patch(f"/api/strategies/{self.strategy.id}", {
            "name": "改名", "build_start_time": "23:00",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/api/logs/changes")
        self.assertEqual(resp.status_code, 200)
        logs = resp.json()["data"]
        self.assertEqual(len(logs), 1)
        # 变更日志记录实际字段差异（策略名 + 构建开始时间）
        self.assertIn("策略名: s1→改名", logs[0]["change_desc"])
        self.assertIn("构建开始时间: 22:00→23:00", logs[0]["change_desc"])

    def test_round_detail(self):
        ExecutionLog.objects.create(round=self.round, stage="build", message="开始构建")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._login('pm1')}")
        resp = self.client.get(f"/api/executions/rounds/{self.round.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["round"]["id"], self.round.id)
        self.assertEqual(data["logs"][0]["message"], "开始构建")

    def test_round_detail_404(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._login('pm1')}")
        resp = self.client.get("/api/executions/rounds/99999")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["code"], 40401)


class PMStrategyPermissionTests(ConfigAwareTestCase):
    """PM 侧策略更新/启停权限：本版本可操作，跨版本 403。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.pm1 = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.pm2 = User.objects.create_user(username="pm2", password="123456", role="pm")
        self.v1 = Version.objects.create(name="27A", pm_user=self.pm1, status="active")
        self.v2 = Version.objects.create(name="27B", pm_user=self.pm2, status="active")
        self.b1 = Branch.objects.create(version=self.v1, name="master")
        self.b2 = Branch.objects.create(version=self.v2, name="master")
        self.tmpl = StrategyTemplate.objects.create(name="t", smoke_minutes=60, analysis_minutes=30)
        self.s1 = Strategy.objects.create(branch=self.b1, template=self.tmpl, name="s1",
                                          build_start_time="22:00", push_mode="normal", created_by=self.pm1)
        self.s2 = Strategy.objects.create(branch=self.b2, template=self.tmpl, name="s2",
                                          build_start_time="22:00", push_mode="normal", created_by=self.pm2)

    def _login(self, username):
        resp = self.client.post("/api/auth/login", {"username": username, "password": "123456"}, format="json")
        return resp.json()["data"]["token"]

    def test_pm_updates_own_strategy(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._login('pm1')}")
        resp = self.client.patch(f"/api/strategies/{self.s1.id}", {"name": "pm1改"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["name"], "pm1改")

    def test_pm_cannot_touch_other_version_strategy(self):
        token = self._login("pm1")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = self.client.patch(f"/api/strategies/{self.s2.id}", {"name": "越权"}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], 40301)
        resp = self.client.patch(f"/api/strategies/{self.s2.id}/toggle")
        self.assertEqual(resp.status_code, 403)

    def test_pm_toggle_own_strategy(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._login('pm1')}")
        resp = self.client.patch(f"/api/strategies/{self.s1.id}/toggle")
        self.assertEqual(resp.status_code, 200)
        self.s1.refresh_from_db()
        self.assertFalse(self.s1.enabled)


class MutexServiceTests(ConfigAwareTestCase):
    """services.mutex.check_build_mutex 直测（含 ds 参数化）。"""

    def setUp(self):
        super().setUp()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.b1 = Branch.objects.create(version=self.version, name="master")
        self.b2 = Branch.objects.create(version=self.version, name="TR5")
        self.tmpl = StrategyTemplate.objects.create(name="t", smoke_minutes=60, analysis_minutes=30)

    def test_mutex_hits_across_branches(self):
        Strategy.objects.create(branch=self.b1, template=self.tmpl, name="A",
                                build_start_time="22:00", push_mode="normal", created_by=self.pm)
        hits = mutex.check_build_mutex(self.version.id, "22:10", 30)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["strategy"], "master/A")

    def test_mutex_clear_when_no_overlap(self):
        Strategy.objects.create(branch=self.b1, template=self.tmpl, name="A",
                                build_start_time="22:00", push_mode="normal", created_by=self.pm)
        self.assertEqual(mutex.check_build_mutex(self.version.id, "23:00", 30), [])

    def test_mutex_exclude_self(self):
        s = Strategy.objects.create(branch=self.b1, template=self.tmpl, name="A",
                                    build_start_time="22:00", push_mode="normal", created_by=self.pm)
        self.assertEqual(
            mutex.check_build_mutex(self.version.id, "22:00", 30, exclude_strategy_id=s.id), [])


class InstanceConstraintTests(TestCase):
    """活跃实例部分唯一约束 + start_instance 并发兜底。"""

    def setUp(self):
        self.pm = User.objects.create_user(username="pm1", password="123456", role="admin")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")
        self.project = Project.objects.create(name="工程A")
        self.bp = BranchProject.objects.create(branch=self.branch, project=self.project)

    def test_second_active_instance_rejected_by_db(self):
        from django.utils import timezone as tz
        Instance.objects.create(branch_project=self.bp, status="RUNNING", started_at=tz.now())
        with self.assertRaises(IntegrityError):
            Instance.objects.create(branch_project=self.bp, status="STARTING", started_at=tz.now())

    def test_start_returns_none_when_active_exists(self):
        from django.utils import timezone as tz
        Instance.objects.create(branch_project=self.bp, status="RUNNING", started_at=tz.now())
        self.assertIsNone(svc_start(self.bp, "pm1"))

    def test_start_after_stop_creates_new(self):
        inst = svc_start(self.bp, "pm1")
        self.assertIsNotNone(inst)
        svc_stop(self.bp, "pm1")
        inst2 = svc_start(self.bp, "pm1")
        self.assertIsNotNone(inst2)
        self.assertNotEqual(inst.id, inst2.id)


class RuntimeConfigPersistenceTests(TestCase):
    """运行期配置落库：set_config 持久化，缓存重置后仍可读回。"""

    def tearDown(self):
        svc_config.reset_config()
        RuntimeConfig.objects.all().delete()

    def test_set_config_persists(self):
        svc_config.set_config("build_minutes", 77)
        self.assertTrue(RuntimeConfig.objects.filter(key="build_minutes", value=77).exists())
        # 重置进程缓存后仍能从库读回（模拟重启后首次读取）
        svc_config.reset_config()
        self.assertEqual(svc_config.get_config("build_minutes", 30), 77)

    def test_get_config_falls_back_to_default(self):
        self.assertEqual(svc_config.get_config("nonexistent_key", 42), 42)


class SlotTemplateWeekdaysTests(ConfigAwareTestCase):
    """时段模板 weekdays 校验：非法值 422，合法值归一化。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        token = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def _login(self):
        resp = self.client.post("/api/auth/login", {"username": "admin", "password": "123456"}, format="json")
        return resp.json()["data"]["token"]

    def test_invalid_weekdays_422(self):
        for bad in ("8", "abc", "0,9", "1,x"):
            resp = self.client.post("/api/slot-templates", {
                "name": f"模板-{bad}", "start_time": "09:00", "end_time": "12:00",
                "weekdays": bad,
            }, format="json")
            self.assertEqual(resp.status_code, 422, msg=bad)
            self.assertEqual(resp.json()["code"], 42201, msg=bad)

    def test_valid_weekdays_normalized(self):
        resp = self.client.post("/api/slot-templates", {
            "name": "工作日时段", "start_time": "09:00", "end_time": "12:00",
            "weekdays": "1, 3",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["template"]["weekdays"], "1,3")
