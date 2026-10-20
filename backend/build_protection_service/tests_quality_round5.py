"""第五轮全库质量优化（2026-10-18）回归测试。

每个修复项（R5-B1 ~ R5-B13）一组锁定测试 + 存量覆盖缺口补测，防止同类问题复发。

2026-10-20 页面精简：验证报告 / 日志中心 / 分支配置 / 系统管理（版本·模板写端点）
/admin 策略列表随页面下线，对应测试类已删；0 值过滤口径改经仍存活的
/api/strategies 列表锁定，mutex 单源用例改经 RuntimeConfig 直建制造不一致。

口径提示：
- 并发用例沿用 round3/round4 技巧：mock 抛 IntegrityError / ORM 直改终态模拟
  「并发窗口内另一事务抢先提交」，不做线程级并发断言；
- R5-B1 的「漂移冲突」场景用 ORM 直建（绕过服务层校验）模拟模板时长被改大后
  既有启用策略阶段重叠的既成事实；
- R5-B10 为决策锁定测试：禁止自借自批（admin 亦不例外），撤回申请走 cancel。
"""
from datetime import timedelta
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from .errors import (
    CODE_ASSOCIATION,
    CODE_DUPLICATE,
    CODE_FORBIDDEN,
    CODE_OK,
    CODE_UNPROCESSABLE,
)
from .models import (
    Branch,
    RuntimeConfig,
    Strategy,
)
from .services.mutex import check_build_mutex
from .services.strategies import (
    StrategyValidationError,
    _raise_conflict_or_reraise,
)
from .tests_quality_round4 import Round4Fixture

# ---------- R5-B1 停用策略 update 不再按启用口径跑冲突校验 ----------

class DisabledStrategyUpdateTests(Round4Fixture):
    """B1：update_strategy 仅在结果态为启用时跑冲突校验（对齐 toggle 语义）。

    修复前：停用策略连改名都被 40902/40901 锁死；漂移冲突策略无法经 PATCH
    停用止血（toggle 却可以），「先停用归档」逃生通道被 update 入口堵死。
    """

    def test_disabled_strategy_rename_allowed_despite_enabled_twin(self):
        """停用 A 与启用 B 同分支同刻（合法：唯一约束只限 enabled），A 改名应放行。"""
        a = self._make_strategy(name="A", build="22:00", enabled=False)
        self._make_strategy(name="B", build="22:00", enabled=True)
        self._auth("pm27a")
        resp = self.client.patch(
            f"/api/strategies/{a.id}", {"name": "A2"}, format="json"
        )
        body = resp.json()
        self.assertEqual(body["code"], CODE_OK)
        a.refresh_from_db()
        self.assertEqual(a.name, "A2")
        self.assertFalse(a.enabled)

    def test_drifted_conflict_strategy_can_be_disabled_via_patch(self):
        """ORM 直建两条阶段重叠的启用策略（模拟模板时长改大后的漂移），PATCH 停用应放行。"""
        a = self._make_strategy(name="A", build="22:00", enabled=True)
        self._make_strategy(name="B", build="22:30", enabled=True)
        self._auth("pm27a")
        resp = self.client.patch(
            f"/api/strategies/{a.id}", {"enabled": False}, format="json"
        )
        self.assertEqual(resp.json()["code"], CODE_OK)
        a.refresh_from_db()
        self.assertFalse(a.enabled)

    def test_format_validation_still_runs_when_disabled(self):
        """停用策略的格式校验（HH:MM）恒跑：非法时间仍 42201。"""
        a = self._make_strategy(name="A", build="22:00", enabled=False)
        self._auth("pm27a")
        resp = self.client.patch(
            f"/api/strategies/{a.id}", {"build_start_time": "25:00"}, format="json"
        )
        self.assertEqual(resp.json()["code"], CODE_UNPROCESSABLE)

    def test_enable_direction_still_validated(self):
        """结果态为启用时冲突校验完整保留：停用 A 重新启用撞同刻启用 B → 40902。"""
        a = self._make_strategy(name="A", build="22:00", enabled=False)
        self._make_strategy(name="B", build="22:00", enabled=True)
        self._auth("pm27a")
        resp = self.client.patch(
            f"/api/strategies/{a.id}", {"enabled": True}, format="json"
        )
        self.assertEqual(resp.json()["code"], CODE_DUPLICATE)


