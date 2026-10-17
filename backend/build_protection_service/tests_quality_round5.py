"""第五轮全库质量优化（2026-10-18）回归测试。

对应 docs/code-quality-assessment-2026-10-18.md 与
docs/superpowers/specs/2026-10-18-code-quality-optimization-round5-design.md：
每个修复项（R5-B1 ~ R5-B13）一组锁定测试 + 存量覆盖缺口补测，防止同类问题复发。

口径提示：
- 并发用例沿用 round3/round4 技巧：mock 抛 IntegrityError / ORM 直改终态模拟
  「并发窗口内另一事务抢先提交」，不做线程级并发断言；
- R5-B1 的「漂移冲突」场景用 ORM 直建（绕过服务层校验）模拟模板时长被改大后
  既有启用策略阶段重叠的既成事实；
- R5-B10 为决策锁定测试：禁止自借自批（admin 亦不例外），撤回申请走 cancel。
"""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
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
    BranchPermission,
    BranchProject,
    Project,
    ReportRevisionLog,
    SecurityLog,
    Strategy,
    StrategyTemplate,
    VerificationReport,
)
from .services.config import set_config
from .services.mutex import check_build_mutex
from .services.report_service import ReportService
from .services.strategies import (
    StrategyValidationError,
    _raise_conflict_or_reraise,
)
from .tests_quality_round4 import Round4Fixture

User = get_user_model()


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

    def test_admin_entry_same_semantics(self):
        """admin PATCH 入口与 PM 入口共用服务层，同语义放行停用策略改名。"""
        a = self._make_strategy(name="A", build="22:00", enabled=False)
        self._make_strategy(name="B", build="22:00", enabled=True)
        self._auth("admin1")
        resp = self.client.patch(
            f"/api/admin/strategies/{a.id}", {"name": "A3"}, format="json"
        )
        self.assertEqual(resp.json()["code"], CODE_OK)

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


# ---------- R5-B3 报告域 username 快照字段扩到 150 ----------

class LongUsernameReportTests(TestCase):
    """B3：101-150 字符用户名建报告/发布/留痕全链路无损（迁 PG 不再 DataError）。"""

    def test_150_char_username_full_lifecycle(self):
        uname = "u" * 150
        user = User.objects.create_user(username=uname, password="123456", role="builder")
        report = ReportService.create(uname, {
            "title": "长用户名报告", "conclusion": "pass", "summary": "内容",
            "version_name": "", "strategy_name": "", "environment": "",
            "risks": "", "remark": "",
        })
        self.assertEqual(report.created_by_username, uname)
        ReportService.update(uname, report, {"remark": "备注更新"})
        ReportService.publish(uname, report)
        report.refresh_from_db()
        self.assertEqual(report.created_by_username, uname)
        self.assertEqual(report.status, "published")
        logs = ReportRevisionLog.objects.filter(report_id=report.id)
        self.assertTrue(logs.exists())
        for log in logs:
            self.assertEqual(log.operator_username, uname)

    def test_field_max_length_is_150(self):
        """模型口径锁定：两快照字段与 User.username（AbstractUser 上限 150）对齐。"""
        width = VerificationReport._meta.get_field("created_by_username").max_length
        op_width = ReportRevisionLog._meta.get_field("operator_username").max_length
        user_width = User._meta.get_field("username").max_length
        self.assertEqual(width, user_width)
        self.assertEqual(op_width, user_width)


# ---------- R5-B4 报告快照字段未变化不重跑活校验 ----------

