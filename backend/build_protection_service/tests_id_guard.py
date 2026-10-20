"""ID 参数类型防护回归测试。

背景：Django 对 ``filter(id="abc")`` 抛 ``ValueError``，未捕获即 HTTP 500，
破坏 {code,message,data} 统一契约。修复前 strategies/weekly/slot_booking
共多处裸用 query/body 参数。

本文件锁定「非法 ID → 42201」这一契约，防止新增端点重犯。

约定：query 中 ``?k=``（空串）等价于「不提供该过滤条件」，属合法用法返回 200；
只有**非空且非数字**的值才判 422。
"""
import json

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from .models import Branch, SlotTemplate, StrategyTemplate, Version
from .tests import ConfigAwareTestCase
from .views import fetch_by_id, parse_int

User = get_user_model()

_BAD_IDS = ["abc", "1; DROP TABLE", "  ", "1.5.6", "０", "１２３", "None", "id", True, False, [], {}]


class ParseIntTests(ConfigAwareTestCase):
    """parse_int：非数字一律返回 None，绝不抛异常。"""

    def test_invalid_values_return_none(self):
        for bad in _BAD_IDS:
            self.assertIsNone(parse_int(bad), msg=f"输入={bad!r}")

    def test_valid_values_accepted(self):
        self.assertEqual(parse_int("12"), 12)
        self.assertEqual(parse_int(12), 12)
        self.assertEqual(parse_int(" 7 "), 7)
        self.assertEqual(parse_int(0), 0)

    def test_bool_is_rejected(self):
        """bool 是 int 子类，直接 int(True)==1 会误当合法 ID，须显式拒绝。"""
        self.assertIsNone(parse_int(True))
        self.assertIsNone(parse_int(False))


class FetchByIdTests(ConfigAwareTestCase):
    """fetch_by_id：非法 → 42201；合法但不存在 → 40401；命中 → (对象, None)。"""

    def setUp(self):
        super().setUp()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")

    def test_invalid_id_returns_422(self):
        for bad in _BAD_IDS:
            obj, err = fetch_by_id(Branch, bad, not_found="分支不存在")
            self.assertIsNone(obj, msg=f"输入={bad!r}")
            self.assertIsNotNone(err, msg=f"输入={bad!r}")
            self.assertEqual(err.status_code, 422, msg=f"输入={bad!r}")
            payload = json.loads(err.content.decode())
            self.assertEqual(payload["code"], 42201, msg=f"输入={bad!r}")

    def test_missing_record_returns_404(self):
        obj, err = fetch_by_id(Branch, 999999, not_found="分支不存在")
        self.assertIsNone(obj)
        self.assertEqual(err.status_code, 404)
        self.assertIn("分支不存在", err.content.decode())

    def test_existing_record_returned(self):
        obj, err = fetch_by_id(Branch, self.branch.id, not_found="分支不存在")
        self.assertIsNone(err)
        self.assertEqual(obj.pk, self.branch.pk)

    def test_accepts_preselect_related_queryset(self):
        """extra_queryset 用于携带 select_related，避免 N+1。"""
        qs = Branch.objects.select_related("version")
        obj, err = fetch_by_id(Branch, self.branch.id, extra_queryset=qs)
        self.assertIsNone(err)
        self.assertEqual(obj.version_id, self.version.pk)


