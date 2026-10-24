"""第七轮质量优化（2026-10-25）回归测试。

每个修复项（R7-B1 ~ R7-B11）一组锁定测试，防止同类问题复发。
主题：范式覆盖盲区与跨层契约漂移——parse_int 老边界（R7-B1）、toggle 陈旧
快照（R7-B2）、admin 根实体级联删除（R7-B3）、/plan 死字段（R7-B4，主断言
在 tests.py）、借用流收口（R7-B5）、变更日志 null 留痕（R7-B6）、停用账号
审计（R7-B7）、异常归一（R7-B8）、版本排序（R7-B9）、seed 事务化（R7-B10）、
SlotTemplate 不变量（R7-B11）。

口径提示：
- R7-B2 沿用 round3~round6 的「陈旧实例」技巧：视图层事务外读出的实例等价物，
  制造「并发窗口内 PATCH 抢先提交」后直调服务层；
- admin 用例沿用 round6 的 _request 夹具（is_staff/is_superuser 仅测面板配置）。
"""
from datetime import time
from json import loads as json_loads
from unittest import mock

from django.contrib import admin as dj_admin
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from rest_framework.exceptions import APIException, UnsupportedMediaType
from rest_framework.test import APIClient

from .admin import (
    BranchAdmin, SlotTemplateAdmin, StrategyTemplateAdmin, VersionAdmin,
)
from .errors import (
    CODE_INTERNAL, CODE_OK, CODE_STAGE_CONFLICT, CODE_UNPROCESSABLE,
)
from .exception_handlers import contract_exception_handler
from .models import (
    Branch, SecurityLog, SlotTemplate, Strategy,
    StrategyChangeLog, StrategyTemplate, User, Version,
)
from .parsing import parse_int
from .services.strategies import StrategyValidationError, toggle_strategy
from .tests import ConfigAwareTestCase
from .tests_quality_round4 import Round4Fixture

# ---------- R7-B1 parse_int 多负号边界 ----------


class ParseIntMatrixTests(ConfigAwareTestCase):
    """B1：--5 一律 None（此前 lstrip("-") 剥掉全部负号后 int() 抛 ValueError）。"""

    def test_parse_int_matrix(self):
        cases = {
            "5": 5,
            "-5": -5,
            "-0": 0,
            " 7 ": 7,
            "--5": None,   # 多负号：isdigit 通过后 int() 必炸，必须 None
            "+5": None,
            "- 5": None,
            "-": None,
            "": None,
            "２２": None,  # 全角
            "abc": None,
            None: None,
            True: None,    # bool 当 int 拒绝
            42: 42,
        }
        for raw, expected in cases.items():
            self.assertEqual(parse_int(raw), expected, msg=repr(raw))

    def test_endpoint_rejects_multi_minus_version_id_with_422(self):
        """GET /api/strategies?version_id=--5 → 42201（此前 500）。"""
        User.objects.create_user(username="viewer", password="123456", role="builder")
        client = APIClient()
        token = client.post(
            "/api/auth/login", {"username": "viewer", "password": "123456"},
            format="json").json()["data"]["token"]
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = client.get("/api/strategies", {"version_id": "--5"})
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], CODE_UNPROCESSABLE)


# ---------- R7-B2 toggle_strategy 事务内重读 ----------