class ReportSnapshotEditTests(Round4Fixture):
    """B4：策略改名/删除后报告仍可 PUT 编辑；配对/存在性校验仅在快照字段变化时触发。"""

    def _create_report(self, strategy_name="策略S"):
        payload = {
            "title": "报告1", "conclusion": "pass", "summary": "验证内容",
            "version_name": "27A", "strategy_name": strategy_name,
            "environment": "测试环境", "risks": "", "remark": "",
        }
        resp = self.client.post("/api/reports", payload, format="json")
        self.assertEqual(resp.json()["code"], CODE_OK)
        return resp.json()["data"]["id"], payload

    def setUp(self):
        super().setUp()
        self.strategy = self._make_strategy(name="策略S", build="22:00")
        self._auth("tester1")
        self.rid, self.payload = self._create_report()

    def test_edit_remark_after_strategy_renamed(self):
        """策略被 PM 改名（常规操作）后，只改 remark 的 PUT 应放行。"""
        self.strategy.name = "策略S-新"
        self.strategy.save()
        resp = self.client.put(
            f"/api/reports/{self.rid}",
            {**self.payload, "remark": "改一个错别字"},
            format="json",
        )
        self.assertEqual(resp.json()["code"], CODE_OK)

    def test_edit_remark_after_strategy_deleted(self):
        """策略被删除后，快照未动的 PUT 仍放行（publish 路径本就不重跑，口径统一）。"""
        self.strategy.delete()
        resp = self.client.put(
            f"/api/reports/{self.rid}",
            {**self.payload, "remark": "策略已删仍可编辑"},
            format="json",
        )
        self.assertEqual(resp.json()["code"], CODE_OK)

    def test_snapshot_change_still_validated(self):
        """快照字段变化时存在性校验保留：改成不存在的策略 → 42201。"""
        resp = self.client.put(
            f"/api/reports/{self.rid}",
            {**self.payload, "strategy_name": "不存在的策略"},
            format="json",
        )
        self.assertEqual(resp.json()["code"], CODE_UNPROCESSABLE)

    def test_snapshot_change_pairing_still_validated(self):
        """快照字段变化时配对校验保留：只清 version_name 留 strategy_name → 42201。"""
        resp = self.client.put(
            f"/api/reports/{self.rid}",
            {**self.payload, "version_name": ""},
            format="json",
        )
        self.assertEqual(resp.json()["code"], CODE_UNPROCESSABLE)

    def test_snapshot_change_to_valid_pair_allowed(self):
        """快照字段变为另一合法配对 → 校验通过。"""
        other = self._make_strategy(name="策略T", build="20:00")
        resp = self.client.put(
            f"/api/reports/{self.rid}",
            {**self.payload, "strategy_name": other.name},
            format="json",
        )
        self.assertEqual(resp.json()["code"], CODE_OK)


# ---------- R5-B5 ReportService.update 精准字段保存 ----------

class ReportUpdateFieldsTests(TestCase):
    """B5：陈旧实例 update 不回滚并发 publish 已提交的 status/publish_count/published_at。"""

    DATA = {
        "title": "并发报告", "conclusion": "pass", "summary": "内容",
        "version_name": "", "strategy_name": "", "environment": "",
        "risks": "", "remark": "",
    }

    def test_stale_update_does_not_rollback_publish(self):
        report = ReportService.create("tester1", dict(self.DATA))
        stale = VerificationReport.objects.get(pk=report.pk)  # 读出后进入「陈旧窗口」
        ReportService.publish("tester1", report)  # 窗口期内发布提交
        ReportService.update("tester1", stale, {"remark": "迟到修改"})
        fresh = VerificationReport.objects.get(pk=report.pk)
        self.assertEqual(fresh.status, "published")
        self.assertEqual(fresh.publish_count, 1)
        self.assertIsNotNone(fresh.published_at)
        self.assertEqual(fresh.remark, "迟到修改")

    def test_double_publish_count_atomic(self):
        """发布两次计数恰为 2（F() 自增既有实现补锁定）。"""
        report = ReportService.create("tester1", dict(self.DATA))
        ReportService.publish("tester1", report)
        ReportService.publish("tester1", report)
        report.refresh_from_db()
        self.assertEqual(report.publish_count, 2)


# ---------- R5-B6 /admin/logs/<kind> GET-only 守卫 ----------

class AdminLogsMethodGuardTests(Round4Fixture):
    """B6：R3-B16「读端点仅 GET」约定的唯一漏网点位补守卫。"""

    def test_non_get_rejected_42201(self):
        self._auth("admin1")
        for kind in ("operations", "security"):
            url = f"/api/admin/logs/{kind}"
            self.assertEqual(
                self.client.post(url, {}, format="json").json()["code"],
                CODE_UNPROCESSABLE,
            )
            self.assertEqual(self.client.delete(url).json()["code"], CODE_UNPROCESSABLE)
            self.assertEqual(
                self.client.put(url, {}, format="json").json()["code"],
                CODE_UNPROCESSABLE,
            )

    def test_get_still_ok(self):
        self._auth("admin1")
        for kind in ("operations", "security"):
            body = self.client.get(f"/api/admin/logs/{kind}").json()
            self.assertEqual(body["code"], CODE_OK)


