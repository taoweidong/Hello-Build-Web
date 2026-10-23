"""第六轮质量优化（2026-10-24）回归测试。

每个修复项（R6-B1 ~ R6-B11）一组锁定测试，防止同类问题复发。
主题：页面精简后残留——admin 运维面收敛（R6-B1/B12）、create/update 最后两个
写入口的范式死角（R6-B2/B3）、双路径口径分裂（R6-B4/B5/B7）、审计与计数口径
（R6-B6/B8/B9）、横切助手唯一来源（R6-B10/B11）。

口径提示：
- 并发用例沿用 round3/round4/round5 技巧：先取陈旧实例再经 API/服务层制造
  「并发窗口内另一事务抢先提交」，不做线程级并发断言；
- R6-B2 的「陈旧实例」即视图层在事务外读出的实例等价物；
- R6-B5/B4 服务层直调用例锁定「服务层是双写校验的最终裁决点」承诺。
"""
from datetime import timedelta

from django.contrib import admin as dj_admin
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIClient

from .admin import SlotTemplateAdmin, StrategyAdmin, _ReadOnlyAdmin
from .errors import CODE_DUPLICATE, CODE_OK, CODE_UNPROCESSABLE
from .models import (
    AdminOpLog, BorrowFlow, SecurityLog, SlotBooking, SlotTemplate,
    Strategy, StrategyChangeLog, Strategy as StrategyModel,
)
from .services.slot_booking import create_booking, release_booking
from .services.strategies import StrategyValidationError, toggle_strategy, update_strategy
from .tests_quality_round4 import Round4Fixture

# ---------- R6-B1 / R6-B12 django-admin 运维面收敛 ----------


class AdminRegistryTests(Round4Fixture):
    """B1/B12：时段模板可管理、抢占/借用/审计面只读、策略删除走服务层拦截。"""

    def _request(self):
        request = RequestFactory().get("/")
        # django-admin 权限判定要求 is_staff（业务用户默认 False，这里仅测面板配置）
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save(update_fields=["is_staff", "is_superuser"])
        request.user = self.admin
        return request

    def test_slot_template_registered_and_manageable(self):
        """SlotTemplate 必须注册进 django-admin 且可增改（写入面唯一合法入口）。"""
        self.assertTrue(dj_admin.site.is_registered(SlotTemplate))
        model_admin = SlotTemplateAdmin(SlotTemplate, dj_admin.site)
        self.assertTrue(model_admin.has_add_permission(self._request()))

    def test_readonly_models_locked(self):
        """抢占记录/借用电子流/审计三表：增删改全禁（审计不可篡改）。"""
        model_admin = _ReadOnlyAdmin(SecurityLog, dj_admin.site)
        request = self._request()
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
        for model in (SlotBooking, BorrowFlow, AdminOpLog, StrategyChangeLog):
            self.assertIs(type(dj_admin.site._registry[model]), _ReadOnlyAdmin)

    def test_admin_delete_routes_to_service_and_intercepts_pending_flow(self):
        """StrategyAdmin 删除路由 delete_strategy：pending 借用流拦截（40903 语义）。"""
        strategy = self._make_strategy(name="待删策略")
        self._make_flow(strategy=strategy, status="pending")
        model_admin = StrategyAdmin(Strategy, dj_admin.site)
        with self.assertRaises(ValidationError):
            model_admin.delete_model(request=None, obj=strategy)
        self.assertTrue(StrategyModel.objects.filter(pk=strategy.pk).exists())

    def test_admin_delete_without_pending_flow_succeeds(self):
        strategy = self._make_strategy(name="可删策略")
        model_admin = StrategyAdmin(Strategy, dj_admin.site)
        model_admin.delete_model(request=None, obj=strategy)
        self.assertFalse(StrategyModel.objects.filter(pk=strategy.pk).exists())


# ---------- R6-B2 update_strategy 事务内重读 + update_fields ----------


