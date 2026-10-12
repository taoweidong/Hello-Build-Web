"""第三轮全库质量优化（2026-10-13）回归测试。

对应 docs/code-quality-assessment-2026-10-13.md 与
docs/superpowers/specs/2026-10-13-code-quality-optimization-round3-design.md：
每个修复项（R3-B1 ~ R3-B18）一组锁定测试，防止同类问题复发。

口径提示：
- 时间断言基准：已知 UTC 时刻 2026-10-13T02:00:00Z → 上海墙钟 2026-10-13T10:00:00；
- 并发用例沿用 tests_strategy_concurrency 的技巧：用 ORM 直改终态/持有旧快照
  模拟「并发窗口内另一事务抢先提交」，不做线程级并发断言（测试库为内存库）。
"""
import json
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.exceptions import APIException, MethodNotAllowed, Throttled
from rest_framework.test import APIClient

from .api import ok as api_ok
from .errors import CODE_OK
from .exception_handlers import contract_exception_handler
from .models import (
    AdminOpLog,
    BorrowFlow,
    Branch,
    BranchProject,
    ExecutionRound,
    Instance,
    Project,
    ReportRevisionLog,
    RevokedToken,
    SecurityLog,
    SlotBooking,
    SlotTemplate,
    Strategy,
    StrategyChangeLog,
    StrategyTemplate,
    Version,
)
from .services.branch_config import start_instance as svc_start
from .services.mutex import check_build_mutex
from .services.report_service import ReportService
from .services.slot_booking import (
    build_slot_calendar,
    release_booking,
    template_applies_on,
)
from .services.strategies import (
    StrategyValidationError,
    toggle_strategy as svc_toggle,
    update_strategy as svc_update,
)
from .services.timeline import build_timeline
from .tests import ConfigAwareTestCase
from .views import body_str, fmt_dt, paginate_qs, parse_body, security_log

User = get_user_model()

# 已知 UTC 时刻与对应上海墙钟（Asia/Shanghai = UTC+8，无夏令时）
KNOWN_UTC = datetime(2026, 10, 13, 2, 0, 0, tzinfo=dt_timezone.utc)
KNOWN_SHANGHAI = "2026-10-13T10:00:00"