class LogListCapTests(Round4Fixture):
    """存量缺口：日志列表 200 条截断上限的边界锁定（第 201 条不返回）。"""

    def test_security_logs_capped_at_200(self):
        SecurityLog.objects.bulk_create(
            [SecurityLog(username="u", action="login_fail", detail="x") for _ in range(205)]
        )
        self._auth("admin1")
        data = self.client.get("/api/admin/logs/security").json()["data"]
        self.assertEqual(len(data), 200)


# ---------- R5-B7 branch_config 两处 check-then-create 并发兜底 ----------

class BranchConfigRaceTests(Round4Fixture):
    """B7：permissions/projects 并发撞 unique 由 IntegrityError 兜底转 40903（R4-B17 同款）。"""

    def test_permissions_race_returns_40903(self):
        self._auth("admin1")
        url = f"/api/branches/{self.b27a.id}/permissions"
        payload = {"user_id": self.builder.id, "role": "VIEWER"}
        with mock.patch.object(
            BranchPermission.objects, "update_or_create",
            side_effect=IntegrityError("UNIQUE constraint failed: branch_id, user_id"),
        ):
            resp = self.client.post(url, payload, format="json")
        self.assertEqual(resp.json()["code"], CODE_ASSOCIATION)
        self.assertEqual(resp.status_code, 409)

    def test_projects_race_returns_40903(self):
        project = Project.objects.create(name="工程X")
        self._auth("admin1")
        url = f"/api/branches/{self.b27a.id}/projects"
        with mock.patch.object(
            BranchProject.objects, "create",
            side_effect=IntegrityError("UNIQUE constraint failed: branch_id, project_id"),
        ):
            resp = self.client.post(url, {"project_id": project.id}, format="json")
        self.assertEqual(resp.json()["code"], CODE_ASSOCIATION)
        self.assertEqual(resp.status_code, 409)

    def test_happy_paths_unaffected(self):
        """兜底不误伤正常路径：首次授权/关联仍成功。"""
        self._auth("admin1")
        project = Project.objects.create(name="工程Y")
        resp = self.client.post(
            f"/api/branches/{self.b27a.id}/projects",
            {"project_id": project.id}, format="json",
        )
        self.assertEqual(resp.json()["code"], CODE_OK)
        resp = self.client.post(
            f"/api/branches/{self.b27a.id}/permissions",
            {"user_id": self.builder.id, "role": "OPERATOR"}, format="json",
        )
        self.assertEqual(resp.json()["code"], CODE_OK)


# ---------- R5-B8 版本 PM 占用文案 ----------

class VersionPmOccupiedMessageTests(Round4Fixture):
    """B8：create/update 撞 OneToOne（PM 已被占用）不再误报「版本号已存在」。"""

    def test_create_version_with_bound_pm_message(self):
        self._auth("admin1")
        resp = self.client.post(
            "/api/admin/versions",
            {"name": "28A", "pm_user_id": self.pm27a.id},  # pm27a 已绑定 v27a
            format="json",
        )
        body = resp.json()
        self.assertEqual(body["code"], CODE_DUPLICATE)
        self.assertIn("PM", body["message"])

    def test_update_version_to_bound_pm_rejected(self):
        """存量缺口：update_version 的 IntegrityError 兜底分支锁定。"""
        self._auth("admin1")
        resp = self.client.put(
            f"/api/admin/versions/{self.v26b.id}",
            {"pm_user_id": self.pm27a.id},
            format="json",
        )
        body = resp.json()
        self.assertEqual(body["code"], CODE_DUPLICATE)
        self.assertIn("PM", body["message"])


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
        set_config("build_minutes", 120)  # 制造 config 与参数不一致
        dev = Branch.objects.create(version=self.v27a, name="dev")
        self._make_strategy(branch=dev, name="既有", build="21:00", enabled=True)
        # 参数 30：目标 [22:00,22:30]，既有 [21:00,21:30] → 不重叠。
        # 修复前既有区间用 config 120 → [21:00,23:00] 误报互斥。
        self.assertEqual(check_build_mutex(self.v27a.id, "22:00", 30), [])
        # 参数 120：目标 [22:00,24:00] 与既有 [21:00,23:00] 重叠 → 命中 1 条
        hits = check_build_mutex(self.v27a.id, "22:00", 120)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["strategy"], "dev/既有")