class ToggleFreshReadTests(Round4Fixture):
    """B2：toggle 校验基于事务内重读的最新状态，陈旧时间快照不再放行。"""

    def test_toggle_validates_against_concurrently_patched_time(self):
        """PATCH（停用态改时间，跳过冲突校验）后，持陈旧快照的 toggle 不得按
        旧时间放行——启用方向必须对重读出的新时间跑完整校验。"""
        # 同分支已启用 22:00 策略
        self._make_strategy(name="占位", build="22:00", enabled=True)
        # 停用策略原 21:30；并发 PATCH 改到 22:30（停用态不校验，合法提交）
        target = self._make_strategy(name="待启用", build="21:30", enabled=False)
        stale = Strategy.objects.get(pk=target.pk)  # 视图事务外读出的陈旧快照
        self._auth("pm27a")
        resp = self.client.patch(
            f"/api/strategies/{target.id}", {"build_start_time": "22:30"}, format="json"
        )
        self.assertEqual(resp.json()["code"], CODE_OK)
        # 陈旧快照（21:30）校验会通过；重读实例（22:30）与同分支 22:00 阶段冲突
        with self.assertRaises(StrategyValidationError) as ctx:
            toggle_strategy(stale)
        self.assertEqual(ctx.exception.code, CODE_STAGE_CONFLICT)
        target.refresh_from_db()
        self.assertFalse(target.enabled)

    def test_toggle_success_returns_fresh_instance(self):
        """成功路径返回重读实例：enabled 为翻转后的值，调用方据此组装响应。"""
        target = self._make_strategy(name="A", build="22:00", enabled=False)
        fresh = toggle_strategy(Strategy.objects.get(pk=target.pk))
        self.assertTrue(fresh.enabled)
        target.refresh_from_db()
        self.assertTrue(target.enabled)

    def test_view_toggle_response_and_audit_use_returned_instance(self):
        """视图层用服务层返回值组装响应与审计（外层实例为陈旧快照的等价物）。"""
        target = self._make_strategy(name="A", build="22:00", enabled=False)
        self._auth("pm27a")
        resp = self.client.patch(f"/api/strategies/{target.id}/toggle")
        self.assertEqual(resp.json()["code"], CODE_OK)
        self.assertTrue(resp.json()["data"]["enabled"])
        target.refresh_from_db()
        self.assertTrue(target.enabled)


# ---------- R7-B3 admin 根实体删除拦截 ----------


class AdminRootEntityDeleteGuardTests(Round4Fixture):
    """B3：Version/Branch/StrategyTemplate/SlotTemplate 删除面收敛。"""

    def _model_admin(self, model, admin_cls):
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save(update_fields=["is_staff", "is_superuser"])
        return admin_cls(model, dj_admin.site)

    def test_version_delete_blocked_with_branches(self):
        model_admin = self._model_admin(Version, VersionAdmin)
        with self.assertRaises(ValidationError):
            model_admin.delete_model(request=None, obj=self.v27a)
        self.assertTrue(Version.objects.filter(pk=self.v27a.pk).exists())

    def test_version_delete_allowed_when_empty(self):
        # Version.pm_user 唯一绑定，空版本用独立 PM
        empty_pm = User.objects.create_user(username="pm29a", password="123456", role="pm")
        empty = Version.objects.create(name="29A", pm_user=empty_pm, status="active")
        model_admin = self._model_admin(Version, VersionAdmin)
        model_admin.delete_model(request=None, obj=empty)
        self.assertFalse(Version.objects.filter(pk=empty.pk).exists())

    def test_branch_delete_blocked_with_strategy(self):
        self._make_strategy()
        model_admin = self._model_admin(Branch, BranchAdmin)
        with self.assertRaises(ValidationError):
            model_admin.delete_model(request=None, obj=self.b27a)
        self.assertTrue(Branch.objects.filter(pk=self.b27a.pk).exists())

    def test_branch_delete_blocked_with_slot_booking(self):
        """无策略但有抢占记录的分支：PROTECT 裸删会冒数据库错误页，前置拦截。"""
        self._make_booking(branch=self.b27a)
        model_admin = self._model_admin(Branch, BranchAdmin)
        with self.assertRaises(ValidationError):
            model_admin.delete_model(request=None, obj=self.b27a)

    def test_strategy_template_delete_blocked_when_referenced(self):
        self._make_strategy()
        model_admin = self._model_admin(StrategyTemplate, StrategyTemplateAdmin)
        with self.assertRaises(ValidationError):
            model_admin.delete_model(request=None, obj=self.tmpl)
        self.assertTrue(StrategyTemplate.objects.filter(pk=self.tmpl.pk).exists())

    def test_slot_template_delete_blocked_by_booking_readable(self):
        """PROTECT 拦截转可读 ValidationError（裸删会冒数据库错误页）。"""
        self._make_booking(template=self.slot_tmpl)
        model_admin = self._model_admin(SlotTemplate, SlotTemplateAdmin)
        with self.assertRaises(ValidationError):
            model_admin.delete_model(request=None, obj=self.slot_tmpl)
        self.assertTrue(SlotTemplate.objects.filter(pk=self.slot_tmpl.pk).exists())


