"""第四轮全库质量优化（2026-10-15）回归测试。

对应 docs/code-quality-assessment-2026-10-15.md 与
docs/superpowers/specs/2026-10-15-code-quality-optimization-round4-design.md：
每个修复项（R4-B1 ~ R4-B19）一组锁定测试，防止同类问题复发。

口径提示：
- 并发用例沿用 tests_strategy_concurrency / round3 的技巧：用 ORM 直改终态 /
  mock 绕过前置检查模拟「并发窗口内另一事务抢先提交」，不做线程级并发断言；
- R4-B3 说明：改期端点空载荷是合法 no-op（缺省字段沿用原值），非 dict 载荷
  归一为 {} 后与空载荷同语义（200），锁定核心是「绝无 500 破坏契约」；
  permissions 端点归一后走既有「授权用户不存在」42201 分支。
"""
import json
from datetime import time, timedelta
from unittest import mock

from django.conf import settings
from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from .admin import StrategyAdmin
from .errors import CODE_ASSOCIATION, CODE_SLOT_CONFLICT
from .models import (
    AdminOpLog,
    BorrowFlow,
    Branch,
    BranchProject,
    ExecutionRound,
    Instance,
    Project,
    RevokedToken,
    RuntimeConfig,
    SecurityLog,
    SlotBooking,
    SlotTemplate,
    Strategy,
    StrategyTemplate,
    Version,
)
from .serializers.slot_booking import SlotTemplateSerializer
from .services.branch_config import start_instance as svc_start
from .services.branch_config import stop_instance as svc_stop
from .services.config import get_config, set_config
from .services.slot_booking import (
    _raise_slot_conflict_or_reraise,
    create_booking,
    reschedule_booking,
)
from .services.strategies import (
    StrategyValidationError,
    delete_strategy as svc_delete_strategy,
)
from .services.timeline import valid_hhmm
from .tests import ConfigAwareTestCase
from .views import check_str_len, security_log
from .views.borrow_flow import _flow_qs, _payload

User = get_user_model()


class Round4Fixture(ConfigAwareTestCase):
    """共享夹具：双版本双分支 + 策略/时段模板 + 各角色用户 + 登录助手。"""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin1", password="123456", role="admin")
        self.pm27a = User.objects.create_user(username="pm27a", password="123456", role="pm")
        self.pm26b = User.objects.create_user(username="pm26b", password="123456", role="pm")
        self.builder = User.objects.create_user(username="builder1", password="123456", role="builder")
        self.tester = User.objects.create_user(username="tester1", password="123456", role="tester")
        self.v27a = Version.objects.create(name="27A", pm_user=self.pm27a, status="active")
        self.v26b = Version.objects.create(name="26B", pm_user=self.pm26b, status="active")
        self.b27a = Branch.objects.create(version=self.v27a, name="master")
        self.b26b = Branch.objects.create(version=self.v26b, name="master")
        self.tmpl = StrategyTemplate.objects.create(
            name="晚间全量冒烟", smoke_minutes=480, analysis_minutes=120
        )
        self.slot_tmpl = SlotTemplate.objects.create(
            name="上午窗口", start_time="08:00", end_time="12:00",
            weekdays="", color="#67c23a", sort_order=1,
        )

    def tearDown(self):
        # 登录失败计数存进程级 cache，用后清理避免污染其他用例
        cache.clear()
        super().tearDown()

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

    def _make_booking(self, when=None, template=None, user=None, version=None,
                      branch=None, purpose="日常构建窗口占用"):
        tpl = template or self.slot_tmpl
        return SlotBooking.objects.create(
            date=when or (timezone.localdate() + timedelta(days=1)),
            template=tpl,
            start_snapshot=time(8, 0),
            end_snapshot=time(12, 0),
            status="reserved",
            user=user or self.builder,
            purpose=purpose,
            version=version or self.v27a,
            branch=branch or self.b27a,
        )

    def _make_flow(self, strategy=None, borrower=None, target_branch=None,
                   new_build_time="21:30", status="pending"):
        return BorrowFlow.objects.create(
            strategy=strategy or self._make_strategy(),
            borrower=borrower or self.builder,
            target_branch=target_branch or self.b26b,
            new_build_time=new_build_time,
            reason="26B 需要复用该时段",
            status=status,
        )


# ---------- R4-B1 admin 删除策略补 pending 借用流拦截 ----------

class AdminStrategyDeleteGuardTests(Round4Fixture):
    """B4-01：admin 删除策略与 PM 入口共用服务层 pending 借用流拦截（40903）。"""

    def test_admin_delete_blocked_by_pending_flow(self):
        s = self._make_strategy()
        flow = self._make_flow(strategy=s)
        self._auth("admin1")
        resp = self.client.delete(f"/api/admin/strategies/{s.id}")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], CODE_ASSOCIATION)
        self.assertTrue(Strategy.objects.filter(id=s.id).exists())
        self.assertTrue(BorrowFlow.objects.filter(id=flow.id).exists())

    def test_admin_delete_ok_after_flow_handled_and_audited(self):
        s = self._make_strategy()
        flow = self._make_flow(strategy=s)
        BorrowFlow.objects.filter(id=flow.id).update(status="rejected")
        self._auth("admin1")
        resp = self.client.delete(f"/api/admin/strategies/{s.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Strategy.objects.filter(id=s.id).exists())
        self.assertTrue(
            AdminOpLog.objects.filter(action="delete_strategy", target_id=str(s.id)).exists()
        )

    def test_pm_delete_blocked_by_pending_flow_regression(self):
        """PM 路径回归：收敛到共享服务函数后行为不变（R3-B5 语义保留）。"""
        s = self._make_strategy()
        self._make_flow(strategy=s)
        self._auth("pm27a")
        resp = self.client.delete(f"/api/strategies/{s.id}")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], CODE_ASSOCIATION)
        self.assertTrue(Strategy.objects.filter(id=s.id).exists())

    def test_service_delete_raises_40903(self):
        s = self._make_strategy()
        self._make_flow(strategy=s)
        with self.assertRaises(StrategyValidationError) as ctx:
            svc_delete_strategy(s)
        self.assertEqual(ctx.exception.code, CODE_ASSOCIATION)