# ---------- R5-B2 策略冲突 IntegrityError 助手双格式匹配 ----------

class StrategyConflictPrecisionTests(TestCase):
    """B2：_raise_conflict_or_reraise 命中 SQLite 字段名式与 PG 约束名式（对齐 R4-B8 slot 版）。"""

    SQLITE_MSG = "UNIQUE constraint failed: strategy.branch_id, strategy.build_start_time"
    PG_MSG = (
        'duplicate key value violates unique constraint '
        '"build_protection_service_strat_uniq_active_strategy_branch_time"'
    )

    def test_sqlite_message_hits_40902(self):
        with self.assertRaises(StrategyValidationError) as cm:
            _raise_conflict_or_reraise(
                IntegrityError(self.SQLITE_MSG), None, "22:00"
            )
        self.assertEqual(cm.exception.code, CODE_DUPLICATE)

    def test_postgres_constraint_name_hits_40902(self):
        with self.assertRaises(StrategyValidationError) as cm:
            _raise_conflict_or_reraise(IntegrityError(self.PG_MSG), None, "22:00")
        self.assertEqual(cm.exception.code, CODE_DUPLICATE)

    def test_other_constraint_reraises(self):
        with self.assertRaises(IntegrityError):
            _raise_conflict_or_reraise(
                IntegrityError("UNIQUE constraint failed: strategy.name"), None, "22:00"
            )


# ---------- R5-B9 改期 purpose 字段级类型守卫 ----------

class ReschedulePurposeGuardTests(Round4Fixture):
    """B9：非 str purpose 一律 42201 拒绝，不再 repr 化入库（与 create 路径口径统一）。"""

    def setUp(self):
        super().setUp()
        self.booking = self._make_booking(user=self.builder)
        self._auth("builder1")

    def test_dict_purpose_rejected(self):
        resp = self.client.patch(
            f"/api/slot-bookings/{self.booking.id}",
            {"purpose": {"a": 1}}, format="json",
        )
        body = resp.json()
        self.assertEqual(body["code"], CODE_UNPROCESSABLE)
        self.booking.refresh_from_db()
        self.assertNotIn("{'a'", self.booking.purpose)

    def test_int_purpose_rejected(self):
        resp = self.client.patch(
            f"/api/slot-bookings/{self.booking.id}",
            {"purpose": 123}, format="json",
        )
        self.assertEqual(resp.json()["code"], CODE_UNPROCESSABLE)

    def test_valid_purpose_still_works(self):
        resp = self.client.patch(
            f"/api/slot-bookings/{self.booking.id}",
            {"purpose": "新的合法用途说明"}, format="json",
        )
        self.assertEqual(resp.json()["code"], CODE_OK)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.purpose, "新的合法用途说明")

    def test_omitted_purpose_keeps_original(self):
        """缺省（None）沿用原值语义不变：只改日期不带 purpose → 原 purpose 保留。"""
        tomorrow = (timezone.localdate() + timedelta(days=2)).isoformat()
        resp = self.client.patch(
            f"/api/slot-bookings/{self.booking.id}",
            {"date": tomorrow}, format="json",
        )
        self.assertEqual(resp.json()["code"], CODE_OK)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.purpose, "日常构建窗口占用")


# ---------- R5-B10 借用审批回避规则（决策锁定） ----------