class StrategyIdGuardTests(ConfigAwareTestCase):
    """策略端点：body 的 branch_id/template_id 非数字 → 42201，不 500。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        User.objects.create_user(username="admin", password="123456", role="admin")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")
        self.tmpl = StrategyTemplate.objects.create(
            name="晚间冒烟", smoke_minutes=480, analysis_minutes=120
        )
        resp = self.client.post(
            "/api/auth/login", {"username": "pm1", "password": "123456"}, format="json"
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}"
        )

    def test_create_with_non_numeric_branch_id_422(self):
        for bad in ("abc", "1; DROP", ""):
            resp = self.client.post("/api/strategies", {
                "branch_id": bad, "template_id": self.tmpl.id,
                "name": f"策略-{bad}", "build_start_time": "22:00",
            }, format="json")
            self.assertEqual(resp.status_code, 422, msg=f"输入={bad!r}")
            self.assertEqual(resp.json()["code"], 42201, msg=f"输入={bad!r}")

    def test_create_with_non_numeric_template_id_422(self):
        resp = self.client.post("/api/strategies", {
            "branch_id": self.branch.id, "template_id": "abc",
            "name": "策略-x", "build_start_time": "22:00",
        }, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_preview_with_non_numeric_ids_422(self):
        for bad in ("abc", ""):
            resp = self.client.post("/api/strategies/preview", {
                "branch_id": bad, "template_id": self.tmpl.id,
                "build_start_time": "22:00",
            }, format="json")
            self.assertEqual(resp.status_code, 422, msg=f"输入={bad!r}")
            self.assertEqual(resp.json()["code"], 42201, msg=f"输入={bad!r}")

    def test_list_with_non_numeric_query_id_422(self):
        for key in ("version_id", "branch_id"):
            resp = self.client.get(f"/api/strategies?{key}=abc")
            self.assertEqual(resp.status_code, 422, msg=key)
            self.assertEqual(resp.json()["code"], 42201, msg=key)

    def test_preview_exclude_id_non_numeric_does_not_500(self):
        """exclude_id 也会流向 exclude(id=...)，非数字必须被吞掉。"""
        resp = self.client.post("/api/strategies/preview", {
            "branch_id": self.branch.id, "template_id": self.tmpl.id,
            "build_start_time": "22:00", "id": "abc",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["code"], 0)

    def test_valid_ids_still_work(self):
        """回归保护：合法 ID 不能被误伤。"""
        resp = self.client.post("/api/strategies", {
            "branch_id": self.branch.id, "template_id": self.tmpl.id,
            "name": "正常策略", "build_start_time": "22:00",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["code"], 0)


class WeeklyIdGuardTests(ConfigAwareTestCase):
    """周视图：query 的 version_id 非数字 → 42201。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        User.objects.create_user(username="pm1", password="123456", role="pm")
        resp = self.client.post(
            "/api/auth/login", {"username": "pm1", "password": "123456"}, format="json"
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}"
        )

    def test_non_numeric_version_id_422(self):
        for bad in ("abc", "1; DROP", "０"):
            resp = self.client.get(f"/api/weekly?version_id={bad}")
            self.assertEqual(resp.status_code, 422, msg=f"输入={bad!r}")
            self.assertEqual(resp.json()["code"], 42201, msg=f"输入={bad!r}")

    def test_empty_version_id_means_no_filter(self):
        """空串等价于不筛选，属合法用法，不应 422。"""
        resp = self.client.get("/api/weekly?version_id=")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["code"], 0)

    def test_numeric_version_id_ok(self):
        resp = self.client.get("/api/weekly?version_id=999999")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["code"], 0)






class SlotBookingIdGuardTests(ConfigAwareTestCase):
    """时段抢占：payload 的 template_id/version_id/branch_id 非数字 → 42201。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")
        self.tmpl = SlotTemplate.objects.create(
            # isoweekday 口径（1=周一…5=周五），与 _future_weekday 的选日范围一致
            name="工作日上午", start_time="09:00", end_time="12:00", weekdays="1,2,3,4,5"
        )
        resp = self.client.post(
            "/api/auth/login", {"username": "pm1", "password": "123456"}, format="json"
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}"
        )

    def _book(self, **overrides):
        payload = {
            "template_id": self.tmpl.pk,
            "date": self._future_weekday(),
            "purpose": "联调占用",
            "version_id": self.version.pk,
            "branch_id": self.branch.pk,
        }
        payload.update(overrides)
        return self.client.post("/api/slot-bookings", payload, format="json")

    def _future_weekday(self):
        from datetime import timedelta

        from django.utils import timezone

        d = timezone.localdate() + timedelta(days=3)
        while d.weekday() > 4:
            d += timedelta(days=1)
        return d.strftime("%Y-%m-%d")

    def test_non_numeric_template_id_422(self):
        resp = self._book(template_id="abc")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_non_numeric_version_or_branch_422(self):
        for key in ("version_id", "branch_id"):
            resp = self._book(**{key: "abc"})
            self.assertEqual(resp.status_code, 422, msg=key)
            self.assertEqual(resp.json()["code"], 42201, msg=key)

    def test_valid_booking_still_works(self):
        resp = self._book()
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertEqual(resp.json()["code"], 0, msg=resp.content)