class Round3Fixture(ConfigAwareTestCase):
    """共享夹具：双版本双分支 + 模板 + 各角色用户 + 登录助手。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin1", password="123456", role="admin")
        self.pm27a = User.objects.create_user(username="pm27a", password="123456", role="pm")
        self.pm27b = User.objects.create_user(username="pm27b", password="123456", role="pm")
        self.builder = User.objects.create_user(username="builder1", password="123456", role="builder")
        self.tester = User.objects.create_user(username="tester1", password="123456", role="tester")
        self.v27a = Version.objects.create(name="27A", pm_user=self.pm27a, status="active")
        self.v27b = Version.objects.create(name="27B", pm_user=self.pm27b, status="active")
        self.b27a = Branch.objects.create(version=self.v27a, name="master")
        self.b27b = Branch.objects.create(version=self.v27b, name="master")
        self.tmpl = StrategyTemplate.objects.create(
            name="晚间全量冒烟", smoke_minutes=480, analysis_minutes=120
        )

    def _token(self, username):
        resp = self.client.post(
            "/api/auth/login", {"username": username, "password": "123456"}, format="json"
        )
        return resp.json()["data"]["token"]

    def _auth(self, username):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._token(username)}")

    def _make_strategy(self, branch=None, name="策略A", build="22:00", enabled=True,
                       push_mode="normal", push_start=None, template=None):
        return Strategy.objects.create(
            branch=branch or self.b27a, template=template or self.tmpl, name=name,
            build_start_time=build, push_mode=push_mode, push_start_time=push_start,
            enabled=enabled, created_by=self.pm27a,
        )


# ---------- R3-B1 停用用户存量 token → 40100 ----------

class DisabledUserTokenTests(Round3Fixture):
    """B-P1-1：admin 停用/删除用户后，其存量 token 必须走 40100 未认证路径。

    旧行为：simplejwt get_user 对停用/不存在用户抛 AuthenticationFailed，
    auth.py 未捕获 → 函数视图裸 500、ViewSet 归入 50000，前端拿不到 40100 不跳登录。
    """

    def _login_builder_token(self):
        return self._token("builder1")

    def test_function_view_returns_40100_after_disable(self):
        token = self._login_builder_token()
        self.builder.is_active = False
        self.builder.save()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = self.client.get("/api/strategies")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], 40100)

    def test_viewset_returns_40100_after_disable(self):
        token = self._login_builder_token()
        self.builder.is_active = False
        self.builder.save()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = self.client.get("/api/reports")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], 40100)

    def test_deleted_user_token_returns_40100(self):
        """用户被删除后存量 token 同样 40100（get_user 抛 user_not_found）。"""
        token = self._login_builder_token()
        self.builder.delete()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = self.client.get("/api/strategies")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], 40100)

    def test_malformed_auth_header_returns_40100(self):
        """Authorization 头形态非法（三段式）→ 40100 而非 500。"""
        self.client.credentials(HTTP_AUTHORIZATION="Bearer a b")
        resp = self.client.get("/api/strategies")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], 40100)


# ---------- R3-B2 非字符串 body 字段类型守卫 ----------

class BodyStrHelperTests(ConfigAwareTestCase):
    """body_str 共享助手单元口径。"""

    def test_non_str_falls_back_to_default(self):
        for bad in (123, 12.5, True, ["a"], {"a": 1}, None):
            self.assertEqual(body_str({"k": bad}, "k"), "", msg=repr(bad))

    def test_missing_key_returns_default(self):
        self.assertEqual(body_str({}, "k"), "")
        self.assertEqual(body_str({}, "k", default="兜底"), "兜底")

    def test_strip_and_max_len(self):
        self.assertEqual(body_str({"k": "  abc  "}, "k"), "abc")
        self.assertEqual(body_str({"k": "  abc  "}, "k", strip=False), "  abc  ")
        self.assertEqual(body_str({"k": "abcdef"}, "k", max_len=3), "abc")

    def test_non_dict_body_is_defensive(self):
        self.assertEqual(body_str([1, 2], "k"), "")


class ParseBodyNonDictTests(ConfigAwareTestCase):
    """parse_body 对合法 JSON 非对象（数组/字符串/null/数字）归一为 {}。"""

    def _parse(self, raw: str):
        req = RequestFactory().post("/", data=raw, content_type="application/json")
        return parse_body(req)

    def test_non_dict_json_normalized(self):
        for raw in ('[1,2]', '"str"', "null", "42", "true"):
            self.assertEqual(self._parse(raw), {}, msg=raw)

    def test_invalid_json_still_empty(self):
        self.assertEqual(self._parse("{oops"), {})

    def test_dict_passthrough(self):
        self.assertEqual(self._parse('{"a": 1}'), {"a": 1})


class NonStringBodyGuardTests(Round3Fixture):
    """B-P1-2：各入口传数字/数组/对象/null → 42201 或既有校验码，绝无 500。"""

    def test_login_non_string_credentials_422(self):
        for payload in (
            {"username": 123, "password": "123456"},
            {"username": "pm27a", "password": 456},
            {"username": ["a"], "password": {"b": 1}},
        ):
            resp = self.client.post("/api/auth/login", payload, format="json")
            self.assertEqual(resp.status_code, 422, msg=repr(payload))
            self.assertEqual(resp.json()["code"], 42201, msg=repr(payload))

    def test_login_non_dict_body_422(self):
        for raw in ("[1,2]", '"str"', "null"):
            resp = self.client.post("/api/auth/login", data=raw, content_type="application/json")
            self.assertEqual(resp.status_code, 422, msg=raw)
            self.assertEqual(resp.json()["code"], 42201, msg=raw)

    def test_strategies_non_dict_body_422(self):
        """普通函数视图：非对象 body 按缺参处理（旧行为 body.get 冒 500）。"""
        self._auth("pm27a")
        for raw in ("[1,2]", '"str"', "null", "42"):
            resp = self.client.post("/api/strategies", data=raw, content_type="application/json")
            self.assertEqual(resp.status_code, 422, msg=raw)
            self.assertEqual(resp.json()["code"], 42201, msg=raw)

    def test_borrow_flow_create_non_string_fields(self):
        s = self._make_strategy()
        self._auth("builder1")
        # new_build_time 传数字 → 归一 "" → 既有 HH:MM 校验 42201
        resp = self.client.post("/api/borrow-flows", {
            "strategy_id": s.id, "target_branch_id": self.b27b.id,
            "new_build_time": 2130, "reason": "借用",
        }, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        # reason 传对象 → 归一 ""（reason 可空，创建成功且不 500）
        resp = self.client.post("/api/borrow-flows", {
            "strategy_id": s.id, "target_branch_id": self.b27b.id,
            "new_build_time": "21:30", "reason": {"a": 1},
        }, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertEqual(resp.json()["data"]["reason"], "")

    def test_borrow_flow_reject_non_string_comment_422(self):
        s = self._make_strategy()
        flow = BorrowFlow.objects.create(
            strategy=s, borrower=self.builder, target_branch=self.b27b,
            new_build_time="21:30",
        )
        self._auth("pm27a")
        resp = self.client.post(
            f"/api/borrow-flows/{flow.id}/reject", {"comment": 12345}, format="json"
        )
        # 非字符串归一 "" → 走既有"驳回必须填写审批意见" 42201
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_branch_create_non_string_fields(self):
        self._auth("admin1")
        resp = self.client.post("/api/branches", {
            "version_id": self.v27a.id, "name": 123,
        }, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        # repository_url/description 非字符串 → 归一 ""，创建成功
        resp = self.client.post("/api/branches", {
            "version_id": self.v27a.id, "name": "TR9",
            "repository_url": ["x"], "description": {"a": 1},
        }, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertEqual(resp.json()["data"]["repository_url"], "")
        self.assertEqual(resp.json()["data"]["description"], "")

    def test_branch_create_non_dict_body_422(self):
        self._auth("admin1")
        resp = self.client.post("/api/branches", data="[1,2]", content_type="application/json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_projects_create_non_string_fields(self):
        self._auth("builder1")
        resp = self.client.post("/api/projects", {"name": 123}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        resp = self.client.post("/api/projects", {
            "name": "工程X", "repository_url": 123, "description": ["d"],
        }, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertEqual(resp.json()["data"]["repository_url"], "")
        self.assertEqual(resp.json()["data"]["description"], "")

    def test_branch_projects_action_non_dict_body_422(self):
        self._auth("admin1")
        resp = self.client.post(
            f"/api/branches/{self.b27a.id}/projects", data="[1]", content_type="application/json"
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_report_publish_non_string_screenshot_422(self):
        report = ReportService.create(self.tester.username, {
            "title": "报告A", "conclusion": "pass", "summary": "内容",
        })
        self._auth("tester1")
        for bad in ({"a": 1}, ["data"], 12345):
            resp = self.client.post(
                f"/api/reports/{report.id}/publish", {"screenshot": bad}, format="json"
            )
            self.assertEqual(resp.status_code, 422, msg=repr(bad))
            self.assertEqual(resp.json()["code"], 42201, msg=repr(bad))


# ---------- R3-B3 时间序列化统一 Asia/Shanghai 墙钟 ----------

class ShanghaiTimeSerializationTests(Round3Fixture):
    """B-P1-3：已知 UTC 时刻 → 各端点返回上海墙钟字符串（无 offset、不早 8 小时）。"""

    def test_fmt_dt_unit(self):
        self.assertEqual(fmt_dt(KNOWN_UTC), KNOWN_SHANGHAI)
        self.assertIsNone(fmt_dt(None))
        # naive 值防御性按墙钟直出（不抛 ValueError）
        self.assertEqual(fmt_dt(datetime(2026, 10, 13, 10, 0, 0)), "2026-10-13T10:00:00")

    def test_executions_returns_shanghai_wall_clock(self):
        s = self._make_strategy()
        r = ExecutionRound.objects.create(
            strategy=s, exec_date=date(2026, 10, 13), build_start_at=KNOWN_UTC,
        )
        self._auth("admin1")
        resp = self.client.get("/api/executions")
        row = next(item for item in resp.json()["data"] if item["id"] == r.id)
        self.assertEqual(row["build_start_at"], KNOWN_SHANGHAI)

    def test_borrow_flow_returns_shanghai_wall_clock(self):
        s = self._make_strategy()
        flow = BorrowFlow.objects.create(
            strategy=s, borrower=self.builder, target_branch=self.b27b,
            new_build_time="21:30",
        )
        BorrowFlow.objects.filter(id=flow.id).update(
            created_at=KNOWN_UTC, handled_at=KNOWN_UTC,
        )
        self._auth("admin1")
        resp = self.client.get("/api/borrow-flows")
        row = next(item for item in resp.json()["data"] if item["id"] == flow.id)
        self.assertEqual(row["created_at"], KNOWN_SHANGHAI)
        self.assertEqual(row["handled_at"], KNOWN_SHANGHAI)

    def test_slot_booking_rows_return_shanghai_wall_clock(self):
        tpl = SlotTemplate.objects.create(name="上午窗口", start_time=time(9, 0), end_time=time(12, 0))
        booking = SlotBooking.objects.create(
            date=timezone.localdate() + timedelta(days=1), template=tpl,
            start_snapshot=time(9, 0), end_snapshot=time(12, 0),
            status="released", user=self.builder, purpose="序列化口径测试",
            version=self.v27a, branch=self.b27a,
        )
        SlotBooking.objects.filter(id=booking.id).update(
            created_at=KNOWN_UTC, released_at=KNOWN_UTC,
        )
        self._auth("builder1")
        resp = self.client.get("/api/slot-bookings/mine")
        row = resp.json()["data"]["items"][0]
        self.assertEqual(row["created_at"], KNOWN_SHANGHAI)
        self.assertEqual(row["released_at"], KNOWN_SHANGHAI)

    def test_admin_logs_return_shanghai_wall_clock(self):
        log = SecurityLog.objects.create(username="u1", action="login_success", detail="d")
        SecurityLog.objects.filter(id=log.id).update(created_at=KNOWN_UTC)
        op = AdminOpLog.objects.create(operator=self.admin, action="update_config", detail="d")
        AdminOpLog.objects.filter(id=op.id).update(created_at=KNOWN_UTC)
        self._auth("admin1")
        resp = self.client.get("/api/admin/logs/security")
        row = next(item for item in resp.json()["data"] if item["id"] == log.id)
        self.assertEqual(row["created_at"], KNOWN_SHANGHAI)
        resp = self.client.get("/api/admin/logs/operations")
        row = next(item for item in resp.json()["data"] if item["id"] == op.id)
        self.assertEqual(row["created_at"], KNOWN_SHANGHAI)

    def test_branch_instance_returns_shanghai_wall_clock(self):
        project = Project.objects.create(name="工程X")
        bp = BranchProject.objects.create(branch=self.b27a, project=project)
        inst = svc_start(bp, "admin1")
        Instance.objects.filter(id=inst.id).update(
            started_at=KNOWN_UTC, last_heartbeat_at=KNOWN_UTC,
        )
        self._auth("admin1")
        resp = self.client.get(f"/api/branches/{self.b27a.id}/instances")
        row = resp.json()["data"][0]
        self.assertEqual(row["instance"]["started_at"], KNOWN_SHANGHAI)
        self.assertEqual(row["instance"]["last_heartbeat_at"], KNOWN_SHANGHAI)


# ---------- R3-B4 toggle 条件 UPDATE + 启用方向跑校验 ----------

class ToggleAtomicGuardTests(Round3Fixture):
    """B-P2-1：toggle 读改写竞态消除 + 重新启用不再绕过互斥/阶段校验。"""

    def test_stale_snapshot_second_toggle_40902(self):
        """并发双 toggle：两份旧快照先后翻转，第二次条件 UPDATE 命中 0 行 → 40902。"""
        s = self._make_strategy()
        snap1 = Strategy.objects.get(id=s.id)
        snap2 = Strategy.objects.get(id=s.id)
        svc_toggle(snap1)
        self.assertFalse(Strategy.objects.get(id=s.id).enabled)
        with self.assertRaises(StrategyValidationError) as ctx:
            svc_toggle(snap2)
        self.assertEqual(ctx.exception.code, 40902)
        # 仅第一次翻转生效，第二次未把状态翻回去
        self.assertFalse(Strategy.objects.get(id=s.id).enabled)

    def test_reenable_cross_branch_mutex_blocked(self):
        """停用 A(22:00) → 他分支建同刻 B → 重新启用 A → 互斥拦截 40902。

        注：跨分支同时刻由资源互斥拦截，错误码为既有口径 40902（40901 是
        同分支阶段冲突专用），与 spec 示例文案的 40901 相比以现码语义为准。
        """
        a = self._make_strategy(name="A", build="22:00")
        self._auth("pm27a")
        resp = self.client.patch(f"/api/strategies/{a.id}/toggle")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        # 他分支（同版本）建同刻启用策略：A 已停用，创建合法
        self._make_strategy(branch=Branch.objects.create(version=self.v27a, name="TR5"),
                            name="B", build="22:00")
        resp = self.client.patch(f"/api/strategies/{a.id}/toggle")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)
        a.refresh_from_db()
        self.assertFalse(a.enabled)

    def test_reenable_same_branch_stage_conflict_40901(self):
        """同分支阶段重叠：重新启用被既有启用策略的冒烟/分析窗口拦截 → 40901。"""
        a = self._make_strategy(name="A", build="20:00", enabled=False)
        # C 启用中：21:00 构建，冒烟 21:30 起 480 分钟，与 A 的冒烟窗口（20:30 起）重叠
        self._make_strategy(name="C", build="21:00", enabled=True)
        self._auth("pm27a")
        resp = self.client.patch(f"/api/strategies/{a.id}/toggle")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40901)
        a.refresh_from_db()
        self.assertFalse(a.enabled)

    def test_toggle_disable_direction_skips_validation(self):
        """停用方向不跑冲突校验（即使现状存在冲突也允许停用），且翻转成功。"""
        a = self._make_strategy(name="A", build="22:00", enabled=True)
        self._auth("pm27a")
        resp = self.client.patch(f"/api/strategies/{a.id}/toggle")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertFalse(resp.json()["data"]["enabled"])
        a.refresh_from_db()
        self.assertFalse(a.enabled)

    def test_admin_toggle_uses_same_guard(self):
        """admin 入口共用服务层：旧快照并发翻转同样 40902。"""
        s = self._make_strategy()
        snap = Strategy.objects.get(id=s.id)
        self._auth("pm27a")
        resp = self.client.patch(f"/api/strategies/{s.id}/toggle")  # 先经 PM 路由翻转
        self.assertEqual(resp.status_code, 200)
        self._auth("admin1")
        # admin 用服务层直调旧快照（等价并发窗口）
        with self.assertRaises(StrategyValidationError) as ctx:
            svc_toggle(snap)
        self.assertEqual(ctx.exception.code, 40902)


# ---------- R3-B5 PM toggle/delete 审计 + delete 拦截 pending 借用流 ----------

class PmStrategyAuditTests(Round3Fixture):
    """B-P2-2：PM 侧策略启停/删除补审计留痕；删除拦截待审批借用流。"""

    def test_toggle_writes_change_log(self):
        s = self._make_strategy()
        self._auth("pm27a")
        resp = self.client.patch(f"/api/strategies/{s.id}/toggle")
        self.assertEqual(resp.status_code, 200)
        log = StrategyChangeLog.objects.filter(strategy=s).first()
        self.assertIsNotNone(log)
        self.assertIn("启停策略", log.change_desc)
        self.assertEqual(log.operator_id, self.pm27a.id)

    def test_delete_blocked_by_pending_borrow_flow_40903(self):
        s = self._make_strategy()
        BorrowFlow.objects.create(
            strategy=s, borrower=self.builder, target_branch=self.b27b,
            new_build_time="21:30",
        )
        self._auth("pm27a")
        resp = self.client.delete(f"/api/strategies/{s.id}")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40903)
        self.assertTrue(Strategy.objects.filter(id=s.id).exists())
        self.assertTrue(BorrowFlow.objects.filter(strategy=s).exists())

    def test_delete_ok_after_flow_handled_and_audited(self):
        s = self._make_strategy()
        sid = s.id
        BorrowFlow.objects.create(
            strategy=s, borrower=self.builder, target_branch=self.b27b,
            new_build_time="21:30", status="rejected",
        )
        self._auth("pm27a")
        resp = self.client.delete(f"/api/strategies/{sid}")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertFalse(Strategy.objects.filter(id=sid).exists())
        # StrategyChangeLog 随策略级联删除，删除审计落 AdminOpLog（独立存续）
        self.assertTrue(AdminOpLog.objects.filter(
            action="delete_strategy", target_type="strategy",
            target_id=str(sid), operator=self.pm27a,
        ).exists())


# ---------- R3-B6 update_user 角色/停用守卫绑定版本 ----------

class UpdateUserVersionGuardTests(Round3Fixture):
    """B-P2-3：绑定版本的 PM 不可被降级/停用（防"无主版本"），移交后放行。"""

    def test_demote_bound_pm_40902(self):
        self._auth("admin1")
        resp = self.client.patch(
            f"/api/admin/users/{self.pm27a.id}", {"role": "builder"}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)
        self.pm27a.refresh_from_db()
        self.assertEqual(self.pm27a.role, "pm")

    def test_disable_bound_pm_40902(self):
        self._auth("admin1")
        resp = self.client.patch(
            f"/api/admin/users/{self.pm27a.id}", {"is_active": False}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)
        self.pm27a.refresh_from_db()
        self.assertTrue(self.pm27a.is_active)

    def test_demote_ok_after_version_transferred(self):
        pm3 = User.objects.create_user(username="pm3", password="123456", role="pm")
        self._auth("admin1")
        resp = self.client.put(
            f"/api/admin/versions/{self.v27a.id}", {"pm_user_id": pm3.id}, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        resp = self.client.patch(
            f"/api/admin/users/{self.pm27a.id}", {"role": "builder"}, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)

    def test_unbound_pm_demote_ok(self):
        pm4 = User.objects.create_user(username="pm4", password="123456", role="pm")
        self._auth("admin1")
        resp = self.client.patch(
            f"/api/admin/users/{pm4.id}", {"role": "tester"}, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)


# ---------- R3-B7 config PUT 值域校验 ----------

class ConfigValueDomainTests(Round3Fixture):
    """B-P2-4：build_minutes 等仅接受非负整数；true/45.7/-1/"abc" → 42201。"""

    def test_invalid_values_422(self):
        self._auth("admin1")
        # 先记录当前值（settings 默认或 .env 覆盖），非法 PUT 后必须保持不变
        before = self.client.get("/api/admin/config").json()["data"]["build_minutes"]
        for bad in (True, 45.7, "45.7", -1, "abc", ["1"]):
            resp = self.client.put("/api/admin/config", {"build_minutes": bad}, format="json")
            self.assertEqual(resp.status_code, 422, msg=repr(bad))
            self.assertEqual(resp.json()["code"], 42201, msg=repr(bad))
        # 非法值不得落库/入缓存
        resp = self.client.get("/api/admin/config")
        self.assertEqual(resp.json()["data"]["build_minutes"], before)

    def test_valid_values_ok(self):
        self._auth("admin1")
        resp = self.client.put("/api/admin/config", {"build_minutes": 0}, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertEqual(resp.json()["data"]["build_minutes"], 0)
        resp = self.client.put("/api/admin/config", {"push_minutes": "45"}, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertEqual(resp.json()["data"]["push_minutes"], 45)


# ---------- R3-B9 release_booking 条件 UPDATE ----------

class ReleaseBookingAtomicTests(Round3Fixture):
    """B-P2-8：并发/重复释放仅第一次生效，released_at/reason 不被覆盖。"""

    def _booking(self):
        tpl = SlotTemplate.objects.create(name="上午窗口", start_time=time(9, 0), end_time=time(12, 0))
        return SlotBooking.objects.create(
            date=timezone.localdate() + timedelta(days=1), template=tpl,
            start_snapshot=time(9, 0), end_snapshot=time(12, 0),
            status="reserved", user=self.builder, purpose="并发释放测试",
            version=self.v27a, branch=self.b27a,
        )

    def test_stale_snapshot_release_rejected_and_not_overwritten(self):
        booking = self._booking()
        stale = SlotBooking.objects.get(id=booking.id)  # 旧快照仍认为 reserved
        # 并发窗口：另一请求已抢先释放
        first_at = timezone.now() - timedelta(minutes=1)
        SlotBooking.objects.filter(id=booking.id).update(
            status="released", released_at=first_at, release_reason="第一次释放",
        )
        data, error = release_booking(stale, self.builder, "第二次释放")
        self.assertIsNone(data)
        self.assertEqual(error["code"], 42201)
        row = SlotBooking.objects.get(id=booking.id)
        self.assertEqual(row.release_reason, "第一次释放")
        self.assertEqual(row.released_at, first_at)

    def test_first_release_succeeds(self):
        booking = self._booking()
        data, error = release_booking(booking, self.builder, "正常释放")
        self.assertIsNone(error)
        self.assertEqual(data["status"], "released")
        row = SlotBooking.objects.get(id=booking.id)
        self.assertEqual(row.status, "released")
        self.assertEqual(row.release_reason, "正常释放")

    def test_repeat_release_via_service_rejected(self):
        booking = self._booking()
        release_booking(booking, self.builder, "第一次")
        booking.refresh_from_db()
        data, error = release_booking(booking, self.builder, "第二次")
        self.assertIsNone(data)
        self.assertEqual(error["code"], 42201)
        self.assertEqual(SlotBooking.objects.get(id=booking.id).release_reason, "第一次")


# ---------- R3-B10 list_strategies 可见性设计决策锁定 ----------

class StrategyVisibilityDecisionTests(Round3Fixture):
    """B-P2-6 定案：策略计划全员可见；PM 过滤是默认视图；无绑定 PM fail-closed。"""

    def setUp(self):
        super().setUp()
        self._make_strategy(branch=self.b27a, name="27A策略")
        self._make_strategy(branch=self.b27b, name="27B策略")

    def _visible_names(self, username):
        self._auth(username)
        resp = self.client.get("/api/strategies")
        self.assertEqual(resp.status_code, 200)
        return {item["name"] for item in resp.json()["data"]}

    def test_builder_tester_integrator_see_all(self):
        User.objects.create_user(username="intg1", password="123456", role="integrator")
        for username in ("builder1", "tester1", "intg1", "admin1"):
            self.assertEqual(self._visible_names(username), {"27A策略", "27B策略"}, msg=username)

    def test_bound_pm_sees_only_own_version(self):
        self.assertEqual(self._visible_names("pm27a"), {"27A策略"})
        self.assertEqual(self._visible_names("pm27b"), {"27B策略"})

    def test_unbound_pm_fail_closed_empty(self):
        User.objects.create_user(username="pm_none", password="123456", role="pm")
        self.assertEqual(self._visible_names("pm_none"), set())


# ---------- R3-B11 死代码清理 / logout 清理 / 分页收敛 ----------

class CleanupAndPaginationTests(Round3Fixture):
    """R3-B11：CODE_OK 引用、logout 黑名单清理、paginate_qs 共享助手。"""

    def test_ok_envelope_uses_code_ok_constant(self):
        self.assertEqual(CODE_OK, 0)
        self.assertEqual(api_ok()["code"], CODE_OK)

    def test_logout_cleans_expired_and_null_revoked_tokens(self):
        RevokedToken.objects.create(jti="null-exp", expires_at=None)
        RevokedToken.objects.create(
            jti="expired", expires_at=timezone.now() - timedelta(days=1))
        RevokedToken.objects.create(
            jti="future", expires_at=timezone.now() + timedelta(days=1))
        resp = self.client.post("/api/auth/logout")
        self.assertEqual(resp.status_code, 200)
        remaining = set(RevokedToken.objects.values_list("jti", flat=True))
        self.assertEqual(remaining, {"future"})

    def test_paginate_qs_invalid_params_fallback(self):
        for i in range(5):
            self._make_strategy(name=f"S{i}", build=f"{10 + i}:00")
        qs = Strategy.objects.order_by("id")
        req = SimpleNamespace(query_params={"page": "abc", "page_size": "xyz"})
        data = paginate_qs(qs, req, lambda r: {"id": r.id})
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 20)
        self.assertEqual(data["total"], 5)
        self.assertEqual(len(data["items"]), 5)

    def test_paginate_qs_bounds(self):
        qs = Strategy.objects.none()
        req = SimpleNamespace(query_params={"page": "0", "page_size": "0"})
        data = paginate_qs(qs, req, lambda r: r)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 20)  # 0 回退默认（reports 旧口径）
        req = SimpleNamespace(query_params={"page": "-3", "page_size": "1000"})
        data = paginate_qs(qs, req, lambda r: r)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 100)  # 上限 100

    def test_reports_pagination_full_params(self):
        for i in range(5):
            ReportService.create(self.tester.username, {
                "title": f"报告{i}", "conclusion": "pass", "summary": "内容",
            })
        self._auth("tester1")
        resp = self.client.get("/api/reports?page=2&page_size=2")
        data = resp.json()["data"]
        self.assertEqual(data["total"], 5)
        self.assertEqual(data["page"], 2)
        self.assertEqual(data["page_size"], 2)
        self.assertEqual(len(data["items"]), 2)
        # 非法 page 回退第 1 页
        resp = self.client.get("/api/reports?page=abc&page_size=2")
        data = resp.json()["data"]
        self.assertEqual(data["page"], 1)
        self.assertEqual(len(data["items"]), 2)
        # page_size 上限 100
        resp = self.client.get("/api/reports?page=1&page_size=1000")
        self.assertEqual(resp.json()["data"]["page_size"], 100)
        # 不带 page：全量数组（向后兼容）
        resp = self.client.get("/api/reports")
        data = resp.json()["data"]
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 5)


# ---------- R3-B12 security_log detail 截断 ----------

class SecurityLogTruncateTests(ConfigAwareTestCase):
    """B-P3-3：拼接后 detail 截断到 max_length=255，迁 Postgres 不再报错。"""

    def test_long_detail_truncated_to_255(self):
        req = RequestFactory().post("/", HTTP_USER_AGENT="u" * 500)
        security_log("test_action", username="someone", detail="详" * 300, request=req)
        log = SecurityLog.objects.latest("id")
        self.assertLessEqual(len(log.detail), 255)
        self.assertTrue(log.detail.startswith("详"))


# ---------- R3-B13/B18 密码策略与空串口径 ----------

class PasswordPolicyTests(Round3Fixture):
    """B-P2-7（最小长度）+ B-P3-6（空串不再静默忽略）。"""

    def test_create_user_short_password_422(self):
        self._auth("admin1")
        for bad in ("1", "12345"):
            resp = self.client.post("/api/admin/users", {
                "username": f"u_{len(bad)}", "role": "builder", "password": bad,
            }, format="json")
            self.assertEqual(resp.status_code, 422, msg=repr(bad))
            self.assertEqual(resp.json()["code"], 42201, msg=repr(bad))
        # 恰 6 位合规（seed 的 123456 同口径）
        resp = self.client.post("/api/admin/users", {
            "username": "u6", "role": "builder", "password": "123456",
        }, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)

    def test_update_user_short_password_422(self):
        self._auth("admin1")
        resp = self.client.patch(
            f"/api/admin/users/{self.builder.id}", {"password": "12345"}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        self.builder.refresh_from_db()
        self.assertTrue(self.builder.check_password("123456"))

    def test_update_user_empty_password_422(self):
        self._auth("admin1")
        resp = self.client.patch(
            f"/api/admin/users/{self.builder.id}", {"password": ""}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_update_user_missing_or_null_password_keeps_old(self):
        self._auth("admin1")
        resp = self.client.patch(
            f"/api/admin/users/{self.builder.id}", {"display_name": "新显示名"}, format="json")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.patch(
            f"/api/admin/users/{self.builder.id}", {"password": None}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.builder.refresh_from_db()
        self.assertTrue(self.builder.check_password("123456"))
        self.assertEqual(self.builder.display_name, "新显示名")

    def test_update_user_valid_password_ok(self):
        self._auth("admin1")
        resp = self.client.patch(
            f"/api/admin/users/{self.builder.id}", {"password": "newpass1"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.builder.refresh_from_db()
        self.assertTrue(self.builder.check_password("newpass1"))


# ---------- R3-B15 借用审批保留推送配置 ----------

class BorrowApprovePushConfigTests(Round3Fixture):
    """B-P3-4：审批通过创建的新策略复制源策略 push_mode/push_start_time。"""

    def _approve_flow(self, source):
        flow = BorrowFlow.objects.create(
            strategy=source, borrower=self.builder, target_branch=self.b27b,
            new_build_time="21:30",
        )
        self._auth("pm27a")
        resp = self.client.post(f"/api/borrow-flows/{flow.id}/approve", format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        return Strategy.objects.get(branch=self.b27b, build_start_time="21:30")

    def test_sync_strategy_push_config_preserved(self):
        source = self._make_strategy(
            name="同步推送源", build="06:30", push_mode="sync", push_start="08:00")
        created = self._approve_flow(source)
        self.assertEqual(created.push_mode, "sync")
        self.assertEqual(created.push_start_time, "08:00")

    def test_normal_fixed_push_preserved(self):
        source = self._make_strategy(
            name="固定推送源", build="22:00", push_mode="normal", push_start="20:00")
        created = self._approve_flow(source)
        self.assertEqual(created.push_mode, "normal")
        self.assertEqual(created.push_start_time, "20:00")

    def test_normal_without_push_time_stays_null(self):
        source = self._make_strategy(name="普通源", build="22:00")
        created = self._approve_flow(source)
        self.assertEqual(created.push_mode, "normal")
        self.assertIsNone(created.push_start_time)


# ---------- R3-B16 读端点方法守卫 ----------

class ReadEndpointMethodGuardTests(Round3Fixture):
    """B-P3-5：GET-only 端点非 GET → 42201；borrow_flow 列表仅放行 GET/POST。"""

    def _assert_guard(self, method, path):
        resp = self.client.generic(method, path)
        self.assertEqual(resp.status_code, 422, msg=f"{method} {path}")
        self.assertEqual(resp.json()["code"], 42201, msg=f"{method} {path}")

    def test_guard_matrix(self):
        self._auth("builder1")
        self._assert_guard("PUT", "/api/plan")
        self._assert_guard("POST", "/api/weekly")
        self._assert_guard("DELETE", "/api/executions")
        self._assert_guard("PUT", "/api/executions/rounds/1")
        self._assert_guard("PUT", "/api/logs/execution")
        self._assert_guard("POST", "/api/logs/changes")
        self._assert_guard("POST", "/api/auth/me")
        self._assert_guard("PUT", "/api/slot-calendar")
        self._assert_guard("DELETE", "/api/users/all")
        self._assert_guard("DELETE", "/api/borrow-flows")
        self._assert_guard("PUT", "/api/borrow-flows")

    def test_approve_reject_get_rejected_no_side_effect(self):
        s = self._make_strategy()
        flow = BorrowFlow.objects.create(
            strategy=s, borrower=self.builder, target_branch=self.b27b,
            new_build_time="21:30",
        )
        self._auth("pm27a")
        self._assert_guard("GET", f"/api/borrow-flows/{flow.id}/approve")
        self._assert_guard("GET", f"/api/borrow-flows/{flow.id}/reject")
        flow.refresh_from_db()
        self.assertEqual(flow.status, "pending")
        self.assertFalse(Strategy.objects.filter(branch=self.b27b).exists())

    def test_get_still_works(self):
        self._auth("builder1")
        for path in ("/api/plan", "/api/weekly", "/api/executions",
                     "/api/logs/execution", "/api/logs/changes", "/api/auth/me",
                     "/api/slot-calendar", "/api/users/all", "/api/borrow-flows"):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 200, msg=path)


# ---------- R3-B14 测试缺口补全 ----------

class ExceptionHandlerMappingTests(ConfigAwareTestCase):
    """exception_handlers 三映射：MethodNotAllowed→42201、Throttled→42901、APIException→50000。"""

    def test_method_not_allowed_maps_42201(self):
        resp = contract_exception_handler(MethodNotAllowed("DELETE"), {})
        self.assertEqual(resp.status_code, 422)
        payload = json.loads(resp.content)
        self.assertEqual(payload["code"], 42201)
        self.assertEqual(payload["message"], "不支持的请求方法")

    def test_throttled_maps_42901(self):
        resp = contract_exception_handler(Throttled(), {})
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(json.loads(resp.content)["code"], 42901)

    def test_generic_api_exception_maps_50000(self):
        resp = contract_exception_handler(APIException("boom"), {})
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(json.loads(resp.content)["code"], 50000)

    def test_viewset_delete_end_to_end_42201(self):
        """端到端：DELETE /api/reports/<pk>（ViewSet 未开放 delete）→ 42201 信封。"""
        client = APIClient()
        User.objects.create_user(username="tester1", password="123456", role="tester")
        resp = client.post(
            "/api/auth/login", {"username": "tester1", "password": "123456"}, format="json")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}")
        resp = client.delete("/api/reports/1")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)


class ExecutionsListPmIsolationTests(Round3Fixture):
    """executions 列表 PM 隔离：他版轮次不可见（round2 只锁了详情隔离）。"""

    def setUp(self):
        super().setUp()
        s_a = self._make_strategy(branch=self.b27a, name="A策略", build="22:00")
        s_b = self._make_strategy(branch=self.b27b, name="B策略", build="22:00")
        self.round_a = ExecutionRound.objects.create(
            strategy=s_a, exec_date=date(2026, 10, 12))
        self.round_b = ExecutionRound.objects.create(
            strategy=s_b, exec_date=date(2026, 10, 12))

    def _ids(self, username):
        self._auth(username)
        resp = self.client.get("/api/executions")
        self.assertEqual(resp.status_code, 200)
        return {item["id"] for item in resp.json()["data"]}

    def test_pm_sees_only_own_version_rounds(self):
        self.assertEqual(self._ids("pm27a"), {self.round_a.id})
        self.assertEqual(self._ids("pm27b"), {self.round_b.id})

    def test_admin_and_builder_see_all(self):
        expected = {self.round_a.id, self.round_b.id}
        self.assertEqual(self._ids("admin1"), expected)
        self.assertEqual(self._ids("builder1"), expected)


class SlotCalendarDecemberTests(Round3Fixture):
    """build_slot_calendar 12 月边界：跨年月份矩阵完整到 12-31。"""

    def test_december_has_31_days(self):
        SlotTemplate.objects.create(
            name="全天窗口", start_time=time(0, 0), end_time=time(23, 59), weekdays="")
        data, error = build_slot_calendar("2026-12", self.builder)
        self.assertIsNone(error)
        self.assertEqual(data["month"], "2026-12")
        self.assertEqual(len(data["days"]), 31)
        self.assertIn("2026-12-01", data["days"])
        self.assertIn("2026-12-31", data["days"])
        entry = data["days"]["2026-12-31"][0]
        self.assertEqual(entry["status"], "available")

    def test_february_leap_year_boundary(self):
        SlotTemplate.objects.create(
            name="全天窗口", start_time=time(0, 0), end_time=time(23, 59), weekdays="")
        data, error = build_slot_calendar("2028-02", self.builder)
        self.assertIsNone(error)
        self.assertEqual(len(data["days"]), 29)  # 2028 闰年
        self.assertIn("2028-02-29", data["days"])


class TimelineSyncPushWindowTests(ConfigAwareTestCase):
    """timeline sync 模式推送窗口：build_start − push − buffer ~ build_start − buffer。"""

    def test_sync_push_window(self):
        tl = build_timeline("2026-10-13", "22:00", 60, 30, 30, 20, 20, "sync",
                            push_start_time=None)
        self.assertEqual(tl["push"]["start"], "2026-10-13T21:20:00")
        self.assertEqual(tl["push"]["end"], "2026-10-13T21:40:00")

    def test_sync_push_window_crosses_midnight(self):
        tl = build_timeline("2026-10-13", "00:10", 60, 30, 30, 20, 20, "sync",
                            push_start_time=None)
        self.assertEqual(tl["push"]["start"], "2026-10-12T23:30:00")
        self.assertEqual(tl["push"]["end"], "2026-10-12T23:50:00")

    def test_fixed_push_time_overrides_sync_window(self):
        tl = build_timeline("2026-10-13", "22:00", 60, 30, 30, 20, 20, "sync",
                            push_start_time="20:00")
        self.assertEqual(tl["push"]["start"], "2026-10-13T20:00:00")
        self.assertEqual(tl["push"]["end"], "2026-10-13T20:20:00")


class ConclusionElseBranchTests(Round3Fixture):
    """conclusion fail/sync → push_status="" else 分支；operator=None → ""。"""

    def _round(self, push_mode="normal", build="22:00"):
        s = self._make_strategy(name=f"S-{push_mode}", build=build, push_mode=push_mode)
        return ExecutionRound.objects.create(
            strategy=s, exec_date=date(2026, 10, 12), conclusion=None)

    def test_fail_conclusion_clears_push(self):
        r = self._round("normal")
        self._auth("tester1")
        resp = self.client.post(
            f"/api/executions/rounds/{r.id}/conclusion",
            {"conclusion": "fail", "note": "冒烟不过"}, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertEqual(resp.json()["data"]["push_status"], "")
        r.refresh_from_db()
        self.assertIsNone(r.push_start_at)
        self.assertIsNone(r.push_end_at)

    def test_pass_on_sync_strategy_clears_push(self):
        r = self._round("sync", build="21:00")
        self._auth("tester1")
        resp = self.client.post(
            f"/api/executions/rounds/{r.id}/conclusion",
            {"conclusion": "pass"}, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        # sync 模式的推送窗口在构建前，结论阶段不再补推送 → else 分支
        self.assertEqual(resp.json()["data"]["push_status"], "")

    def test_change_log_operator_none_serialized_empty(self):
        s = self._make_strategy()
        StrategyChangeLog.objects.create(
            strategy=s, operator=None, change_desc="系统自动记录")
        self._auth("builder1")
        resp = self.client.get("/api/logs/changes")
        row = next(item for item in resp.json()["data"] if item["change_desc"] == "系统自动记录")
        self.assertEqual(row["operator"], "")


class BorrowFlowEdgeTests(Round3Fixture):
    """borrow_flow 边界：create 404 / 审批时模板已删 404+回滚 / approve 后再 reject。"""

    def test_create_strategy_not_found_40401(self):
        self._auth("builder1")
        resp = self.client.post("/api/borrow-flows", {
            "strategy_id": 999999, "target_branch_id": self.b27b.id,
            "new_build_time": "21:30",
        }, format="json")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["code"], 40401)

    def test_approve_after_template_deleted_40401_and_rollback(self):
        s = self._make_strategy()
        flow = BorrowFlow.objects.create(
            strategy=s, borrower=self.builder, target_branch=self.b27b,
            new_build_time="21:30",
        )
        self._auth("pm27a")
        # 模拟"审批时模板已不存在"的终态：Strategy.template 为 PROTECT，正常 ORM
        # 删不掉被引用模板（原生 SQL 又会留悬空外键触发测试 teardown 约束检查），
        # 故 mock 模板查询返回 None——与库中行被删对视图代码路径完全等价。
        with mock.patch(
            "build_protection_service.views.borrow_flow.StrategyTemplate"
        ) as mocked:
            mocked.objects.filter.return_value.first.return_value = None
            resp = self.client.post(f"/api/borrow-flows/{flow.id}/approve", format="json")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["code"], 40401)
        # set_rollback：抢占回滚，电子流保持待审批，未创建借用策略
        flow.refresh_from_db()
        self.assertEqual(flow.status, "pending")
        self.assertIsNone(flow.approver_id)
        self.assertFalse(Strategy.objects.filter(branch=self.b27b).exists())

    def test_reject_after_approve_40903(self):
        s = self._make_strategy()
        flow = BorrowFlow.objects.create(
            strategy=s, borrower=self.builder, target_branch=self.b27b,
            new_build_time="21:30", status="approved",
        )
        self._auth("pm27a")
        resp = self.client.post(
            f"/api/borrow-flows/{flow.id}/reject", {"comment": "反悔了"}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40903)
        flow.refresh_from_db()
        self.assertEqual(flow.status, "approved")


class TemplateAppliesBoundaryTests(ConfigAwareTestCase):
    """template_applies_on：effective_from/to 等于当天为闭区间边界。"""

    def setUp(self):
        super().setUp()
        self.tpl = SlotTemplate.objects.create(
            name="边界窗口", start_time=time(9, 0), end_time=time(12, 0),
            weekdays="", effective_from=date(2026, 10, 13), effective_to=date(2026, 10, 20),
        )

    def test_boundaries_inclusive(self):
        self.assertTrue(template_applies_on(self.tpl, date(2026, 10, 13)))
        self.assertTrue(template_applies_on(self.tpl, date(2026, 10, 20)))
        self.assertFalse(template_applies_on(self.tpl, date(2026, 10, 12)))
        self.assertFalse(template_applies_on(self.tpl, date(2026, 10, 21)))


class AdminSlotListDateGuardTests(Round3Fixture):
    """admin slot 记录列表 date_from/date_to 非法 → 42201。"""

    def test_invalid_dates_422(self):
        self._auth("admin1")
        resp = self.client.get("/api/slot-bookings?date_from=abc")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        resp = self.client.get("/api/slot-bookings?date_to=xyz")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_valid_dates_ok(self):
        self._auth("admin1")
        resp = self.client.get("/api/slot-bookings?date_from=2026-10-01&date_to=2026-10-31")
        self.assertEqual(resp.status_code, 200)


class AdminBranchAndVersionRaceTests(Round3Fixture):
    """add_branch 重名 40902；update_version 并发重命名 IntegrityError 兜底。"""

    def test_add_branch_duplicate_name_40902(self):
        self._auth("admin1")
        resp = self.client.post(
            f"/api/admin/versions/{self.v27a.id}/branches", {"name": "master"}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)

    def test_update_version_concurrent_rename_integrity_fallback(self):
        """模拟并发窗口：重名预检通过后、save 前另一事务抢先占用名字。"""
        self._auth("admin1")
        with mock.patch.object(
            Version, "save",
            side_effect=IntegrityError(
                "UNIQUE constraint failed: build_protection_service_version.name"),
        ):
            resp = self.client.put(
                f"/api/admin/versions/{self.v27a.id}", {"name": "27C"}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)


class ReportFilterNumericKeywordTests(Round3Fixture):
    """ReportFilter 纯数字 keyword → 同时按 pk 精确匹配。"""

    def test_numeric_keyword_matches_pk(self):
        r1 = ReportService.create(self.tester.username, {
            "title": "Alpha报告", "conclusion": "pass", "summary": "s"})
        r2 = ReportService.create(self.tester.username, {
            "title": "Beta报告", "conclusion": "pass", "summary": "s"})
        self._auth("tester1")
        resp = self.client.get(f"/api/reports?keyword={r2.id}")
        ids = [item["id"] for item in resp.json()["data"]]
        self.assertEqual(ids, [r2.id])
        self.assertNotIn(r1.id, ids)


class StrategyServiceIntegrityTests(Round3Fixture):
    """update_strategy save 撞唯一约束 → 40902；非目标约束 IntegrityError 原样抛。"""

    def test_save_hits_unique_constraint_40902(self):
        s = self._make_strategy()
        with mock.patch.object(
            Strategy, "save",
            side_effect=IntegrityError(
                "UNIQUE constraint failed: strategy.branch_id, strategy.build_start_time"),
        ):
            with self.assertRaises(StrategyValidationError) as ctx:
                svc_update(s, {"name": "改名撞约束"}, self.pm27a)
        self.assertEqual(ctx.exception.code, 40902)

    def test_non_target_integrity_error_reraised(self):
        s = self._make_strategy()
        with mock.patch.object(
            Strategy, "save", side_effect=IntegrityError("FOREIGN KEY constraint failed"),
        ):
            with self.assertRaises(IntegrityError):
                svc_update(s, {"name": "外键异常"}, self.pm27a)


class MutexInvalidTimeTests(Round3Fixture):
    """check_build_mutex：既有策略构建时间非法 → warning 跳过，不中断校验。"""

    def test_invalid_time_skipped_with_warning(self):
        # 直接 ORM 落库非法时间（CharField 无校验，模拟历史脏数据）
        Strategy.objects.create(
            branch=self.b27a, template=self.tmpl, name="脏数据策略",
            build_start_time="99:99", push_mode="normal", enabled=True,
            created_by=self.pm27a,
        )
        with self.assertLogs("build_protection_service.services.mutex", level="WARNING") as cm:
            hits = check_build_mutex(self.v27a.id, "22:00", 30)
        self.assertEqual(hits, [])
        self.assertTrue(any("构建时间非法" in line for line in cm.output))


class ReportServiceNoChangeTests(Round3Fixture):
    """report_service.update：字段无变化时不落库、不留痕。"""

    _DATA = {
        "title": "标题A", "version_name": "27A", "strategy_name": "",
        "conclusion": "pass", "environment": "", "summary": "内容",
        "risks": "", "remark": "",
    }

    def test_update_without_changes_leaves_no_log(self):
        report = ReportService.create(self.tester.username, dict(self._DATA))
        self.assertEqual(
            ReportRevisionLog.objects.filter(report_id=report.id).count(), 1)  # create 留痕
        updated_at_before = report.updated_at
        ReportService.update(self.tester.username, report, dict(self._DATA))
        # 无变化：不新增留痕、不 save（updated_at 不变）
        self.assertEqual(
            ReportRevisionLog.objects.filter(report_id=report.id).count(), 1)
        report.refresh_from_db()
        self.assertEqual(report.updated_at, updated_at_before)


class StrategiesUnsupportedMethodTests(Round3Fixture):
    """strategies 集合/详情/toggle 不支持的方法 → 42201。"""

    def test_unsupported_methods_422(self):
        s = self._make_strategy()
        self._auth("pm27a")
        resp = self.client.put("/api/strategies", {}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        resp = self.client.post(f"/api/strategies/{s.id}", {}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        resp = self.client.put(f"/api/strategies/{s.id}/toggle")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        resp = self.client.get(f"/api/strategies/{s.id}/toggle")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        # 无副作用
        s.refresh_from_db()
        self.assertTrue(s.enabled)