class BorrowSelfApprovalTests(Round4Fixture):
    """B10：禁止自借自批（admin 亦不例外）；撤回申请走 cancel 端点。"""

    def _create_flow(self, borrower_login, strategy, target_branch=None):
        self._auth(borrower_login)
        resp = self.client.post(
            "/api/borrow-flows",
            {
                "strategy_id": strategy.id,
                "target_branch_id": (target_branch or self.b26b).id,
                "new_build_time": "21:30",
                "reason": "借用原因说明",
            },
            format="json",
        )
        body = resp.json()
        self.assertEqual(body["code"], CODE_OK)
        return body["data"]["id"]

    def test_pm_cannot_approve_own_flow(self):
        s = self._make_strategy(name="被借策略", build="22:00")
        fid = self._create_flow("pm27a", s)  # pm27a 借自己版本的策略（合法发起）
        self._auth("pm27a")
        resp = self.client.post(f"/api/borrow-flows/{fid}/approve", {}, format="json")
        body = resp.json()
        self.assertEqual(body["code"], CODE_FORBIDDEN)
        self.assertIn("自己发起", body["message"])

    def test_pm_cannot_reject_own_flow(self):
        s = self._make_strategy(name="被借策略", build="22:00")
        fid = self._create_flow("pm27a", s)
        self._auth("pm27a")
        resp = self.client.post(
            f"/api/borrow-flows/{fid}/reject", {"comment": "自我驳回"}, format="json"
        )
        self.assertEqual(resp.json()["code"], CODE_FORBIDDEN)

    def test_admin_cannot_approve_own_flow(self):
        """admin 亦不例外（对照 cancel 端点既定审计取向）。"""
        s = self._make_strategy(name="被借策略", build="22:00")
        fid = self._create_flow("admin1", s)
        self._auth("admin1")
        resp = self.client.post(f"/api/borrow-flows/{fid}/approve", {}, format="json")
        self.assertEqual(resp.json()["code"], CODE_FORBIDDEN)

    def test_admin_can_approve_others_flow(self):
        """回避规则不误伤：他人发起的电子流 admin 仍可审批通过。"""
        s = self._make_strategy(name="被借策略", build="22:00")
        fid = self._create_flow("builder1", s)
        self._auth("admin1")
        resp = self.client.post(f"/api/borrow-flows/{fid}/approve", {}, format="json")
        self.assertEqual(resp.json()["code"], CODE_OK)
        # 审批通过在目标分支实际创建借用策略
        self.assertTrue(
            Strategy.objects.filter(branch=self.b26b, build_start_time="21:30").exists()
        )

    def test_owner_can_still_cancel_own_flow(self):
        """撤回自己的申请走 cancel（回避规则不堵死借用人出口）。"""
        s = self._make_strategy(name="被借策略", build="22:00")
        fid = self._create_flow("pm27a", s)
        self._auth("pm27a")
        resp = self.client.post(f"/api/borrow-flows/{fid}/cancel", {}, format="json")
        self.assertEqual(resp.json()["code"], CODE_OK)


# ---------- R5-B11 check_build_mutex 构建时长单源 ----------

class MutexBuildMinSourceTests(Round4Fixture):
    """B11：目标区间与既有策略区间统一用参数 build_min，不再函数内重读 config。"""

    def test_param_single_source(self):
        RuntimeConfig.objects.create(key="build_minutes", value=120)  # 制造 config 与参数不一致
        dev = Branch.objects.create(version=self.v27a, name="dev")
        self._make_strategy(branch=dev, name="既有", build="21:00", enabled=True)
        # 参数 30：目标 [22:00,22:30]，既有 [21:00,21:30] → 不重叠。
        # 修复前既有区间用 config 120 → [21:00,23:00] 误报互斥。
        self.assertEqual(check_build_mutex(self.v27a.id, "22:00", 30), [])
        # 参数 120：目标 [22:00,24:00] 与既有 [21:00,23:00] 重叠 → 命中 1 条
        hits = check_build_mutex(self.v27a.id, "22:00", 120)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["strategy"], "dev/既有")


# ---------- R5-B13 过滤参数 0 值 fail-closed ----------

class FilterZeroSemanticsTests(Round4Fixture):
    """B13：version_id/branch_id 的 0 值统一「按 0 过滤 → 空集」。

    2026-10-20：admin 策略列表与 executions 列表端点已随页面下线，
    口径改经仍存活的 /api/strategies 列表过滤锁定。
    """

    def setUp(self):
        super().setUp()
        self._make_strategy(name="S1", build="22:00")
        self._auth("admin1")

    def test_strategy_list_zero_filters_empty(self):
        for qs in ("version_id=0", "branch_id=0", "version_id=0&branch_id=0"):
            body = self.client.get(f"/api/strategies?{qs}").json()
            self.assertEqual(body["code"], CODE_OK, qs)
            self.assertEqual(body["data"], [], qs)

    def test_strategy_list_valid_filter_unaffected(self):
        body = self.client.get(f"/api/strategies?version_id={self.v27a.id}").json()
        self.assertEqual(body["code"], CODE_OK)
        self.assertEqual(len(body["data"]), 1)

    def test_strategy_list_invalid_param_still_42201(self):
        body = self.client.get("/api/strategies?version_id=abc").json()
        self.assertEqual(body["code"], CODE_UNPROCESSABLE)