class UpdateStrategyFreshReadTests(Round4Fixture):
    """B2：陈旧实例不再回写未请求字段，陈旧 enabled 不再撤销他人重新启用。"""

    def test_stale_instance_does_not_clobber_concurrent_rename(self):
        """PATCH+PATCH：改名后，持陈旧快照的「改时间」请求不得把名字写回旧值。"""
        strategy = self._make_strategy(name="A", build="22:00")
        stale = Strategy.objects.get(pk=strategy.pk)  # 事务外读出的陈旧快照
        self._auth("pm27a")
        resp = self.client.patch(
            f"/api/strategies/{strategy.id}", {"name": "A2"}, format="json"
        )
        self.assertEqual(resp.json()["code"], CODE_OK)
        # 陈旧实例只改 build_start_time
        update_strategy(stale, {"build_start_time": "23:00"}, self.pm27a)
        strategy.refresh_from_db()
        self.assertEqual(strategy.name, "A2")
        self.assertEqual(strategy.build_start_time, "23:00")

    def test_stale_instance_does_not_clobber_concurrent_push_start(self):
        """请求体未提供的字段不写列：并发设置的 push_start_time 不被陈旧 None 覆盖。"""
        strategy = self._make_strategy(name="A", build="22:00")
        stale = Strategy.objects.get(pk=strategy.pk)
        self._auth("pm27a")
        resp = self.client.patch(
            f"/api/strategies/{strategy.id}", {"push_start_time": "21:00"}, format="json"
        )
        self.assertEqual(resp.json()["code"], CODE_OK)
        update_strategy(stale, {"name": "A2"}, self.pm27a)
        strategy.refresh_from_db()
        self.assertEqual(strategy.push_start_time, "21:00")

    def test_stale_disabled_snapshot_does_not_undo_concurrent_enable(self):
        """PATCH+toggle：持陈旧 enabled=False 的请求不得把他人已重新启用的策略改回停用。"""
        strategy = self._make_strategy(name="A", build="22:00", enabled=False)
        stale = Strategy.objects.get(pk=strategy.pk)  # enabled=False 的陈旧快照
        toggle_strategy(strategy)  # 并发方完整校验后重新启用
        update_strategy(stale, {"name": "A2"}, self.pm27a)
        strategy.refresh_from_db()
        self.assertTrue(strategy.enabled)
        self.assertEqual(strategy.name, "A2")


# ---------- R6-B3 create_strategy 按结果态决定冲突校验 ----------


class CreateStrategyDisabledConflictTests(Round4Fixture):
    """B3：创建停用归档策略不再被同时段既有启用策略 40902 误拦。"""

    def test_create_disabled_strategy_with_conflicting_time_ok(self):
        self._make_strategy(name="B", build="22:00", enabled=True)
        self._auth("pm27a")
        resp = self.client.post("/api/strategies", {
            "branch_id": self.b27a.id,
            "template_id": self.tmpl.id,
            "name": "停用归档",
            "build_start_time": "22:00",
            "push_mode": "normal",
            "enabled": False,
        }, format="json")
        self.assertEqual(resp.json()["code"], CODE_OK)
        self.assertFalse(
            self.b27a.strategies.get(name="停用归档").enabled
        )

    def test_create_enabled_strategy_with_conflicting_time_still_blocked(self):
        """启用方向冲突校验完整保留（DB 约束之外的应用层拦截）。"""
        self._make_strategy(name="B", build="22:00", enabled=True)
        self._auth("pm27a")
        resp = self.client.post("/api/strategies", {
            "branch_id": self.b27a.id,
            "template_id": self.tmpl.id,
            "name": "冲突启用",
            "build_start_time": "22:00",
            "push_mode": "normal",
            "enabled": True,
        }, format="json")
        self.assertEqual(resp.json()["code"], CODE_DUPLICATE)


# ---------- R6-B4 抢占 purpose 双路径类型口径统一 ----------


