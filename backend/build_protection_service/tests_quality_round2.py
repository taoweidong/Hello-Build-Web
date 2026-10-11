"""第二轮全库质量优化（2026-10-12）回归测试。

对应 docs/code-quality-assessment-2026-10-12.md 与
docs/superpowers/specs/2026-10-12-code-quality-optimization-round2-design.md：
每个修复项一组锁定测试，防止同类问题复发。
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from .models import (
    AdminOpLog, BorrowFlow, Branch, BranchProject, ExecutionRound, Project,
    SlotTemplate, Strategy, StrategyTemplate, Version,
)
from .services.report_service import ReportService
from .services.slot_booking import template_applies_on
from .tests import ConfigAwareTestCase

User = get_user_model()


def _next_isoweekday(from_d: date, iso: int) -> date:
    """从 from_d 起（含当天）找下一个 isoweekday==iso 的日期。"""
    d = from_d
    while d.isoweekday() != iso:
        d += timedelta(days=1)
    return d


class WeekdayConventionTests(ConfigAwareTestCase):
    """B-P0-1：weekdays 全链路统一 isoweekday 1-7（1=周一…7=周日）。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        resp = self.client.post(
            "/api/auth/login", {"username": "admin", "password": "123456"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")

    def test_ui_sunday_template_end_to_end(self):
        """UI 口径周日（值 7）：API 可建模板，且服务层在真实周日命中、周一不命中。"""
        resp = self.client.post("/api/slot-templates", {
            "name": "周日维护窗口", "start_time": "09:00", "end_time": "12:00",
            "weekdays": "7",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        tpl = SlotTemplate.objects.get(name="周日维护窗口")
        sunday = _next_isoweekday(date.today(), 7)
        self.assertTrue(template_applies_on(tpl, sunday))
        self.assertFalse(template_applies_on(tpl, sunday + timedelta(days=1)))

    def test_saturday_template_matches_saturday(self):
        """UI 口径周六（值 6）必须命中周六——旧 0-6 约定下会错位命中周日。"""
        tpl = SlotTemplate.objects.create(
            name="周六窗口", start_time="09:00", end_time="12:00", weekdays="6"
        )
        saturday = _next_isoweekday(date.today(), 6)
        self.assertTrue(template_applies_on(tpl, saturday))
        self.assertFalse(template_applies_on(tpl, saturday + timedelta(days=1)))

    def test_zero_rejected_by_api(self):
        """0 在 isoweekday 口径下永不匹配，必须在入口拒绝而非静默失效。"""
        resp = self.client.post("/api/slot-templates", {
            "name": "非法零", "start_time": "09:00", "end_time": "12:00",
            "weekdays": "0",
        }, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)


class StrategyNameRequiredTests(ConfigAwareTestCase):
    """B-P0-2：创建/更新策略缺 name → 42201（旧行为：IntegrityError 500 / 空串静默入库）。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")
        self.tmpl = StrategyTemplate.objects.create(
            name="晚间全量冒烟", smoke_minutes=480, analysis_minutes=120
        )

    def _login(self, username):
        resp = self.client.post(
            "/api/auth/login", {"username": username, "password": "123456"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")

    def _payload(self, **overrides):
        data = {
            "branch_id": self.branch.id, "template_id": self.tmpl.id,
            "build_start_time": "22:00", "push_mode": "normal", "enabled": True,
        }
        data.update(overrides)
        return data

    def test_pm_create_missing_name_422(self):
        self._login("pm1")
        resp = self.client.post("/api/strategies", self._payload(), format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_pm_create_blank_name_422(self):
        self._login("pm1")
        for blank in ("", "   "):
            resp = self.client.post("/api/strategies", self._payload(name=blank), format="json")
            self.assertEqual(resp.status_code, 422, msg=repr(blank))
            self.assertEqual(resp.json()["code"], 42201, msg=repr(blank))

    def test_admin_create_missing_name_422(self):
        self._login("admin")
        resp = self.client.post("/api/admin/strategies", self._payload(), format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_create_with_valid_name_ok_and_trimmed(self):
        self._login("pm1")
        resp = self.client.post("/api/strategies", self._payload(name="  夜间构建  "), format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["name"], "夜间构建")

    def test_update_name_to_blank_422(self):
        self._login("pm1")
        s = Strategy.objects.create(
            branch=self.branch, template=self.tmpl, name="原有名",
            build_start_time="22:00", push_mode="normal", created_by=self.pm,
        )
        resp = self.client.patch(f"/api/strategies/{s.id}", {"name": "  "}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)


class PlanDateGuardTests(ConfigAwareTestCase):
    """B-P0-3：GET /api/plan?date=非法值 → 42201（旧行为：strptime ValueError 500）。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")
        self.tmpl = StrategyTemplate.objects.create(
            name="晚间全量冒烟", smoke_minutes=480, analysis_minutes=120
        )
        # 旧 500 需要至少一条启用策略才会触发 build_timeline 解析日期，夹具保持同条件
        Strategy.objects.create(
            branch=self.branch, template=self.tmpl, name="夜间构建",
            build_start_time="22:00", push_mode="normal", created_by=self.pm,
        )
        resp = self.client.post(
            "/api/auth/login", {"username": "pm1", "password": "123456"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")

    def test_invalid_date_422(self):
        for bad in ("abc", "2026-13-99", "2026/10/12", "  "):
            resp = self.client.get(f"/api/plan?date={bad}")
            self.assertEqual(resp.status_code, 422, msg=bad)
            self.assertEqual(resp.json()["code"], 42201, msg=bad)

    def test_valid_date_200(self):
        resp = self.client.get("/api/plan?date=2026-10-12")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["code"], 0)

    def test_default_date_200(self):
        resp = self.client.get("/api/plan")
        self.assertEqual(resp.status_code, 200)


class TemplateMinutesGuardTests(ConfigAwareTestCase):
    """B-P0-4：模板整数字段非法类型/负数 → 42201（旧行为：ValueError/IntegrityError/TypeError 500）。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        resp = self.client.post(
            "/api/auth/login", {"username": "admin", "password": "123456"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")

    def test_create_invalid_minutes_422(self):
        for bad in ("abc", -5, 1.5, [], {}):
            resp = self.client.post("/api/admin/templates", {
                "name": f"模板-{bad!r}", "smoke_minutes": bad, "analysis_minutes": 30,
            }, format="json")
            self.assertEqual(resp.status_code, 422, msg=repr(bad))
            self.assertEqual(resp.json()["code"], 42201, msg=repr(bad))

    def test_create_explicit_null_minutes_defaults_to_zero(self):
        """显式 null 视为未提供，落默认 0（旧行为：NOT NULL IntegrityError 500）。"""
        resp = self.client.post("/api/admin/templates", {
            "name": "模板-null", "smoke_minutes": None, "analysis_minutes": None,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["smoke_minutes"], 0)
        self.assertEqual(resp.json()["data"]["analysis_minutes"], 0)

    def test_create_invalid_analysis_minutes_422(self):
        resp = self.client.post("/api/admin/templates", {
            "name": "模板-analysis", "smoke_minutes": 30, "analysis_minutes": "xyz",
        }, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_create_non_string_name_or_description_422(self):
        resp = self.client.post("/api/admin/templates", {
            "name": {"zh": "字典名"}, "smoke_minutes": 30, "analysis_minutes": 30,
        }, format="json")
        self.assertEqual(resp.status_code, 422)
        resp = self.client.post("/api/admin/templates", {
            "name": "模板-desc", "description": ["列表"], "smoke_minutes": 30, "analysis_minutes": 30,
        }, format="json")
        self.assertEqual(resp.status_code, 422)

    def test_create_valid_ok(self):
        resp = self.client.post("/api/admin/templates", {
            "name": "模板-合法", "smoke_minutes": "45", "analysis_minutes": 30,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["smoke_minutes"], 45)

    def test_patch_invalid_minutes_422(self):
        t = StrategyTemplate.objects.create(name="模板-待改", smoke_minutes=30, analysis_minutes=30)
        for bad in ("abc", -1, {}):
            resp = self.client.patch(f"/api/admin/templates/{t.id}", {
                "smoke_minutes": bad,
            }, format="json")
            self.assertEqual(resp.status_code, 422, msg=repr(bad))
            self.assertEqual(resp.json()["code"], 42201, msg=repr(bad))

    def test_patch_blank_name_422(self):
        t = StrategyTemplate.objects.create(name="模板-待改2", smoke_minutes=30, analysis_minutes=30)
        resp = self.client.patch(f"/api/admin/templates/{t.id}", {"name": "   "}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)


class CsrfHardeningTests(ConfigAwareTestCase):
    """B-P0-5：CSRF 中间件保护 django-admin 会话面；JWT API 全量豁免不受影响。"""

    def test_csrf_middleware_installed(self):
        from django.conf import settings
        self.assertIn("django.middleware.csrf.CsrfViewMiddleware", settings.MIDDLEWARE)

    def test_function_api_exempt_from_csrf(self):
        """开启 CSRF 强校验后，无 token 的登录 POST 不应被 403（应为业务码响应）。"""
        client = APIClient(enforce_csrf_checks=True)
        resp = client.post("/api/auth/login", {"username": "x", "password": "y"}, format="json")
        self.assertNotEqual(resp.status_code, 403)
        self.assertIn("code", resp.json())

    def test_viewset_api_exempt_from_csrf(self):
        """DRF ViewSet 自带 csrf_exempt：无 token 的报告 POST 走未认证而非 CSRF 403。"""
        client = APIClient(enforce_csrf_checks=True)
        resp = client.post("/api/reports", {}, format="json")
        self.assertNotEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], 40100)


class ToggleMethodGuardTests(ConfigAwareTestCase):
    """B-P1-7：toggle 仅接受 POST/PATCH，GET 不得产生副作用。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")
        self.tmpl = StrategyTemplate.objects.create(name="模板A", smoke_minutes=60, analysis_minutes=30)
        self.s = Strategy.objects.create(
            branch=self.branch, template=self.tmpl, name="策略A",
            build_start_time="22:00", push_mode="normal", created_by=self.pm, enabled=True,
        )
        resp = self.client.post(
            "/api/auth/login", {"username": "pm1", "password": "123456"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")

    def test_get_toggle_rejected_and_no_side_effect(self):
        resp = self.client.get(f"/api/strategies/{self.s.id}/toggle")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        self.s.refresh_from_db()
        self.assertTrue(self.s.enabled)

    def test_patch_toggle_flips(self):
        resp = self.client.patch(f"/api/strategies/{self.s.id}/toggle")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["data"]["enabled"])

    def test_post_toggle_flips(self):
        resp = self.client.post(f"/api/strategies/{self.s.id}/toggle")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["data"]["enabled"])


class AdminMethodGuardTests(ConfigAwareTestCase):
    """B-P1-8：update_version/add_branch/update_user 补方法守卫，GET/DELETE 无副作用。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.builder = User.objects.create_user(username="b1", password="123456", role="builder")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        resp = self.client.post(
            "/api/auth/login", {"username": "admin", "password": "123456"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")

    def test_update_version_get_rejected_no_side_effect(self):
        resp = self.client.get(f"/api/admin/versions/{self.version.id}")
        self.assertEqual(resp.status_code, 422)
        before = AdminOpLog.objects.count()
        self.version.refresh_from_db()
        self.assertEqual(self.version.name, "27A")
        self.assertEqual(AdminOpLog.objects.count(), before)

    def test_update_version_delete_rejected(self):
        """DELETE 曾不删数据却返回成功 payload（删除成功假象），必须显式拒绝。"""
        resp = self.client.delete(f"/api/admin/versions/{self.version.id}")
        self.assertEqual(resp.status_code, 422)
        self.assertTrue(Version.objects.filter(id=self.version.id).exists())

    def test_update_version_put_and_patch_ok(self):
        for method in (self.client.put, self.client.patch):
            resp = method(f"/api/admin/versions/{self.version.id}", {"status": "active"}, format="json")
            self.assertEqual(resp.status_code, 200)

    def test_add_branch_get_rejected(self):
        resp = self.client.get(f"/api/admin/versions/{self.version.id}/branches")
        self.assertEqual(resp.status_code, 422)
        self.assertFalse(Branch.objects.filter(version=self.version).exists())

    def test_update_user_get_rejected(self):
        resp = self.client.get(f"/api/admin/users/{self.pm.id}")
        self.assertEqual(resp.status_code, 422)

    def test_update_user_put_rejected(self):
        resp = self.client.put(f"/api/admin/users/{self.pm.id}", {"role": "builder"}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.pm.refresh_from_db()
        self.assertEqual(self.pm.role, "pm")


class ExecutionsPmIsolationTests(ConfigAwareTestCase):
    """B-P1-9/B-P1-10：轮次详情 PM 版本隔离 + 结论提交原子防重与角色/参数矩阵。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.pm_a = User.objects.create_user(username="pmA", password="123456", role="pm")
        self.pm_b = User.objects.create_user(username="pmB", password="123456", role="pm")
        self.tester = User.objects.create_user(username="t1", password="123456", role="tester")
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        self.v_a = Version.objects.create(name="27A", pm_user=self.pm_a, status="active")
        self.v_b = Version.objects.create(name="27B", pm_user=self.pm_b, status="active")
        self.b_a = Branch.objects.create(version=self.v_a, name="master")
        self.tmpl = StrategyTemplate.objects.create(name="模板A", smoke_minutes=60, analysis_minutes=30)
        self.s_a = Strategy.objects.create(
            branch=self.b_a, template=self.tmpl, name="策略A",
            build_start_time="22:00", push_mode="normal", created_by=self.pm_a,
        )
        self.round = ExecutionRound.objects.create(strategy=self.s_a, exec_date="2026-10-12")

    def _login(self, username):
        resp = self.client.post(
            "/api/auth/login", {"username": username, "password": "123456"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")

    def test_own_pm_can_read_round_detail(self):
        self._login("pmA")
        resp = self.client.get(f"/api/executions/rounds/{self.round.id}")
        self.assertEqual(resp.status_code, 200)

    def test_other_pm_round_detail_403(self):
        self._login("pmB")
        resp = self.client.get(f"/api/executions/rounds/{self.round.id}")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], 40301)

    def test_admin_and_tester_round_detail_ok(self):
        for who in ("admin", "t1"):
            self._login(who)
            resp = self.client.get(f"/api/executions/rounds/{self.round.id}")
            self.assertEqual(resp.status_code, 200, msg=who)

    def test_round_detail_404(self):
        self._login("admin")
        resp = self.client.get("/api/executions/rounds/999999")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["code"], 40401)

    def test_conclusion_non_tester_403(self):
        self._login("pmA")
        resp = self.client.post(
            f"/api/executions/rounds/{self.round.id}/conclusion",
            {"conclusion": "pass"}, format="json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], 40301)

    def test_conclusion_invalid_value_422(self):
        self._login("t1")
        resp = self.client.post(
            f"/api/executions/rounds/{self.round.id}/conclusion",
            {"conclusion": "maybe"}, format="json",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_conclusion_get_rejected(self):
        self._login("t1")
        resp = self.client.get(f"/api/executions/rounds/{self.round.id}/conclusion")
        self.assertEqual(resp.status_code, 422)

    def test_conclusion_duplicate_40902(self):
        self._login("t1")
        first = self.client.post(
            f"/api/executions/rounds/{self.round.id}/conclusion",
            {"conclusion": "pass", "note": "全绿"}, format="json",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["data"]["conclusion"], "pass")
        second = self.client.post(
            f"/api/executions/rounds/{self.round.id}/conclusion",
            {"conclusion": "fail"}, format="json",
        )
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["code"], 40902)
        self.round.refresh_from_db()
        self.assertEqual(self.round.conclusion, "pass")

    def test_conclusion_pass_normal_pushes(self):
        self._login("t1")
        resp = self.client.post(
            f"/api/executions/rounds/{self.round.id}/conclusion",
            {"conclusion": "pass"}, format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["push_status"], "pushed")


class StrategyVisibilityAndValueDomainTests(ConfigAwareTestCase):
    """B-P1-11/B-P1-12：无绑定 PM fail-closed + push_mode/enabled 值域校验。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.pm_bound = User.objects.create_user(username="pmA", password="123456", role="pm")
        self.pm_free = User.objects.create_user(username="pmFree", password="123456", role="pm")
        self.version = Version.objects.create(name="27A", pm_user=self.pm_bound, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")
        self.tmpl = StrategyTemplate.objects.create(name="模板A", smoke_minutes=60, analysis_minutes=30)
        self.s = Strategy.objects.create(
            branch=self.branch, template=self.tmpl, name="策略A",
            build_start_time="22:00", push_mode="normal", created_by=self.pm_bound,
        )

    def _login(self, username):
        resp = self.client.post(
            "/api/auth/login", {"username": username, "password": "123456"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")

    def test_unbound_pm_sees_empty_list(self):
        """未绑定版本的 PM 此前可见全部策略，必须 fail-closed 为空集。"""
        self._login("pmFree")
        resp = self.client.get("/api/strategies")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"], [])

    def test_bound_pm_sees_own_version(self):
        self._login("pmA")
        resp = self.client.get("/api/strategies")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["data"]), 1)

    def test_update_push_mode_invalid_422(self):
        self._login("pmA")
        resp = self.client.patch(f"/api/strategies/{self.s.id}", {"push_mode": "xyz"}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        self.s.refresh_from_db()
        self.assertEqual(self.s.push_mode, "normal")

    def test_update_enabled_string_422(self):
        self._login("pmA")
        resp = self.client.patch(f"/api/strategies/{self.s.id}", {"enabled": "false"}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        self.s.refresh_from_db()
        self.assertTrue(self.s.enabled)

    def test_create_push_mode_invalid_422(self):
        self._login("pmA")
        resp = self.client.post("/api/strategies", {
            "branch_id": self.branch.id, "template_id": self.tmpl.id,
            "name": "策略B", "build_start_time": "23:00", "push_mode": "turbo",
        }, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_update_push_mode_sync_ok(self):
        self._login("pmA")
        resp = self.client.patch(f"/api/strategies/{self.s.id}", {"push_mode": "sync"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["push_mode"], "sync")


class AdminUserManagementTests(ConfigAwareTestCase):
    """B-P1-14 + B-P2-21：建用户密码必填、类型守卫、is_active 严格布尔、PM 角色校验。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.builder = User.objects.create_user(username="b1", password="123456", role="builder")
        resp = self.client.post(
            "/api/auth/login", {"username": "admin", "password": "123456"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")

    def test_create_user_requires_password(self):
        resp = self.client.post("/api/admin/users", {
            "username": "newbie", "role": "builder",
        }, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        self.assertFalse(User.objects.filter(username="newbie").exists())

    def test_create_user_ok(self):
        resp = self.client.post("/api/admin/users", {
            "username": "newbie", "role": "builder", "password": "Str0ng!pass",
            "display_name": "新同事",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        u = User.objects.get(username="newbie")
        self.assertTrue(u.check_password("Str0ng!pass"))
        self.assertEqual(u.display_name, "新同事")

    def test_create_user_non_string_fields_422(self):
        resp = self.client.post("/api/admin/users", {
            "username": {"a": 1}, "role": "builder", "password": "x12345",
        }, format="json")
        self.assertEqual(resp.status_code, 422)
        resp = self.client.post("/api/admin/users", {
            "username": "u2", "role": "builder", "password": ["list"],
        }, format="json")
        self.assertEqual(resp.status_code, 422)

    def test_users_get_list_ok(self):
        """零覆盖端点补齐：GET /admin/users 列表。"""
        resp = self.client.get("/api/admin/users")
        self.assertEqual(resp.status_code, 200)
        usernames = {u["username"] for u in resp.json()["data"]}
        self.assertIn("admin", usernames)

    def test_update_user_is_active_strict_bool(self):
        """垃圾值此前被静默解析为「停用」，必须 422。"""
        resp = self.client.patch(f"/api/admin/users/{self.builder.id}", {
            "is_active": "yes",
        }, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        self.builder.refresh_from_db()
        self.assertTrue(self.builder.is_active)

    def test_update_user_password_type_guard(self):
        resp = self.client.patch(f"/api/admin/users/{self.builder.id}", {
            "password": {"dict": True},
        }, format="json")
        self.assertEqual(resp.status_code, 422)

    def test_create_version_pm_must_have_pm_role(self):
        resp = self.client.post("/api/admin/versions", {
            "name": "28A", "pm_user_id": self.builder.id,
        }, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        self.assertFalse(Version.objects.filter(name="28A").exists())

    def test_update_version_pm_role_check(self):
        v = Version.objects.create(name="27C", pm_user=self.pm, status="active")
        resp = self.client.put(f"/api/admin/versions/{v.id}", {
            "pm_user_id": self.builder.id,
        }, format="json")
        self.assertEqual(resp.status_code, 422)

    def test_versions_get_list_ok(self):
        """零覆盖端点补齐：GET /admin/versions 列表。"""
        Version.objects.create(name="27D", pm_user=self.pm, status="active")
        resp = self.client.get("/api/admin/versions")
        self.assertEqual(resp.status_code, 200)
        names = {v["name"] for v in resp.json()["data"]}
        self.assertIn("27D", names)


class ContractExceptionHandlerTests(ConfigAwareTestCase):
    """B-P1-15：DRF 异常也走 {code,message,data} 信封（非法 JSON body 不再返回 {"detail":...}）。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.tester = User.objects.create_user(username="t1", password="123456", role="tester")
        resp = self.client.post(
            "/api/auth/login", {"username": "t1", "password": "123456"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")

    def test_invalid_json_body_returns_envelope(self):
        resp = self.client.post(
            "/api/reports", "{不是合法 JSON", content_type="application/json"
        )
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertEqual(data["code"], 42201)
        self.assertIn("message", data)
        self.assertIn("data", data)


class LoginLockoutKeyTests(ConfigAwareTestCase):
    """B-P1-16：登录锁定按「用户名+IP」联合键，他人无法远程锁死任意账号。"""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")

    def tearDown(self):
        cache.clear()

    def _post(self, username, password, ip):
        return self.client.post(
            "/api/auth/login", {"username": username, "password": password},
            format="json", REMOTE_ADDR=ip,
        )

    def test_same_ip_locked_after_5_failures(self):
        for _ in range(5):
            resp = self._post("admin", "wrong-pass", "10.0.0.1")
            self.assertEqual(resp.json()["code"], 40101)
        locked = self._post("admin", "123456", "10.0.0.1")
        self.assertEqual(locked.status_code, 429)
        self.assertEqual(locked.json()["code"], 42901)

    def test_other_ip_not_locked(self):
        for _ in range(5):
            self._post("admin", "wrong-pass", "10.0.0.1")
        ok_resp = self._post("admin", "123456", "10.0.0.2")
        self.assertEqual(ok_resp.status_code, 200)
        self.assertEqual(ok_resp.json()["code"], 0)


class AdminMiscHardeningTests(ConfigAwareTestCase):
    """B-P2-21/22：模板重名 40902、logs kind 值域、config 读写与非法值 422。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        StrategyTemplate.objects.create(name="模板X", smoke_minutes=30, analysis_minutes=30)
        resp = self.client.post(
            "/api/auth/login", {"username": "admin", "password": "123456"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")

    def test_create_duplicate_template_name_40902(self):
        resp = self.client.post("/api/admin/templates", {
            "name": "模板X", "smoke_minutes": 30, "analysis_minutes": 30,
        }, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)

    def test_patch_template_rename_duplicate_40902(self):
        other = StrategyTemplate.objects.create(name="模板Y", smoke_minutes=30, analysis_minutes=30)
        resp = self.client.patch(f"/api/admin/templates/{other.id}", {"name": "模板X"}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)

    def test_logs_kind_valid(self):
        for kind in ("operations", "security"):
            resp = self.client.get(f"/api/admin/logs/{kind}")
            self.assertEqual(resp.status_code, 200, msg=kind)
            self.assertEqual(resp.json()["code"], 0, msg=kind)

    def test_logs_unknown_kind_422(self):
        """未知 kind 此前静默落到 security 分支，必须显式 422。"""
        resp = self.client.get("/api/admin/logs/oops")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_config_get_ok(self):
        """零覆盖端点补齐：GET /admin/config。"""
        resp = self.client.get("/api/admin/config")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        for key in ("build_minutes", "push_minutes", "sync_buffer_minutes"):
            self.assertIn(key, data)

    def test_config_put_invalid_422(self):
        resp = self.client.put("/api/admin/config", {"build_minutes": "abc"}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_config_put_ok(self):
        resp = self.client.put("/api/admin/config", {"build_minutes": 90}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["build_minutes"], 90)


class ExecutionsFilterTests(ConfigAwareTestCase):
    """零覆盖补齐：executions 的 date/from/to 过滤（合法 + 非法 42201）。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        version = Version.objects.create(name="27A", pm_user=pm, status="active")
        branch = Branch.objects.create(version=version, name="master")
        tmpl = StrategyTemplate.objects.create(name="模板A", smoke_minutes=60, analysis_minutes=30)
        strategy = Strategy.objects.create(
            branch=branch, template=tmpl, name="策略A",
            build_start_time="22:00", push_mode="normal", created_by=pm,
        )
        ExecutionRound.objects.create(strategy=strategy, exec_date="2026-10-10")
        ExecutionRound.objects.create(strategy=strategy, exec_date="2026-10-12")
        ExecutionRound.objects.create(strategy=strategy, exec_date="2026-10-14")
        resp = self.client.post(
            "/api/auth/login", {"username": "admin", "password": "123456"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")

    def test_filter_by_date(self):
        resp = self.client.get("/api/executions?date=2026-10-12")
        self.assertEqual(resp.status_code, 200)
        rows = resp.json()["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["exec_date"], "2026-10-12")

    def test_filter_by_range(self):
        resp = self.client.get("/api/executions?from=2026-10-11&to=2026-10-13")
        self.assertEqual(resp.status_code, 200)
        rows = resp.json()["data"]
        self.assertEqual([r["exec_date"] for r in rows], ["2026-10-12"])

    def test_invalid_date_filters_422(self):
        for query in ("date=abc", "from=xyz", "to=123"):
            resp = self.client.get(f"/api/executions?{query}")
            self.assertEqual(resp.status_code, 422, msg=query)
            self.assertEqual(resp.json()["code"], 42201, msg=query)


class StrategyPreviewConflictTests(ConfigAwareTestCase):
    """补齐 preview 冲突命中分支断言（此前仅测非 POST/非法 id/exclude_id）。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")
        self.tmpl = StrategyTemplate.objects.create(name="模板A", smoke_minutes=60, analysis_minutes=30)
        Strategy.objects.create(
            branch=self.branch, template=self.tmpl, name="既有策略",
            build_start_time="22:00", push_mode="normal", created_by=self.pm,
        )
        resp = self.client.post(
            "/api/auth/login", {"username": "pm1", "password": "123456"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")

    def _preview(self, build_start_time, push_mode="normal"):
        return self.client.post("/api/strategies/preview", {
            "branch_id": self.branch.id, "template_id": self.tmpl.id,
            "build_start_time": build_start_time, "push_mode": push_mode,
        }, format="json")

    def test_conflict_hit_returns_conflict_payload(self):
        resp = self._preview("22:00")
        self.assertEqual(resp.status_code, 200)
        conflict = resp.json()["data"]["conflict"]
        self.assertIsNotNone(conflict)
        self.assertIn(conflict["code"], (40901, 40902))
        self.assertTrue(conflict["message"])

    def test_no_conflict_returns_timeline(self):
        resp = self._preview("03:00")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertIsNone(data["conflict"])
        self.assertTrue(data["timeline"]["build"]["start"].endswith("T03:00:00"))

    def test_invalid_push_mode_422(self):
        """值域非法走错误响应而非 conflict 载荷（B-P1-12 配套）。"""
        resp = self._preview("03:00", push_mode="turbo")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)


class AdminToggleConflictTests(ConfigAwareTestCase):
    """补齐：admin toggle 启用撞 uniq_active_strategy_branch_time → 40902。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        version = Version.objects.create(name="27A", pm_user=pm, status="active")
        self.branch = Branch.objects.create(version=version, name="master")
        tmpl = StrategyTemplate.objects.create(name="模板A", smoke_minutes=60, analysis_minutes=30)
        Strategy.objects.create(
            branch=self.branch, template=tmpl, name="启用中的策略",
            build_start_time="22:00", push_mode="normal", created_by=pm, enabled=True,
        )
        self.disabled = Strategy.objects.create(
            branch=self.branch, template=tmpl, name="停用的同刻策略",
            build_start_time="22:00", push_mode="normal", created_by=pm, enabled=False,
        )
        resp = self.client.post(
            "/api/auth/login", {"username": "admin", "password": "123456"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")

    def test_admin_toggle_enable_conflict_40902(self):
        resp = self.client.patch(f"/api/admin/strategies/{self.disabled.id}/toggle")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)
        self.disabled.refresh_from_db()
        self.assertFalse(self.disabled.enabled)


class BorrowFlowVisibilityTests(ConfigAwareTestCase):
    """B-P2-20/信息暴露：电子流仅相关人可见 + pending 唯一约束兜底并发重复发起。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.pm_a = User.objects.create_user(username="pmA", password="123456", role="pm")
        self.pm_b = User.objects.create_user(username="pmB", password="123456", role="pm")
        self.builder_x = User.objects.create_user(username="bx", password="123456", role="builder")
        self.builder_y = User.objects.create_user(username="by", password="123456", role="builder")
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        self.v_a = Version.objects.create(name="27A", pm_user=self.pm_a, status="active")
        self.v_b = Version.objects.create(name="27B", pm_user=self.pm_b, status="active")
        self.b_a = Branch.objects.create(version=self.v_a, name="master")
        self.b_b = Branch.objects.create(version=self.v_b, name="master")
        tmpl = StrategyTemplate.objects.create(name="模板A", smoke_minutes=60, analysis_minutes=30)
        self.strategy = Strategy.objects.create(
            branch=self.b_a, template=tmpl, name="被借策略",
            build_start_time="22:00", push_mode="normal", created_by=self.pm_a,
        )
        self._login("bx")
        resp = self.client.post("/api/borrow-flows", {
            "strategy_id": self.strategy.id, "target_branch_id": self.b_b.id,
            "new_build_time": "23:00", "reason": "联调需要借用构建窗口",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.flow_id = resp.json()["data"]["id"]

    def _login(self, username):
        resp = self.client.post(
            "/api/auth/login", {"username": username, "password": "123456"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")

    def _list(self):
        resp = self.client.get("/api/borrow-flows")
        self.assertEqual(resp.status_code, 200)
        return resp.json()["data"]

    def test_visibility_matrix(self):
        cases = {
            "bx": 1,      # 发起人可见
            "by": 0,      # 无关用户不可见（此前全量可见 → 信息暴露）
            "pmA": 1,     # 审批人（源版本 PM）可见
            "pmB": 0,     # 目标版本 PM 非审批参与方，不可见
            "admin": 1,   # 管理员全量可见
        }
        for username, expected in cases.items():
            self._login(username)
            self.assertEqual(len(self._list()), expected, msg=username)

    def test_duplicate_pending_rejected_40903(self):
        self._login("bx")
        resp = self.client.post("/api/borrow-flows", {
            "strategy_id": self.strategy.id, "target_branch_id": self.b_b.id,
            "new_build_time": "23:30", "reason": "重复发起",
        }, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40903)

    def test_db_constraint_blocks_double_pending(self):
        """部分唯一约束 uniq_pending_borrow_flow 在 DB 层兜底并发双发起。"""
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BorrowFlow.objects.create(
                    strategy=self.strategy, borrower=self.builder_x,
                    target_branch=self.b_b, new_build_time="23:45",
                )

    def test_invalid_status_filter_422(self):
        self._login("admin")
        resp = self.client.get("/api/borrow-flows?status=oops")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)


class ReportPublishAtomicTests(ConfigAwareTestCase):
    """B-P2-20：发布计数 F() 原子自增、留痕完整（create + 两次 publish = 3 条）。"""

    def test_publish_increments_and_logs(self):
        report = ReportService.create("t1", {
            "title": "冒烟报告", "conclusion": "pass", "summary": "全部通过",
        })
        self.assertEqual(report.publish_count, 0)
        ReportService.publish("t1", report)
        self.assertEqual(report.publish_count, 1)
        self.assertEqual(report.status, "published")
        ReportService.publish("t1", report)
        self.assertEqual(report.publish_count, 2)
        revisions = ReportService.revisions(report.id)
        self.assertEqual(len(revisions), 3)
        self.assertEqual(revisions[0].action, "publish")  # 倒序：最近一条在前
        self.assertEqual(revisions[-1].action, "create")


class BranchProjectDestroyTests(ConfigAwareTestCase):
    """零覆盖端点补齐：DELETE /api/branch-projects/<pk>（ADMIN 可删、VIEWER 403、404）。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        self.builder = User.objects.create_user(username="b1", password="123456", role="builder")
        pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        version = Version.objects.create(name="27A", pm_user=pm, status="active")
        self.branch = Branch.objects.create(version=version, name="master")
        self.project = Project.objects.create(name="工程A")
        self.bp = BranchProject.objects.create(branch=self.branch, project=self.project)

    def _login(self, username):
        resp = self.client.post(
            "/api/auth/login", {"username": username, "password": "123456"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")

    def test_viewer_cannot_delete(self):
        self._login("b1")
        resp = self.client.delete(f"/api/branch-projects/{self.bp.id}")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], 40301)
        self.assertTrue(BranchProject.objects.filter(id=self.bp.id).exists())

    def test_admin_delete_ok(self):
        self._login("admin")
        resp = self.client.delete(f"/api/branch-projects/{self.bp.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(BranchProject.objects.filter(id=self.bp.id).exists())
        self.assertTrue(Project.objects.filter(id=self.project.id).exists())  # 工程库不受影响

    def test_delete_missing_404(self):
        self._login("admin")
        resp = self.client.delete("/api/branch-projects/999999")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["code"], 40401)


class SlotAdminListStatusTests(ConfigAwareTestCase):
    """B-P2-21：admin 抢占记录列表 status 参数值域校验。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        resp = self.client.post(
            "/api/auth/login", {"username": "admin", "password": "123456"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")

    def test_invalid_status_422(self):
        resp = self.client.get("/api/slot-bookings?status=oops")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_valid_status_ok(self):
        for status in ("reserved", "released"):
            resp = self.client.get(f"/api/slot-bookings?status={status}")
            self.assertEqual(resp.status_code, 200, msg=status)