# ---------- R7-B5 借用流收口 ----------


class BorrowFlowPolishTests(Round4Fixture):
    """B5：cancel 响应经 _flow_qs 重取（标量+关联一次刷新），payload 完整。"""

    def test_cancel_returns_full_payload_with_relations(self):
        flow = self._make_flow(status="pending")
        self._auth("builder1")
        resp = self.client.post(f"/api/borrow-flows/{flow.id}/cancel")
        self.assertEqual(resp.json()["code"], CODE_OK)
        data = resp.json()["data"]
        self.assertEqual(data["status"], "cancelled")
        # 关联字段完整（refresh_from_db 清空关联缓存后 _payload 仍需逐字段可得）
        self.assertIn("borrower_name", data)
        self.assertIn("target_version_name", data)
        self.assertTrue(data["cancelled_at"])

    def test_double_create_pending_intercepted_by_unique_constraint(self):
        """uniq_pending_borrow_flow 兜底：并发重复发起 → 40903（匹配路径）。"""
        strategy = self._make_strategy()
        self._make_flow(strategy=strategy, status="pending")
        self._auth("builder1")
        resp = self.client.post("/api/borrow-flows", {
            "strategy_id": strategy.id,
            "target_branch_id": self.b26b.id,
            "new_build_time": "21:00",
            "reason": "重复发起",
        }, format="json")
        self.assertEqual(resp.status_code, 409)


# ---------- R7-B6 变更日志显式 null 留痕 ----------


class ChangeLogExplicitNullTests(Round4Fixture):
    """B6：显式 {"push_start_time": null} 清空动作必须进变更日志。"""

    def test_explicit_null_clearing_logged(self):
        s = self._make_strategy(name="A", build="22:00", push_start="20:00")
        self._auth("pm27a")
        resp = self.client.patch(
            f"/api/strategies/{s.id}", {"push_start_time": None}, format="json"
        )
        self.assertEqual(resp.json()["code"], CODE_OK)
        s.refresh_from_db()
        self.assertIsNone(s.push_start_time)
        desc = StrategyChangeLog.objects.filter(strategy=s).latest("id").change_desc
        self.assertIn("推送开始时间: 20:00→（清空）", desc)

    def test_set_value_logged_as_before(self):
        s = self._make_strategy(name="A", build="22:00")
        self._auth("pm27a")
        self.client.patch(
            f"/api/strategies/{s.id}", {"push_start_time": "21:00"}, format="json"
        )
        desc = StrategyChangeLog.objects.filter(strategy=s).latest("id").change_desc
        self.assertIn("推送开始时间: （未设置）→21:00", desc)

    def test_noop_null_not_logged_as_change(self):
        """已为空再传 null：真实值未变，不出差异行。"""
        s = self._make_strategy(name="A", build="22:00")
        self._auth("pm27a")
        self.client.patch(
            f"/api/strategies/{s.id}", {"push_start_time": None}, format="json"
        )
        desc = StrategyChangeLog.objects.filter(strategy=s).latest("id").change_desc
        self.assertNotIn("推送开始时间", desc)


# ---------- R7-B7 停用账号登录审计 ----------