class SlotPurposeTypeGuardTests(Round4Fixture):
    """B4：create 路径（序列化器与服务层）对非 str purpose 一律 42201。"""

    def _payload(self, **overrides):
        from datetime import date as date_cls

        payload = {
            "date": (timezone.localdate() + timedelta(days=1)).isoformat(),
            "template_id": self.slot_tmpl.id,
            "purpose": "回归验证",
            "version_id": self.v27a.id,
            "branch_id": self.b27a.id,
        }
        payload.update(overrides)
        return payload

    def test_api_create_int_purpose_rejected(self):
        """int 经 CharField 曾被静默强转 "12345" 放行，与改期路径（R5-B9）相反。"""
        self._auth("pm27a")
        resp = self.client.post("/api/slot-bookings", self._payload(purpose=12345), format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], CODE_UNPROCESSABLE)
        self.assertEqual(resp.json()["message"], "purpose 应为字符串")

    def test_api_create_dict_purpose_rejected(self):
        self._auth("pm27a")
        resp = self.client.post(
            "/api/slot-bookings", self._payload(purpose={"a": 1}), format="json"
        )
        self.assertEqual(resp.json()["code"], CODE_UNPROCESSABLE)

    def test_service_direct_non_str_purpose_rejected(self):
        """服务层直调路径同口径（服务层是双写校验最终裁决点）。"""
        _, error = create_booking(self.pm27a, self._payload(purpose={"a": 1}))
        self.assertEqual(error["code"], CODE_UNPROCESSABLE)
        self.assertEqual(error["message"], "purpose 应为字符串")

    def test_service_direct_missing_purpose_rejected(self):
        _, error = create_booking(self.pm27a, self._payload(purpose=None))
        self.assertEqual(error["code"], CODE_UNPROCESSABLE)

    def test_reschedule_path_still_rejects_non_str(self):
        """改期路径（R5-B9）行为不变：同资源两条写路径口径由此真正统一。"""
        booking = self._make_booking(user=self.pm27a)
        self._auth("pm27a")
        resp = self.client.patch(
            f"/api/slot-bookings/{booking.id}", {"purpose": {"a": 1}}, format="json"
        )
        self.assertEqual(resp.json()["code"], CODE_UNPROCESSABLE)


# ---------- R6-B5 release_booking 服务层 reason 守卫 ----------


class ReleaseReasonServiceGuardTests(Round4Fixture):
    """B5：释放原因服务层直调的非 str 拒绝与 200 长度守卫。"""

    def test_service_direct_overlong_reason_rejected(self):
        booking = self._make_booking(user=self.pm27a)
        _, error = release_booking(booking, self.pm27a, "长" * 201)
        self.assertEqual(error["code"], CODE_UNPROCESSABLE)
        self.assertIn("200", error["message"])

    def test_service_direct_non_str_reason_rejected(self):
        booking = self._make_booking(user=self.pm27a)
        _, error = release_booking(booking, self.pm27a, {"a": 1})
        self.assertEqual(error["code"], CODE_UNPROCESSABLE)
        self.assertEqual(error["message"], "释放原因应为字符串")

    def test_owner_release_none_reason_ok(self):
        """本人释放原因可选语义不变（None 归一为空串）。"""
        booking = self._make_booking(user=self.pm27a)
        data, error = release_booking(booking, self.pm27a, None)
        self.assertIsNone(error)
        self.assertEqual(data["status"], "released")

    def test_admin_release_other_overlong_reason_rejected(self):
        """admin 释放他人：超长原因按长度拒绝而非「需填写原因」（42201 语义族内）。"""
        booking = self._make_booking(user=self.builder)
        _, error = release_booking(booking, self.admin, "长" * 300)
        self.assertEqual(error["code"], CODE_UNPROCESSABLE)
        self.assertIn("200", error["message"])


# ---------- R6-B6 BorrowFlow.borrower PROTECT ----------


class BorrowerProtectTests(Round4Fixture):
    """B6：删除借用人不得级联抹掉电子流审计（含 approved 执行凭证）。"""

    def test_deleting_borrower_is_blocked(self):
        flow = self._make_flow(borrower=self.builder, status="approved")
        with self.assertRaises(ProtectedError):
            self.builder.delete()
        self.assertTrue(BorrowFlow.objects.filter(pk=flow.pk).exists())


# ---------- R6-B7 借用 reason 拒绝优于截断 ----------


class BorrowReasonLengthTests(Round4Fixture):
    """B7：reason 超 500 字符 42201 拒绝（此前静默截断丢字）。"""

    def _create_payload(self, reason):
        strategy = self._make_strategy(name="被借策略")
        return {
            "strategy_id": strategy.id,
            "target_branch_id": self.b26b.id,
            "new_build_time": "21:30",
            "reason": reason,
        }

    def test_overlong_reason_rejected(self):
        self._auth("pm26b")
        resp = self.client.post(
            "/api/borrow-flows", self._create_payload("需" * 501), format="json"
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], CODE_UNPROCESSABLE)
        self.assertEqual(resp.json()["message"], "借用原因长度不能超过 500 字符")

    def test_reason_at_limit_kept_intact(self):
        self._auth("pm26b")
        resp = self.client.post(
            "/api/borrow-flows", self._create_payload("需" * 500), format="json"
        )
        self.assertEqual(resp.json()["code"], CODE_OK)
        flow = BorrowFlow.objects.get(strategy__name="被借策略")
        self.assertEqual(len(flow.reason), 500)


