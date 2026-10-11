"""第二轮全库质量优化（2026-10-12）回归测试。

对应 docs/code-quality-assessment-2026-10-12.md 与
docs/superpowers/specs/2026-10-12-code-quality-optimization-round2-design.md：
每个修复项一组锁定测试，防止同类问题复发。
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from .models import Branch, SlotTemplate, Strategy, StrategyTemplate, Version
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
