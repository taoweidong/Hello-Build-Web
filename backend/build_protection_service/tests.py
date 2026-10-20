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
    ExecutionRound,
    SecurityLog,
    SlotBooking,
    SlotTemplate,
    Strategy,
    StrategyTemplate,
    Version,
)
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

    def test_plan_returns_latest_round_conclusion(self):
        # 回归：status_map 相关子查询曾误用 OuterRef("pk")，导致 status 恒为空
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
        s = Strategy.objects.create(branch=self.b1, template=self.tmpl, name="s1",
                                    build_start_time="22:00", push_mode="normal", created_by=self.pm)
        ExecutionRound.objects.create(strategy=s, exec_date="2026-08-09", conclusion="fail")
        ExecutionRound.objects.create(strategy=s, exec_date="2026-08-10", conclusion="pass")
        resp = self.client.get("/api/plan", {"date": "2026-08-10"})
        st = resp.json()["data"][0]["branches"][0]["strategies"][0]
        self.assertEqual(st["status"], "pass")  # 取最近 exec_date 的结论


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
        # 重复运行不报错、不重复
        self.assertEqual(Version.objects.count(), 3)
        self.assertEqual(Branch.objects.count(), 9)
        self.assertEqual(Strategy.objects.count(), 23)
        self.assertEqual(SlotTemplate.objects.count(), 4)
        # 测量点修正（R3-B8）：首跑后立即取样，第二/第三跑均立即比对——
        # 旧测量点在第二跑之后才取样，恰好测不到"released 行第二跑被复活为
        # reserved"的 1→2 增量（2026-10-13 评估 B-P2-5）。
        booking_count = SlotBooking.objects.count()
        released_count = SlotBooking.objects.filter(status="released").count()
        self.assertGreater(booking_count, 0)
        call_command("seed")
        self.assertEqual(SlotBooking.objects.count(), booking_count)
        # released 历史样例不被复活为 reserved
        self.assertEqual(SlotBooking.objects.filter(status="released").count(), released_count)
        call_command("seed")
        self.assertEqual(SlotBooking.objects.count(), booking_count)
        self.assertEqual(SlotBooking.objects.filter(status="released").count(), released_count)



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