# ---------- R5-B12 模板时长变更联动告警 ----------

class TemplateDurationWarningTests(Round4Fixture):
    """B12：update_template 时长变更后附 warnings（引用该模板的启用策略新出现阶段重叠）。"""

    def setUp(self):
        super().setUp()
        self.tpl2 = StrategyTemplate.objects.create(
            name="短冒烟", smoke_minutes=60, analysis_minutes=30
        )
        # 同分支两条启用策略（默认 build 30 分钟）：
        # A: build 10:00-10:30, smoke 10:30-11:30, analysis 11:30-12:00
        # B: build 12:00-12:30, smoke 12:30-13:30 → 初始无重叠
        self.sa = self._make_strategy(
            branch=self.b27a, name="A", build="10:00", template=self.tpl2
        )
        self.sb = self._make_strategy(
            branch=self.b27a, name="B", build="12:00", template=self.tpl2
        )
        self._auth("admin1")

    def test_duration_increase_returns_warnings(self):
        resp = self.client.patch(
            f"/api/admin/templates/{self.tpl2.id}",
            {"smoke_minutes": 180}, format="json",
        )
        body = resp.json()
        self.assertEqual(body["code"], CODE_OK)
        warnings = body["data"]["warnings"]
        self.assertEqual(len(warnings), 1)
        self.assertEqual({warnings[0]["first"], warnings[0]["second"]}, {"A", "B"})
        self.assertEqual(warnings[0]["branch"], "master")

    def test_duration_change_without_conflict_empty_warnings(self):
        resp = self.client.patch(
            f"/api/admin/templates/{self.tpl2.id}",
            {"smoke_minutes": 61}, format="json",
        )
        body = resp.json()
        self.assertEqual(body["code"], CODE_OK)
        self.assertEqual(body["data"]["warnings"], [])

    def test_non_duration_change_has_no_warnings_key(self):
        resp = self.client.patch(
            f"/api/admin/templates/{self.tpl2.id}",
            {"description": "只改描述"}, format="json",
        )
        body = resp.json()
        self.assertEqual(body["code"], CODE_OK)
        self.assertNotIn("warnings", body["data"])


# ---------- R5-B13 过滤参数 0 值 fail-closed ----------

class FilterZeroSemanticsTests(Round4Fixture):
    """B13：version_id/branch_id/strategy_id 的 0 值统一「按 0 过滤 → 空集」。"""

    def setUp(self):
        super().setUp()
        self._make_strategy(name="S1", build="22:00")
        self._auth("admin1")

    def test_strategy_list_zero_filters_empty(self):
        for qs in ("version_id=0", "branch_id=0", "version_id=0&branch_id=0"):
            body = self.client.get(f"/api/admin/strategies?{qs}").json()
            self.assertEqual(body["code"], CODE_OK, qs)
            self.assertEqual(body["data"], [], qs)

    def test_strategy_list_valid_filter_unaffected(self):
        body = self.client.get(f"/api/admin/strategies?version_id={self.v27a.id}").json()
        self.assertEqual(body["code"], CODE_OK)
        self.assertEqual(len(body["data"]), 1)

    def test_strategy_list_invalid_param_still_42201(self):
        body = self.client.get("/api/admin/strategies?version_id=abc").json()
        self.assertEqual(body["code"], CODE_UNPROCESSABLE)

    def test_executions_zero_filter_consistent(self):
        """executions 的 strategy_id=0 → 空集语义保持（两端点口径一致）。"""
        body = self.client.get("/api/executions?strategy_id=0").json()
        self.assertEqual(body["code"], CODE_OK)
        self.assertEqual(body["data"], [])