class LoginDisabledAuditTests(Round4Fixture):
    """B7：凭据正确但停用 → 40301 + login_disabled 审计行，且不计失败限流。"""

    def test_disabled_account_login_audited_and_not_rate_counted(self):
        u = User.objects.create_user(username="offboard", password="123456", role="builder")
        u.is_active = False
        u.save(update_fields=["is_active"])
        client = APIClient()
        resp = client.post(
            "/api/auth/login", {"username": "offboard", "password": "123456"},
            format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(
            SecurityLog.objects.filter(action="login_disabled", username="offboard").exists()
        )
        # 不计入失败限流（密码已验证正确，锁定语义针对口令爆破）
        self.assertIsNone(cache.get("login:fail:offboard:"))


# ---------- R7-B8 contract_exception_handler 4xx 归一 ----------


class ExceptionContractTests(ConfigAwareTestCase):
    """B8：未枚举 APIException 按 status_code 归一，415 不再误标 500。"""

    def _handle(self, exc):
        return contract_exception_handler(exc, context=None)

    def test_unsupported_media_type_maps_to_422(self):
        resp = self._handle(UnsupportedMediaType("unsupported_media_type"))
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(json_loads(resp.content)["code"], CODE_UNPROCESSABLE)

    def test_client_apiexception_maps_to_422(self):
        class Custom4xx(APIException):
            status_code = 499

        resp = self._handle(Custom4xx("客户端错误"))
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(json_loads(resp.content)["code"], CODE_UNPROCESSABLE)

    def test_server_apiexception_maps_to_internal(self):
        class Custom5xx(APIException):
            status_code = 503

        resp = self._handle(Custom5xx("内部错误"))
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(json_loads(resp.content)["code"], CODE_INTERNAL)


# ---------- R7-B9 版本列表显式排序 ----------


class VersionOrderingTests(Round4Fixture):
    """B9：/weekly 与 /plan 的版本列表按 id 显式排序（不依赖 DB 返回序）。"""

    def test_weekly_versions_ordered_by_id(self):
        self._auth("builder1")
        resp = self.client.get("/api/weekly")
        ids = [v["version_id"] for v in resp.json()["data"]["versions"]]
        self.assertEqual(ids, sorted(ids))

    def test_plan_versions_ordered_by_id(self):
        self._auth("builder1")
        resp = self.client.get("/api/plan")
        ids = [v["version_id"] for v in resp.json()["data"]]
        self.assertEqual(ids, sorted(ids))


# ---------- R7-B10 seed 首块事务化 ----------


class SeedAtomicityTests(ConfigAwareTestCase):
    """B10：首块任一步失败整体回滚，重跑干净（此前中途失败后 seed 永久损坏）。"""

    def test_seed_recovers_from_mid_block_failure(self):
        # 确认干净起点（测试库无种子数据）
        self.assertFalse(User.objects.filter(username="pm27a").exists())
        with mock.patch.object(Strategy.objects, "create", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                call_command("seed", verbosity=0)
        # 首块整体回滚：用户/版本均不存在，27A 锚点未建立
        self.assertFalse(User.objects.filter(username="pm27a").exists())
        self.assertFalse(Version.objects.filter(name="27A").exists())
        # 重跑成功补全
        call_command("seed", verbosity=0)
        self.assertTrue(User.objects.filter(username="pm27a").exists())
        self.assertTrue(Version.objects.filter(name="27A").exists())
        self.assertTrue(Strategy.objects.filter(name="27A-master-晚间全量").exists())


# ---------- R7-B11 SlotTemplate start < end 不变量 ----------


class SlotTemplateInvariantTests(Round4Fixture):
    """B11：逆序/跨天模板被 DB 约束与 admin 表单双重拦截。"""

    def test_model_rejects_reversed_range(self):
        tpl = SlotTemplate(
            name="逆序窗口", start_time=time(22, 0), end_time=time(6, 0),
        )
        with self.assertRaises(Exception):
            tpl.save()

    def test_admin_save_model_rejects_reversed_range(self):
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save(update_fields=["is_staff", "is_superuser"])
        model_admin = SlotTemplateAdmin(SlotTemplate, dj_admin.site)
        tpl = SlotTemplate(
            name="跨天窗口", start_time=time(22, 0), end_time=time(6, 0),
        )
        with self.assertRaises(ValidationError):
            model_admin.save_model(request=None, obj=tpl, form=None, change=False)

    def test_valid_range_saves(self):
        tpl = SlotTemplate.objects.create(
            name="晚间窗口", start_time=time(20, 0), end_time=time(23, 0),
        )
        self.assertTrue(SlotTemplate.objects.filter(pk=tpl.pk).exists())
