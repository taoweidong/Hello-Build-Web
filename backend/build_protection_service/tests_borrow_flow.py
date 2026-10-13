"""借用电子流测试：发起校验 / 审批权限 / 通过即建策略 / 冲突保持待审批 / 驳回。"""
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    BorrowFlow,
    Branch,
    Strategy,
    StrategyTemplate,
    User,
    Version,
)
from .tests import ConfigAwareTestCase


class BorrowFlowFixture(ConfigAwareTestCase):
    """共享夹具：两版本两分支 + 被借用策略 + 各角色 token（发起/审批/撤销用例同源复用）。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.pm27a = User.objects.create_user(username="pm27a", password="123456", role="pm")
        self.pm26b = User.objects.create_user(username="pm26b", password="123456", role="pm")
        self.builder = User.objects.create_user(username="builder", password="123456", role="builder")
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        v27a = Version.objects.create(name="27A", pm_user=self.pm27a, status="active")
        v26b = Version.objects.create(name="26B", pm_user=self.pm26b, status="active")
        self.b27a = Branch.objects.create(version=v27a, name="master")
        self.b26b = Branch.objects.create(version=v26b, name="master")
        self.tmpl = StrategyTemplate.objects.create(name="晚间全量冒烟", smoke_minutes=480, analysis_minutes=120)
        self.strategy = Strategy.objects.create(
            branch=self.b27a, template=self.tmpl, name="27A-master-晚间全量",
            build_start_time="22:00", push_mode="normal", created_by=self.pm27a,
        )
        self._login = {
            "pm27a": self._token("pm27a"),
            "pm26b": self._token("pm26b"),
            "builder": self._token("builder"),
            "admin": self._token("admin"),
        }

    def _token(self, username):
        resp = self.client.post(
            "/api/auth/login", {"username": username, "password": "123456"}, format="json"
        )
        return resp.json()["data"]["token"]

    def _auth(self, username):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._login[username]}")

    def _create_flow(self, token_user="builder", **overrides):
        self._auth(token_user)
        payload = {
            "strategy_id": self.strategy.id,
            "target_branch_id": self.b26b.id,
            "new_build_time": "21:30",
            "reason": "26B 晚间需要复用该时段",
        }
        payload.update(overrides)
        return self.client.post("/api/borrow-flows", payload, format="json")


class BorrowFlowTests(BorrowFlowFixture):
    """借用电子流 API：发起校验 / 审批权限 / 通过即建策略 / 冲突保持待审批 / 驳回。"""

    # ---- 发起 ----

    def test_create_flow_ok(self):
        resp = self._create_flow()
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["strategy_name"], "27A-master-晚间全量")
        self.assertEqual(data["target_version_name"], "26B")
        self.assertEqual(data["borrower_name"], "builder")

    def test_create_rejects_same_version_target(self):
        resp = self._create_flow(target_branch_id=self.b27a.id)
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_create_rejects_duplicate_pending(self):
        self._create_flow()
        resp = self._create_flow()
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40903)

    def test_create_rejects_bad_time_format(self):
        resp = self._create_flow(new_build_time="25:00")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_create_requires_auth(self):
        resp = self.client.post(
            "/api/borrow-flows",
            {"strategy_id": self.strategy.id, "target_branch_id": self.b26b.id,
             "new_build_time": "21:30"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    # ---- 审批权限 ----

    def test_approve_forbidden_for_non_source_pm(self):
        flow = BorrowFlow.objects.create(
            strategy=self.strategy, borrower=self.builder,
            target_branch=self.b26b, new_build_time="21:30",
        )
        self._auth("pm26b")
        resp = self.client.post(f"/api/borrow-flows/{flow.id}/approve", format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], 40301)

    def test_approve_by_source_pm_creates_strategy(self):
        flow = BorrowFlow.objects.create(
            strategy=self.strategy, borrower=self.builder,
            target_branch=self.b26b, new_build_time="21:30",
        )
        self._auth("pm27a")
        resp = self.client.post(f"/api/borrow-flows/{flow.id}/approve", format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["status"], "approved")
        created = Strategy.objects.filter(branch=self.b26b, build_start_time="21:30").first()
        self.assertIsNotNone(created)
        self.assertEqual(created.template_id, self.tmpl.id)
        self.assertTrue(created.name.endswith("(26B借用)"))
        flow.refresh_from_db()
        self.assertEqual(flow.approver_id, self.pm27a.id)
        self.assertIsNotNone(flow.handled_at)

    def test_approve_by_admin_ok(self):
        flow = BorrowFlow.objects.create(
            strategy=self.strategy, borrower=self.pm26b,
            target_branch=self.b26b, new_build_time="21:30",
        )
        self._auth("admin")
        resp = self.client.post(f"/api/borrow-flows/{flow.id}/approve", format="json")
        self.assertEqual(resp.status_code, 200)

    def test_approve_conflict_keeps_pending(self):
        # 目标版本 21:30 已有启用策略 → 阶段冲突，审批失败且电子流保持待审批
        Strategy.objects.create(
            branch=self.b26b, template=self.tmpl, name="26B-master-晚间全量",
            build_start_time="21:30", push_mode="normal", created_by=self.pm26b,
        )
        flow = BorrowFlow.objects.create(
            strategy=self.strategy, borrower=self.builder,
            target_branch=self.b26b, new_build_time="21:30",
        )
        self._auth("pm27a")
        resp = self.client.post(f"/api/borrow-flows/{flow.id}/approve", format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertIn(resp.json()["code"], (40901, 40902))
        flow.refresh_from_db()
        self.assertEqual(flow.status, "pending")
        self.assertFalse(Strategy.objects.filter(name__endswith="(26B借用)").exists())

    def test_double_approve_rejected(self):
        flow = BorrowFlow.objects.create(
            strategy=self.strategy, borrower=self.builder,
            target_branch=self.b26b, new_build_time="21:30", status="approved",
        )
        self._auth("pm27a")
        resp = self.client.post(f"/api/borrow-flows/{flow.id}/approve", format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40903)

    # ---- 驳回 ----

    def test_reject_requires_comment(self):
        flow = BorrowFlow.objects.create(
            strategy=self.strategy, borrower=self.builder,
            target_branch=self.b26b, new_build_time="21:30",
        )
        self._auth("pm27a")
        resp = self.client.post(f"/api/borrow-flows/{flow.id}/reject", {"comment": ""}, format="json")
        self.assertEqual(resp.status_code, 422)
        resp = self.client.post(
            f"/api/borrow-flows/{flow.id}/reject",
            {"comment": "时段已被占用"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        flow.refresh_from_db()
        self.assertEqual(flow.status, "rejected")
        self.assertEqual(flow.handle_comment, "时段已被占用")
        self.assertFalse(Strategy.objects.filter(branch=self.b26b).exists())

    # ---- 列表 ----

    def test_list_with_status_filter(self):
        BorrowFlow.objects.create(
            strategy=self.strategy, borrower=self.builder,
            target_branch=self.b26b, new_build_time="21:30",
        )
        BorrowFlow.objects.create(
            strategy=self.strategy, borrower=self.pm26b,
            target_branch=self.b26b, new_build_time="20:30", status="rejected",
            approver=self.pm27a, handle_comment="冲突", handled_at=timezone.now(),
        )
        # 2026-10-12 起列表按"与我相关"过滤：全量列表仅 admin 可见，
        # 发起人只看到自己发起的电子流（避免他人申请理由/审批意见全量暴露）。
        self._auth("admin")
        resp = self.client.get("/api/borrow-flows")
        self.assertEqual(len(resp.json()["data"]), 2)
        resp = self.client.get("/api/borrow-flows?status=pending")
        self.assertEqual(len(resp.json()["data"]), 1)
        self.assertEqual(resp.json()["data"][0]["status"], "pending")
        self._auth("builder")
        resp = self.client.get("/api/borrow-flows")
        self.assertEqual(len(resp.json()["data"]), 1)
        self.assertEqual(resp.json()["data"][0]["borrower_name"], "builder")


class BorrowFlowCancelTests(BorrowFlowFixture):
    """借用撤销（P2-R1）：仅借用人本人 + 仅待审批可撤。"""

    def test_cancel_ok_releases_pending_constraint(self):
        flow_id = self._create_flow().json()["data"]["id"]
        resp = self.client.post(f"/api/borrow-flows/{flow_id}/cancel")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()["data"]
        self.assertEqual(body["status"], "cancelled")
        self.assertIsNotNone(body["cancelled_at"])
        # 撤销不删记录（审计留痕）
        self.assertTrue(
            BorrowFlow.objects.filter(id=flow_id, status="cancelled").exists()
        )
        # 部分唯一约束只覆盖 pending → 撤销后同策略可立即重新发起
        again = self._create_flow()
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["data"]["status"], "pending")

    def test_cancel_forbidden_for_others(self):
        """来源版本 PM 也不能替借用人撤销（撤销是「撤回自己的申请」）。"""
        flow_id = self._create_flow().json()["data"]["id"]
        self._auth("pm27a")
        resp = self.client.post(f"/api/borrow-flows/{flow_id}/cancel")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], 40301)
        self.assertEqual(BorrowFlow.objects.get(id=flow_id).status, "pending")

    def test_cancel_after_approved_conflicts(self):
        flow_id = self._create_flow().json()["data"]["id"]
        self._auth("pm27a")
        self.client.post(f"/api/borrow-flows/{flow_id}/approve")
        self._auth("builder")
        resp = self.client.post(f"/api/borrow-flows/{flow_id}/cancel")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40903)
        self.assertEqual(BorrowFlow.objects.get(id=flow_id).status, "approved")

    def test_cancel_not_found(self):
        self._auth("builder")
        resp = self.client.post("/api/borrow-flows/9999/cancel")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["code"], 40401)

    def test_cancel_method_guard(self):
        """写端点仅 POST：GET 不产生副作用。"""
        flow_id = self._create_flow().json()["data"]["id"]
        self._auth("builder")
        resp = self.client.get(f"/api/borrow-flows/{flow_id}/cancel")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        self.assertEqual(BorrowFlow.objects.get(id=flow_id).status, "pending")

    def test_list_status_filter_accepts_cancelled(self):
        flow_id = self._create_flow().json()["data"]["id"]
        self.client.post(f"/api/borrow-flows/{flow_id}/cancel")
        resp = self.client.get("/api/borrow-flows?status=cancelled")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["data"]), 1)
        self.assertEqual(resp.json()["data"][0]["status"], "cancelled")