# ---------- R6-B8 panorama todos 排除自借单 ----------


class PanoramaTodosSelfBorrowTests(Round4Fixture):
    """B8：R5-B10 回避规则下本人无法审批的「自借单」不计入待我审批。"""

    def test_pm_self_borrow_excluded_from_pending_approval(self):
        strategy = self._make_strategy(name="27A主策略")
        # pm27a 借自己版本策略到 26B：法定审批人是自己 → 永不可审批
        self._make_flow(strategy=strategy, borrower=self.pm27a, target_branch=self.b26b)
        self._auth("pm27a")
        resp = self.client.get("/api/panorama/todos")
        data = resp.json()["data"]
        self.assertEqual(data["pending_approval"], 0)
        self.assertEqual(data["my_pending_borrows"], 1)

    def test_admin_self_borrow_excluded_but_others_counted(self):
        strategy = self._make_strategy(name="27A主策略")
        # admin 自己发起的单（回避规则下永远无法自批）不计入待我审批
        self._make_flow(strategy=strategy, borrower=self.admin, target_branch=self.b26b)
        self._make_flow(
            strategy=strategy, borrower=self.builder, target_branch=self.b26b
        )
        self._auth("admin1")
        resp = self.client.get("/api/panorama/todos")
        self.assertEqual(resp.json()["data"]["pending_approval"], 1)


# ---------- R6-B9 logout 审计条件化 ----------


class LogoutAuditConditionalTests(Round4Fixture):
    """B9：匿名/垃圾 token 调用 logout 不再写审计噪音行（响应契约不变）。"""

    def _logout_rows(self):
        return SecurityLog.objects.filter(action="logout").count()

    def test_logout_without_token_writes_no_audit(self):
        self.client.credentials()
        resp = self.client.post("/api/auth/logout")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._logout_rows(), 0)

    def test_logout_with_garbage_token_writes_no_audit(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not.a.token")
        resp = self.client.post("/api/auth/logout")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._logout_rows(), 0)

    def test_logout_with_valid_token_still_writes_audit(self):
        self._auth("pm27a")
        resp = self.client.post("/api/auth/logout")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._logout_rows(), 1)
        self.assertEqual(
            SecurityLog.objects.filter(action="logout").latest("created_at").username,
            "pm27a",
        )


# ---------- R6-B10 客户端 IP 唯一来源 ----------


class ClientIpUnificationTests(Round4Fixture):
    """B10：REMOTE_ADDR 优先、XFF 取首段，security_log 与登录限流同源。"""

    def _request(self, meta_extra):
        factory = RequestFactory()
        request = factory.get("/", **meta_extra)
        request.META.pop("REMOTE_ADDR", None)
        return request

    def test_remote_addr_wins_over_xff(self):
        from .views import client_ip

        request = RequestFactory().get(
            "/", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8"
        )
        self.assertEqual(client_ip(request), "127.0.0.1")

    def test_xff_first_segment_fallback(self):
        from .views import client_ip

        request = self._request({"HTTP_X_FORWARDED_FOR": "1.2.3.4, 5.6.7.8"})
        self.assertEqual(client_ip(request), "1.2.3.4")

    def test_security_log_uses_unified_ip(self):
        from .views import security_log

        request = self._request({"HTTP_X_FORWARDED_FOR": "1.2.3.4, 5.6.7.8"})
        security_log("login_failed", username="u1", request=request)
        row = SecurityLog.objects.latest("created_at")
        self.assertIn("ip=1.2.3.4", row.detail)
        self.assertNotIn("5.6.7.8", row.detail)


# ---------- R6-B11 slot_calendar 全角月份硬化 ----------


class SlotCalendarFullWidthMonthTests(Round4Fixture):
    """B11：int() 可解析全角数字，isascii 前置硬化拦截（parse_int 同款口径）。"""

    def test_full_width_month_rejected(self):
        self._auth("pm27a")
        resp = self.client.get("/api/slot-calendar", {"month": "２０２６-１"})
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], CODE_UNPROCESSABLE)
        self.assertIn("月份格式非法", resp.json()["message"])

    def test_normal_month_still_ok(self):
        self._auth("pm27a")
        resp = self.client.get(
            "/api/slot-calendar",
            {"month": timezone.localdate().strftime("%Y-%m")},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["code"], CODE_OK)
