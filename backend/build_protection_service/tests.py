import unittest
from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Branch, ExecutionRound, Strategy, StrategyTemplate, Version
from .services import config as svc_config
from .services import conflict, mutex, timeline

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
        self.assertEqual(Version.objects.count(), 2)
        self.assertEqual(Branch.objects.count(), 3)
        self.assertEqual(StrategyTemplate.objects.count(), 2)
        self.assertEqual(Strategy.objects.count(), 4)
        self.assertEqual(
            set(Strategy.objects.values_list("name", flat=True)),
            {
                "27A-master-晚间全量",
                "27A-master-午间快速",
                "27A-TR5-晚间全量",
                "27B-master-晚间全量",
            },
        )

    def test_seed_idempotent_when_run_twice(self):
        User.objects.all().delete()
        call_command("seed")
        call_command("seed")
        # 重复运行不报错、不重复
        self.assertEqual(Version.objects.count(), 2)
        self.assertEqual(Strategy.objects.count(), 4)


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
            "version_id": self.version.id,
            "strategy_id": self.strategy.id,
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
        self.assertEqual(data["created_by_id"], self.tester.id)
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
        resp = self.client.post("/api/reports", self._valid(strategy_id=None), format="json")
        self.assertEqual(resp.status_code, 422)
        # 只选策略不选版本
        resp = self.client.post("/api/reports", self._valid(version_id=None), format="json")
        self.assertEqual(resp.status_code, 422)
        # 策略不属于所选版本
        pm27b = User.objects.create_user(username="pm27b", password="123456", role="pm")
        v2 = Version.objects.create(name="27B", pm_user=pm27b, status="active")
        b2 = Branch.objects.create(version=v2, name="master")
        s2 = Strategy.objects.create(branch=b2, template=self.tmpl, name="27B-master-晚间",
                                     build_start_time="23:00", push_mode="normal", created_by=self.pm)
        resp = self.client.post("/api/reports", self._valid(strategy_id=s2.id), format="json")
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
        # status / version_id / 未命中
        resp = self.client.get("/api/reports", {"status": "draft"})
        self.assertEqual(len(resp.json()["data"]), 2)
        resp = self.client.get("/api/reports", {"version_id": self.version.id})
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

    def test_published_cannot_republish_or_edit(self):
        self._auth(self.token)
        r = self.client.post("/api/reports", self._valid(), format="json").json()["data"]
        img = "data:image/png;base64,AAAA"
        self.client.post(f"/api/reports/{r['id']}/publish", {"screenshot": img}, format="json")
        # 已发布重发被拒，发布次数保持 1
        resp = self.client.post(f"/api/reports/{r['id']}/publish", {"screenshot": img}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        self.assertIn("不可重复发布", resp.json()["message"])
        # 已发布修改被拒
        resp = self.client.put(f"/api/reports/{r['id']}", self._valid(title="发布后篡改"), format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], 40301)
        self.assertIn("先废弃后重新发布", resp.json()["message"])
        self.assertEqual(self.client.get(f"/api/reports/{r['id']}").json()["data"]["publish_count"], 1)

    def test_deprecate_flow(self):
        self._auth(self.token)
        r = self.client.post("/api/reports", self._valid(), format="json").json()["data"]
        img = "data:image/png;base64,AAAA"
        self.client.post(f"/api/reports/{r['id']}/publish", {"screenshot": img}, format="json")
        # 草稿态不可废弃
        r2 = self.client.post("/api/reports", self._valid(title="草稿报告"), format="json").json()["data"]
        resp = self.client.post(f"/api/reports/{r2['id']}/deprecate", {"reason": "误操作"}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertIn("仅已发布报告可废弃", resp.json()["message"])
        # 缺原因被拒
        resp = self.client.post(f"/api/reports/{r['id']}/deprecate", {}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertIn("废弃原因不能为空", resp.json()["message"])
        # 非作者废弃被拒
        self._auth(self._login("builder1"))
        resp = self.client.post(f"/api/reports/{r['id']}/deprecate", {"reason": "非作者废弃"}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], 40301)
        # 作者废弃成功
        self._auth(self.token)
        resp = self.client.post(f"/api/reports/{r['id']}/deprecate", {"reason": "结论填写有误"}, format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["status"], "deprecated")
        self.assertIsNotNone(data["deprecated_at"])
        self.assertEqual(data["deprecated_reason"], "结论填写有误")
        # 废弃后不可重复废弃
        resp = self.client.post(f"/api/reports/{r['id']}/deprecate", {"reason": "重复废弃"}, format="json")
        self.assertEqual(resp.status_code, 422)

    def test_deprecated_unlock_then_republish(self):
        self._auth(self.token)
        r = self.client.post("/api/reports", self._valid(), format="json").json()["data"]
        img = "data:image/png;base64,AAAA"
        self.client.post(f"/api/reports/{r['id']}/publish", {"screenshot": img}, format="json")
        self.client.post(f"/api/reports/{r['id']}/deprecate", {"reason": "发布有误"}, format="json")
        # 废弃后编辑解锁：回到草稿态，废弃标记保留追溯
        resp = self.client.put(f"/api/reports/{r['id']}", self._valid(title="修正后标题"), format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["status"], "draft")
        self.assertEqual(data["title"], "修正后标题")
        self.assertIsNotNone(data["deprecated_at"])
        self.assertEqual(data["deprecated_reason"], "发布有误")
        # 重新发布成功，累计发布 2 次
        resp = self.client.post(f"/api/reports/{r['id']}/publish", {"screenshot": img}, format="json")
        self.assertEqual(resp.status_code, 200)
        rep = resp.json()["data"]
        self.assertEqual(rep["status"], "published")
        self.assertEqual(rep["publish_count"], 2)

    def test_reports_requires_auth(self):
        resp = self.client.get("/api/reports")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], 40100)