# ---------- R4-B2 分支删除 ProtectedError 兜底 ----------

class BranchDeleteProtectTests(Round4Fixture):
    """B4-02：SlotBooking.branch / BorrowFlow.target_branch 均 PROTECT，
    删除被引用分支须转契约 40903，不得裸 500。"""

    def test_delete_branch_with_slot_booking_40903(self):
        self._make_booking(branch=self.b27a, version=self.v27a)
        self._auth("admin1")
        resp = self.client.delete(f"/api/branches/{self.b27a.id}")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], CODE_ASSOCIATION)
        self.assertTrue(Branch.objects.filter(id=self.b27a.id).exists())

    def test_delete_branch_referenced_by_borrow_flow_40903(self):
        s = self._make_strategy()
        self._make_flow(strategy=s, target_branch=self.b26b)
        self._auth("admin1")
        resp = self.client.delete(f"/api/branches/{self.b26b.id}")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], CODE_ASSOCIATION)
        self.assertTrue(Branch.objects.filter(id=self.b26b.id).exists())

    def test_delete_unreferenced_branch_ok(self):
        b = Branch.objects.create(version=self.v27a, name="TR5")
        self._auth("admin1")
        resp = self.client.delete(f"/api/branches/{b.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Branch.objects.filter(id=b.id).exists())


# ---------- R4-B3 非 dict body 归一补齐两处漏网 ----------

class NonDictBodyGuardRound4Tests(Round4Fixture):
    """B4-03：改期端点与 permissions 端点的非 dict JSON 载荷不得 500。"""

    def test_reschedule_non_dict_body_never_500(self):
        booking = self._make_booking(user=self.builder)
        self._auth("builder1")
        for body in ("[1]", '"str"', "null"):
            resp = self.client.patch(
                f"/api/slot-bookings/{booking.id}", data=body, content_type="application/json"
            )
            self.assertNotEqual(resp.status_code, 500, msg=body)
            # 归一为 {} = 空载荷 no-op 改期（缺省字段沿用原值，与既有空 body 语义一致）
            self.assertEqual(resp.status_code, 200, msg=body)
            self.assertEqual(resp.json()["code"], 0, msg=body)
        booking.refresh_from_db()
        self.assertEqual(booking.status, "reserved")

    def test_permissions_non_dict_body_42201(self):
        self._auth("admin1")
        for body in ("[1]", '"str"', "null"):
            resp = self.client.post(
                f"/api/branches/{self.b27a.id}/permissions",
                data=body, content_type="application/json",
            )
            self.assertEqual(resp.status_code, 422, msg=body)
            self.assertEqual(resp.json()["code"], 42201, msg=body)


# ---------- R4-B4 conclusion note 走 body_str ----------

class ConclusionNoteGuardTests(Round4Fixture):
    """B4-04：note 非 str 回退原值、超长截断 255（审计备注类字段口径）。"""

    def setUp(self):
        super().setUp()
        self.strategy = self._make_strategy()
        self.round = ExecutionRound.objects.create(
            strategy=self.strategy, exec_date=timezone.localdate(), note="初始备注"
        )

    def _submit(self, payload):
        self._auth("tester1")
        return self.client.post(
            f"/api/executions/rounds/{self.round.id}/conclusion", payload, format="json"
        )

    def _note_after(self, payload):
        resp = self._submit(payload)
        self.assertEqual(resp.status_code, 200)
        self.round.refresh_from_db()
        return self.round.note

    def test_note_object_keeps_original(self):
        self.assertEqual(self._note_after({"conclusion": "pass", "note": {"a": 1}}), "初始备注")

    def test_note_number_keeps_original(self):
        self.assertEqual(self._note_after({"conclusion": "pass", "note": 123}), "初始备注")

    def test_note_null_keeps_original(self):
        self.assertEqual(self._note_after({"conclusion": "pass", "note": None}), "初始备注")

    def test_note_missing_keeps_original(self):
        self.assertEqual(self._note_after({"conclusion": "pass"}), "初始备注")

    def test_note_over_255_truncated(self):
        note = self._note_after({"conclusion": "fail", "note": "x" * 300})
        self.assertEqual(len(note), 255)

    def test_note_normal_str_saved(self):
        self.assertEqual(self._note_after({"conclusion": "pass", "note": "冒烟全部通过"}), "冒烟全部通过")


# ---------- R4-B5 版本 PM 必须为启用用户 ----------

class VersionPmActiveGuardTests(Round4Fixture):
    """B4-05：停用用户不可被设为版本 PM（与 R3-B6「无主版本」不变量对齐）。"""

    def setUp(self):
        super().setUp()
        self.dead_pm = User.objects.create_user(
            username="dead_pm", password="123456", role="pm", is_active=False
        )

    def test_create_version_inactive_pm_42201(self):
        self._auth("admin1")
        resp = self.client.post(
            "/api/admin/versions",
            {"name": "99A", "pm_user_id": self.dead_pm.id, "status": "active"},
            format="json",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        self.assertFalse(Version.objects.filter(name="99A").exists())

    def test_update_version_inactive_pm_42201(self):
        self._auth("admin1")
        resp = self.client.put(
            f"/api/admin/versions/{self.v27a.id}",
            {"pm_user_id": self.dead_pm.id}, format="json",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        self.v27a.refresh_from_db()
        self.assertEqual(self.v27a.pm_user_id, self.pm27a.id)

    def test_create_version_active_pm_ok(self):
        live_pm = User.objects.create_user(username="pm99", password="123456", role="pm")
        self._auth("admin1")
        resp = self.client.post(
            "/api/admin/versions",
            {"name": "99A", "pm_user_id": live_pm.id, "status": "active"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Version.objects.filter(name="99A").exists())


# ---------- R4-B6 login/logout 方法守卫 ----------

class AuthMethodGuardTests(Round4Fixture):
    """B4-06：GET /auth/logout 不得吊销 token；GET /auth/login 不得语义错位。"""

    def test_get_logout_rejected_no_side_effect(self):
        token = self._token("builder1")
        for method in ("get", "put", "delete", "patch"):
            resp = getattr(self.client, method)(
                "/api/auth/logout", HTTP_AUTHORIZATION=f"Bearer {token}"
            )
            self.assertEqual(resp.status_code, 422, msg=method)
            self.assertEqual(resp.json()["code"], 42201, msg=method)
        self.assertEqual(RevokedToken.objects.count(), 0)
        self.assertFalse(SecurityLog.objects.filter(action="logout").exists())

    def test_post_logout_still_revokes_regression(self):
        token = self._token("builder1")
        resp = self.client.post("/api/auth/logout", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(RevokedToken.objects.count(), 1)
        self.assertTrue(SecurityLog.objects.filter(action="logout").exists())

    def test_login_non_post_rejected_no_side_effect(self):
        for method in ("get", "put", "delete", "patch"):
            resp = getattr(self.client, method)("/api/auth/login")
            self.assertEqual(resp.status_code, 422, msg=method)
            self.assertEqual(resp.json()["code"], 42201, msg=method)
        self.assertEqual(SecurityLog.objects.count(), 0)


# ---------- R4-B7 security_log username 截断 ----------

class SecurityLogUsernameTruncateTests(Round4Fixture):
    """B4-07：SecurityLog.username max_length=100，超长截断防迁 Postgres 审计致盲。"""

    def test_security_log_username_truncated_unit(self):
        security_log("test_action", username="u" * 200)
        log = SecurityLog.objects.latest("id")
        self.assertEqual(len(log.username), 100)

    def test_login_failed_long_username_truncated(self):
        resp = self.client.post(
            "/api/auth/login", {"username": "u" * 200, "password": "bad"}, format="json"
        )
        self.assertEqual(resp.status_code, 401)
        log = SecurityLog.objects.filter(action="login_failed").latest("id")
        self.assertEqual(len(log.username), 100)


# ---------- R4-B8 抢占/改期 IntegrityError 精确匹配 ----------

class SlotConflictPrecisionTests(Round4Fixture):
    """B4-08：仅目标唯一约束转 40904，其余 IntegrityError 原样上抛不吞。"""

    def test_helper_matches_target_constraint_sqlite_style(self):
        exc = IntegrityError(
            "UNIQUE constraint failed: build_protection_service_slotbooking.date, "
            "build_protection_service_slotbooking.template_id"
        )
        err, holder = _raise_slot_conflict_or_reraise(
            exc, timezone.localdate(), self.slot_tmpl, "已"
        )
        self.assertEqual(err["code"], CODE_SLOT_CONFLICT)
        self.assertEqual(holder, "他人")  # 无占位记录时兜底文案

    def test_helper_matches_constraint_name(self):
        # Postgres 等后端消息携带约束名
        exc = IntegrityError(
            'duplicate key value violates unique constraint "uniq_slot_booking_active"'
        )
        err, _ = _raise_slot_conflict_or_reraise(
            exc, timezone.localdate(), self.slot_tmpl, "已"
        )
        self.assertEqual(err["code"], CODE_SLOT_CONFLICT)

    def test_helper_reraises_other_constraints(self):
        for msg in (
            "NOT NULL constraint failed: build_protection_service_slotbooking.purpose",
            "NOT NULL constraint failed: build_protection_service_slotbooking.date",
            "FOREIGN KEY constraint failed",
        ):
            with self.assertRaises(IntegrityError, msg=msg):
                _raise_slot_conflict_or_reraise(
                    IntegrityError(msg), timezone.localdate(), self.slot_tmpl, "已"
                )

    def test_second_create_returns_40904_regression(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        self._make_booking(when=tomorrow)
        data, error = create_booking(self.builder, {
            "date": tomorrow.isoformat(), "template_id": self.slot_tmpl.id,
            "purpose": "第二次抢占测试", "version_id": self.v27a.id, "branch_id": self.b27a.id,
        })
        self.assertIsNone(data)
        self.assertEqual(error["code"], CODE_SLOT_CONFLICT)
        self.assertIn("刚被", error["message"])

    def test_reschedule_into_occupied_returns_40904_regression(self):
        d1 = timezone.localdate() + timedelta(days=1)
        d2 = timezone.localdate() + timedelta(days=2)
        self._make_booking(when=d1)
        b2 = self._make_booking(when=d2)
        data, error = reschedule_booking(b2, self.builder, {"date": d1.isoformat()})
        self.assertIsNone(data)
        self.assertEqual(error["code"], CODE_SLOT_CONFLICT)
        self.assertIn("已被", error["message"])


# ---------- R4-B9 config PUT 先全量校验后原子写入 ----------

class ConfigAtomicPutTests(Round4Fixture):
    """B4-09：多键部分非法时不得留下半套中间态；set_config 并发竞态兜底。"""

    def test_partial_invalid_leaves_config_untouched(self):
        self._auth("admin1")
        resp = self.client.put(
            "/api/admin/config", {"build_minutes": 40, "push_minutes": "abc"}, format="json"
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        # 原子性断言：第一键不得已生效
        self.assertFalse(RuntimeConfig.objects.filter(key="build_minutes").exists())
        get_resp = self.client.get("/api/admin/config")
        self.assertEqual(get_resp.json()["data"]["build_minutes"], settings.BUILD_MINUTES)

    def test_all_valid_persisted(self):
        self._auth("admin1")
        resp = self.client.put(
            "/api/admin/config",
            {"build_minutes": 40, "push_minutes": 25, "sync_buffer_minutes": 15},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual((data["build_minutes"], data["push_minutes"], data["sync_buffer_minutes"]),
                         (40, 25, 15))
        self.assertEqual(RuntimeConfig.objects.get(key="build_minutes").value, 40)

    def test_set_config_integrity_retry(self):
        """并发 get_or_create 竞态撞 key unique → 兜底按 UPDATE 重试一次。"""
        RuntimeConfig.objects.create(key="build_minutes", value=1)
        with mock.patch.object(
            RuntimeConfig.objects, "update_or_create",
            side_effect=IntegrityError("UNIQUE constraint failed: key"),
        ):
            set_config("build_minutes", 77)
        self.assertEqual(RuntimeConfig.objects.get(key="build_minutes").value, 77)
        self.assertEqual(get_config("build_minutes"), 77)


# ---------- R4-B10 字符串字段 max_length 校验补全 ----------

class CheckStrLenHelperTests(ConfigAwareTestCase):
    """check_str_len 纯函数：超长 → 42201 响应；合规/非 str → None。"""

    def test_within_limit_returns_none(self):
        self.assertIsNone(check_str_len("abc", "字段", 3))

    def test_non_str_returns_none(self):
        # 非字符串由各调用点既有 isinstance/必填分支处理，不在此拦截
        self.assertIsNone(check_str_len(123, "字段", 3))
        self.assertIsNone(check_str_len(None, "字段", 3))

    def test_over_limit_returns_42201_resp(self):
        resp = check_str_len("abcd", "字段", 3)
        self.assertIsNotNone(resp)
        payload = json.loads(resp.content)
        self.assertEqual(payload["code"], 42201)
        self.assertIn("3", payload["message"])


class MaxLengthGuardTests(Round4Fixture):
    """B4-10：写端点字符串字段超模型 max_length → 42201 拒绝（优于静默截断）。"""

    def test_create_version_name_over_100(self):
        self._auth("admin1")
        resp = self.client.post(
            "/api/admin/versions", {"name": "V" * 101, "pm_user_id": self.pm26b.id}, format="json"
        )
        self.assertEqual(resp.json()["code"], 42201)

    def test_create_version_name_boundary_100_ok(self):
        live_pm = User.objects.create_user(username="pm98", password="123456", role="pm")
        self._auth("admin1")
        resp = self.client.post(
            "/api/admin/versions", {"name": "V" * 100, "pm_user_id": live_pm.id}, format="json"
        )
        self.assertEqual(resp.status_code, 200)

    def test_update_version_name_over_100(self):
        self._auth("admin1")
        resp = self.client.put(
            f"/api/admin/versions/{self.v27a.id}", {"name": "V" * 101}, format="json"
        )
        self.assertEqual(resp.json()["code"], 42201)

    def test_add_branch_name_over_100(self):
        self._auth("admin1")
        resp = self.client.post(
            f"/api/admin/versions/{self.v27a.id}/branches", {"name": "B" * 101}, format="json"
        )
        self.assertEqual(resp.json()["code"], 42201)

    def test_create_user_username_over_150(self):
        self._auth("admin1")
        resp = self.client.post(
            "/api/admin/users",
            {"username": "u" * 151, "password": "123456", "role": "builder"},
            format="json",
        )
        self.assertEqual(resp.json()["code"], 42201)

    def test_create_user_display_name_over_100(self):
        self._auth("admin1")
        resp = self.client.post(
            "/api/admin/users",
            {"username": "ok_user", "password": "123456", "role": "builder",
             "display_name": "d" * 101},
            format="json",
        )
        self.assertEqual(resp.json()["code"], 42201)

    def test_update_user_display_name_over_100(self):
        self._auth("admin1")
        resp = self.client.patch(
            f"/api/admin/users/{self.builder.id}", {"display_name": "d" * 101}, format="json"
        )
        self.assertEqual(resp.json()["code"], 42201)

    def test_create_template_name_over_100_and_description_over_255(self):
        self._auth("admin1")
        resp = self.client.post("/api/admin/templates", {"name": "T" * 101}, format="json")
        self.assertEqual(resp.json()["code"], 42201)
        resp = self.client.post(
            "/api/admin/templates", {"name": "新模板", "description": "D" * 256}, format="json"
        )
        self.assertEqual(resp.json()["code"], 42201)

    def test_update_template_name_over_100(self):
        self._auth("admin1")
        resp = self.client.patch(
            f"/api/admin/templates/{self.tmpl.id}", {"name": "T" * 101}, format="json"
        )
        self.assertEqual(resp.json()["code"], 42201)
        resp = self.client.patch(
            f"/api/admin/templates/{self.tmpl.id}", {"description": "D" * 256}, format="json"
        )
        self.assertEqual(resp.json()["code"], 42201)

    def test_branch_create_name_over_100_and_url_over_255(self):
        self._auth("admin1")
        resp = self.client.post(
            "/api/branches", {"version_id": self.v27a.id, "name": "N" * 101}, format="json"
        )
        self.assertEqual(resp.json()["code"], 42201)
        resp = self.client.post(
            "/api/branches",
            {"version_id": self.v27a.id, "name": "合规名", "repository_url": "r" * 256},
            format="json",
        )
        self.assertEqual(resp.json()["code"], 42201)

    def test_project_create_name_over_100_and_url_over_255(self):
        self._auth("admin1")
        resp = self.client.post("/api/projects", {"name": "P" * 101}, format="json")
        self.assertEqual(resp.json()["code"], 42201)
        resp = self.client.post(
            "/api/projects", {"name": "合规工程", "repository_url": "r" * 256}, format="json"
        )
        self.assertEqual(resp.json()["code"], 42201)

    def test_strategy_name_over_200_rejected_by_service(self):
        self._auth("pm27a")
        resp = self.client.post(
            "/api/strategies",
            {"branch_id": self.b27a.id, "template_id": self.tmpl.id,
             "name": "策" * 201, "build_start_time": "22:00"},
            format="json",
        )
        self.assertEqual(resp.json()["code"], 42201)
        self.assertFalse(Strategy.objects.filter(name="策" * 201).exists())

    def test_borrow_approve_concat_name_capped_200(self):
        """审批建策略拼接名 f"...(...借用)" 防御截断到 Strategy.name 上限 200。"""
        s = self._make_strategy(name="策" * 198)
        flow = self._make_flow(strategy=s)
        self._auth("pm27a")
        resp = self.client.post(
            f"/api/borrow-flows/{flow.id}/approve", {"comment": "同意"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        created = Strategy.objects.filter(branch=self.b26b, build_start_time="21:30").first()
        self.assertIsNotNone(created)
        self.assertEqual(len(created.name), 200)
        self.assertTrue(created.name.startswith("策"))


# ---------- R4-B11 django-admin StrategyAdmin.save_model 服务层校验 ----------

class StrategyAdminSaveModelTests(Round4Fixture):
    """B4-11：后台直改策略须过 validate_strategy，冲突/非法数据被拒。"""

    def _model_admin(self):
        return StrategyAdmin(Strategy, django_admin.site)

    def test_conflicting_save_rejected(self):
        self._make_strategy(build="22:00")
        obj = Strategy(
            branch=self.b27a, template=self.tmpl, name="冲突策略",
            build_start_time="22:00", push_mode="normal", enabled=True,
        )
        with self.assertRaises(ValidationError):
            self._model_admin().save_model(None, obj, None, change=False)
        self.assertFalse(Strategy.objects.filter(name="冲突策略").exists())

    def test_invalid_time_format_rejected(self):
        obj = Strategy(
            branch=self.b27a, template=self.tmpl, name="非法时间",
            build_start_time="25:00", push_mode="normal", enabled=True,
        )
        with self.assertRaises(ValidationError):
            self._model_admin().save_model(None, obj, None, change=False)
        self.assertFalse(Strategy.objects.filter(name="非法时间").exists())

    def test_valid_save_persists(self):
        b = Branch.objects.create(version=self.v27a, name="TR9")
        obj = Strategy(
            branch=b, template=self.tmpl, name="新策略",
            build_start_time="22:00", push_mode="normal", enabled=True,
        )
        self._model_admin().save_model(None, obj, None, change=False)
        self.assertTrue(Strategy.objects.filter(name="新策略").exists())

    def test_disabled_save_skips_validation(self):
        """停用策略不占时段（约束/冲突检测仅覆盖 enabled=True），跳过校验。"""
        self._make_strategy(build="22:00")
        obj = Strategy(
            branch=self.b27a, template=self.tmpl, name="停用冲突策略",
            build_start_time="22:00", push_mode="normal", enabled=False,
        )
        self._model_admin().save_model(None, obj, None, change=False)
        self.assertTrue(Strategy.objects.filter(name="停用冲突策略").exists())


# ---------- R4-B12 全角数字拒绝 ----------

class FullWidthDigitGuardTests(Round4Fixture):
    """B4-12：valid_hhmm / validate_weekdays 拒绝 Unicode 全角数字。"""

    def test_valid_hhmm_rejects_fullwidth(self):
        self.assertFalse(valid_hhmm("２２:００"))
        self.assertFalse(valid_hhmm("22:００"))
        self.assertTrue(valid_hhmm("22:00"))

    def test_strategy_create_fullwidth_time_42201(self):
        self._auth("pm27a")
        resp = self.client.post(
            "/api/strategies",
            {"branch_id": self.b27a.id, "template_id": self.tmpl.id,
             "name": "全角时间策略", "build_start_time": "２２:００"},
            format="json",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_borrow_flow_fullwidth_time_42201(self):
        s = self._make_strategy()
        self._auth("builder1")
        resp = self.client.post(
            "/api/borrow-flows",
            {"strategy_id": s.id, "target_branch_id": self.b26b.id,
             "new_build_time": "２１:３０"},
            format="json",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_template_weekdays_fullwidth_rejected(self):
        serializer = SlotTemplateSerializer(data={
            "name": "全角星期", "start_time": "08:00", "end_time": "09:00", "weekdays": "１,２",
        })
        self.assertFalse(serializer.is_valid())
        self._auth("admin1")
        resp = self.client.post(
            "/api/slot-templates",
            {"name": "全角星期", "start_time": "08:00", "end_time": "09:00", "weekdays": "１"},
            format="json",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)


# ---------- R4-B13 借用流列表可选分页 ----------

class BorrowFlowPaginationTests(Round4Fixture):
    """B4-13：带 page 参数返回分页结构，不带保持全量数组（向后兼容）。"""

    def setUp(self):
        super().setUp()
        for i in range(5):
            s = self._make_strategy(name=f"策略{i}", build=f"{10 + i * 2}:00")
            self._make_flow(strategy=s)

    def test_no_page_returns_full_array_regression(self):
        self._auth("admin1")
        resp = self.client.get("/api/borrow-flows")
        data = resp.json()["data"]
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 5)

    def test_page_params(self):
        self._auth("admin1")
        resp = self.client.get("/api/borrow-flows?page=1&page_size=2")
        data = resp.json()["data"]
        self.assertEqual(data["total"], 5)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 2)
        self.assertEqual(len(data["items"]), 2)

    def test_last_page_partial(self):
        self._auth("admin1")
        resp = self.client.get("/api/borrow-flows?page=3&page_size=2")
        data = resp.json()["data"]
        self.assertEqual(data["total"], 5)
        self.assertEqual(len(data["items"]), 1)

    def test_out_of_range_page_empty_items(self):
        self._auth("admin1")
        resp = self.client.get("/api/borrow-flows?page=9&page_size=2")
        data = resp.json()["data"]
        self.assertEqual(data["total"], 5)
        self.assertEqual(len(data["items"]), 0)

    def test_invalid_params_fallback(self):
        self._auth("admin1")
        resp = self.client.get("/api/borrow-flows?page=abc&page_size=xyz")
        data = resp.json()["data"]
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 20)
        self.assertEqual(len(data["items"]), 5)

    def test_page_size_cap_100(self):
        self._auth("admin1")
        resp = self.client.get("/api/borrow-flows?page=1&page_size=1000")
        self.assertEqual(resp.json()["data"]["page_size"], 100)

    def test_borrower_visibility_with_pagination(self):
        self._auth("builder1")
        resp = self.client.get("/api/borrow-flows?page=1&page_size=2")
        data = resp.json()["data"]
        self.assertEqual(data["total"], 5)  # 全部为本人发起
        self.assertEqual(len(data["items"]), 2)


# ---------- R4-B14 借用流单条响应路径 select_related ----------

class BorrowFlowSelectRelatedTests(Round4Fixture):
    """B4-14：单条响应路径（create/approve/cancel）消除固定 N+1。"""

    def setUp(self):
        super().setUp()
        self.strategy = self._make_strategy()

    def test_payload_zero_queries_on_flow_qs(self):
        flow = self._make_flow(strategy=self.strategy)
        flow = _flow_qs().get(pk=flow.pk)
        with self.assertNumQueries(0):
            payload = _payload(flow)
        self.assertEqual(payload["strategy_name"], "策略A")
        self.assertEqual(payload["target_version_name"], "26B")
        self.assertEqual(payload["borrower_name"], "builder1")

    def test_create_response_query_budget(self):
        self._auth("builder1")
        payload = {
            "strategy_id": self.strategy.id, "target_branch_id": self.b26b.id,
            "new_build_time": "21:30", "reason": "复用时段",
        }
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.post("/api/borrow-flows", payload, format="json")
        self.assertEqual(resp.status_code, 200)
        # 修复后：认证 1 + 策略/分支/重复检查 3 + INSERT 1 + select_related 重取 1；
        # 修复前 _payload 逐关联点查另加 6+ 条。上界 10 锁定不回潮。
        self.assertLessEqual(len(ctx.captured_queries), 10)

    def test_approve_response_has_fresh_approver(self):
        """重取替代 refresh_from_db：条件 UPDATE 改写 approver_id 后缓存同步刷新。"""
        flow = self._make_flow(strategy=self.strategy)
        self._auth("pm27a")
        resp = self.client.post(
            f"/api/borrow-flows/{flow.id}/approve", {"comment": "同意"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["status"], "approved")
        self.assertEqual(data["approver_name"], "pm27a")
        self.assertIsNotNone(data["handled_at"])

    def test_reject_response_ok(self):
        flow = self._make_flow(strategy=self.strategy)
        self._auth("pm27a")
        resp = self.client.post(
            f"/api/borrow-flows/{flow.id}/reject", {"comment": "时段冲突"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["status"], "rejected")
        self.assertEqual(data["approver_name"], "pm27a")

    def test_cancel_response_ok(self):
        flow = self._make_flow(strategy=self.strategy)
        self._auth("builder1")
        resp = self.client.post(f"/api/borrow-flows/{flow.id}/cancel")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["status"], "cancelled")
        self.assertIsNotNone(data["cancelled_at"])


# ---------- R4-B15 seed master 分支缺失守卫 ----------

class SeedMasterBranchGuardTests(TestCase):
    """B4-15：27A master 分支被删后重跑 seed 不崩且补建（对齐 tr5/tr6 守卫）。"""

    def test_seed_recreates_missing_master_branch(self):
        User.objects.all().delete()
        call_command("seed")
        v27a = Version.objects.get(name="27A")
        master = Branch.objects.get(version=v27a, name="master")
        # SlotBooking.branch 为 PROTECT，删除前先清理引用
        SlotBooking.objects.filter(branch=master).delete()
        master.delete()  # 级联删除其上策略（含幂等锚点"27A-master-早间回归"）
        # 修复前：_seed_extra_strategies 以 None 分支 get_or_create → IntegrityError 整个 seed 中断
        call_command("seed")
        self.assertTrue(Branch.objects.filter(version=v27a, name="master").exists())
        self.assertTrue(Strategy.objects.filter(name="27A-master-早间回归").exists())


# ---------- R4-B16 stop_instance 条件 UPDATE ----------

class StopInstanceAtomicTests(Round4Fixture):
    """B4-16：停止实例走「条件 UPDATE + rowcount」范式，不覆盖首次停止留痕。"""

    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(name="工程A")
        self.bp = BranchProject.objects.create(branch=self.b27a, project=self.project)

    def test_stop_running_sets_stopped(self):
        inst = svc_start(self.bp, "actor1")
        result = svc_stop(self.bp, "actor1")
        self.assertEqual(result.id, inst.id)
        self.assertEqual(result.status, "STOPPED")
        self.assertIsNotNone(result.stopped_at)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("actor1] 发起停止", result.log_tail)

    def test_double_stop_idempotent_no_overwrite(self):
        svc_start(self.bp, "actor1")
        first = svc_stop(self.bp, "actor1")
        second = svc_stop(self.bp, "actor2")
        self.assertEqual(second.id, first.id)
        self.assertEqual(second.status, "STOPPED")
        db = Instance.objects.get(pk=first.pk)
        self.assertEqual(db.stopped_at, first.stopped_at)
        self.assertNotIn("actor2", db.log_tail)

    def test_stale_window_stop_does_not_overwrite(self):
        """模拟并发窗口：本方持有旧快照期间他人已停止 → 不覆盖 stopped_at。"""
        inst = svc_start(self.bp, "actor1")
        first_stop = timezone.now()
        # 他人抢先停止（ORM 直改终态模拟窗口内提交）
        Instance.objects.filter(id=inst.id).update(
            status="STOPPED", stopped_at=first_stop, exit_code=0
        )
        result = svc_stop(self.bp, "actor2")
        self.assertEqual(result.status, "STOPPED")
        db = Instance.objects.get(pk=inst.pk)
        self.assertEqual(db.stopped_at, first_stop)
        self.assertNotIn("actor2", db.log_tail)

    def test_conditional_update_matches_only_active(self):
        """rowcount=0 语义锁定：条件 UPDATE 仅命中 STARTING/RUNNING。"""
        inst = svc_start(self.bp, "actor1")
        Instance.objects.filter(id=inst.id).update(status="STOPPED")
        updated = Instance.objects.filter(
            id=inst.id, status__in=("STARTING", "RUNNING")
        ).update(status="STOPPED")
        self.assertEqual(updated, 0)

    def test_stop_without_instance_returns_none(self):
        self.assertIsNone(svc_stop(self.bp, "actor1"))


# ---------- R4-B17 模板创建并发重名兜底 ----------

class TemplateCreateIntegrityTests(Round4Fixture):
    """B4-17：并发重名撞 unique 约束 → 契约 40902 而非 500/50000。"""

    def test_slot_template_concurrent_duplicate_40902(self):
        self._auth("admin1")
        resp = self.client.post(
            "/api/slot-templates",
            {"name": "窗口A", "start_time": "13:00", "end_time": "14:00"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        # mock 前置 exists 检查为 False，模拟 check-then-create 窗口内他人已插入同名
        with mock.patch("django.db.models.query.QuerySet.exists", return_value=False):
            resp = self.client.post(
                "/api/slot-templates",
                {"name": "窗口A", "start_time": "13:00", "end_time": "14:00"},
                format="json",
            )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)
        self.assertEqual(SlotTemplate.objects.filter(name="窗口A").count(), 1)

    def test_admin_template_concurrent_duplicate_40902(self):
        self._auth("admin1")
        resp = self.client.post("/api/admin/templates", {"name": "模板X"}, format="json")
        self.assertEqual(resp.status_code, 200)
        with mock.patch("django.db.models.query.QuerySet.exists", return_value=False):
            resp = self.client.post("/api/admin/templates", {"name": "模板X"}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)
        self.assertEqual(StrategyTemplate.objects.filter(name="模板X").count(), 1)


# ---------- R4-B18 登录失败计数原子化 ----------

class LoginCounterAtomicTests(Round4Fixture):
    """B4-18：add+incr 原子计数，锁定阈值不被并发稀释、无 read-modify-write。"""

    def test_counter_exact_after_failures(self):
        for _ in range(3):
            resp = self.client.post(
                "/api/auth/login", {"username": "pm27a", "password": "bad"}, format="json"
            )
            self.assertEqual(resp.status_code, 401)
        self.assertEqual(cache.get("login:fail:pm27a:127.0.0.1"), 3)

    def test_lockout_at_five_regression(self):
        for _ in range(5):
            self.client.post(
                "/api/auth/login", {"username": "pm27a", "password": "bad"}, format="json"
            )
        resp = self.client.post(
            "/api/auth/login", {"username": "pm27a", "password": "123456"}, format="json"
        )
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.json()["code"], 42901)

    def test_success_clears_counter(self):
        for _ in range(2):
            self.client.post(
                "/api/auth/login", {"username": "pm27a", "password": "bad"}, format="json"
            )
        resp = self.client.post(
            "/api/auth/login", {"username": "pm27a", "password": "123456"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(cache.get("login:fail:pm27a:127.0.0.1"))

    def test_failure_uses_atomic_add_not_set(self):
        """锁定实现路径：add(key, 1, ttl) 初始化计数，不再 cache.set 读改写。"""
        with mock.patch("build_protection_service.views.login.cache") as m_cache:
            m_cache.get.return_value = 0
            m_cache.add.return_value = True
            resp = self.client.post(
                "/api/auth/login", {"username": "atomic_u", "password": "bad"}, format="json"
            )
        self.assertEqual(resp.status_code, 401)
        m_cache.add.assert_called_once()
        args = m_cache.add.call_args[0]
        self.assertEqual(args[1], 1)
        self.assertEqual(args[2], 15 * 60)
        m_cache.set.assert_not_called()

    def test_incr_race_fallback_reopens_window(self):
        """键恰在 add 与 incr 之间过期（incr 抛 ValueError）→ 兜底重开计数窗口。"""
        with mock.patch("build_protection_service.views.login.cache") as m_cache:
            m_cache.get.return_value = 0
            m_cache.add.side_effect = [False, True]
            m_cache.incr.side_effect = ValueError("Key not found")
            resp = self.client.post(
                "/api/auth/login", {"username": "race_u", "password": "bad"}, format="json"
            )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(m_cache.add.call_count, 2)
        m_cache.incr.assert_called_once()


# ---------- R4-B19 双写校验口径漂移锁定 ----------

class SlotDualValidationDriftTests(Round4Fixture):
    """B-P2-21 记录在案项（R4-B19 补测）：SlotBookingCreateSerializer 与
    services.slot_booking.create_booking 双写校验，同一非法载荷走 API（序列化器
    先拦）与直调服务（唯一裁决点）两条路径必须产生同一错误码。"""

    def _base_payload(self):
        return {
            "date": (timezone.localdate() + timedelta(days=1)).isoformat(),
            "template_id": self.slot_tmpl.id,
            "purpose": "合法的用途说明",
            "version_id": self.v27a.id,
            "branch_id": self.b27a.id,
        }

    def _invalid_payloads(self):
        base = self._base_payload()
        return [
            ("日期非法", {**base, "date": "not-a-date"}),
            ("用途过短", {**base, "purpose": "短"}),
            ("用途超长", {**base, "purpose": "x" * 201}),
            ("分支不属版本", {**base, "branch_id": self.b26b.id}),
            ("版本不存在", {**base, "version_id": 999999}),
            ("过去日期", {**base, "date": (timezone.localdate() - timedelta(days=1)).isoformat()}),
        ]

    def test_same_error_code_via_both_paths(self):
        self._auth("builder1")
        for label, payload in self._invalid_payloads():
            resp = self.client.post("/api/slot-bookings", payload, format="json")
            data, error = create_booking(self.builder, dict(payload))
            self.assertIsNone(data, msg=label)
            self.assertIsNotNone(error, msg=label)
            self.assertEqual(resp.json()["code"], error["code"], msg=label)
            self.assertEqual(resp.json()["code"], 42201, msg=label)

    def test_disabled_template_same_code_via_both_paths(self):
        self.slot_tmpl.enabled = False
        self.slot_tmpl.save(update_fields=["enabled"])
        self._auth("builder1")
        payload = self._base_payload()
        resp = self.client.post("/api/slot-bookings", payload, format="json")
        data, error = create_booking(self.builder, dict(payload))
        self.assertIsNone(data)
        self.assertEqual(resp.json()["code"], error["code"])
        self.assertEqual(resp.json()["code"], 42201)

    def test_valid_payload_succeeds_via_both_paths(self):
        self._auth("builder1")
        d1 = timezone.localdate() + timedelta(days=1)
        d2 = timezone.localdate() + timedelta(days=2)
        resp = self.client.post("/api/slot-bookings", {**self._base_payload(), "date": d1.isoformat()}, format="json")
        self.assertEqual(resp.status_code, 200)
        data, error = create_booking(self.builder, {**self._base_payload(), "date": d2.isoformat()})
        self.assertIsNone(error)
        self.assertIsNotNone(data)
        self.assertEqual(SlotBooking.objects.filter(status="reserved").count(), 2)
