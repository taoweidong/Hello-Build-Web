"""调度全景聚合接口测试（P2-R3）：GET /api/panorama/todos。

覆盖三类计数的口径边界：
- `pending_approval` 随角色变化（admin 全量 / pm 仅自己绑定版本 / 其余 0）；
- `my_reserved_slots` 只算 reserved 且未过期，他人记录不计；
- `my_pending_borrows` 只算自己发起且仍 pending。
"""
from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    BorrowFlow,
    Branch,
    SlotBooking,
    SlotTemplate,
    Strategy,
    StrategyTemplate,
    User,
    Version,
)


class PanoramaTodosTests(TestCase):
    """待办聚合接口：角色口径 + 计数边界 + 方法守卫。"""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="admin", password="123456", role="admin"
        )
        self.pm_a = User.objects.create_user(
            username="pmA", password="123456", role="pm"
        )
        self.pm_b = User.objects.create_user(
            username="pmB", password="123456", role="pm"
        )
        self.builder = User.objects.create_user(
            username="builder", password="123456", role="builder"
        )
        v_a = Version.objects.create(name="27A", pm_user=self.pm_a, status="active")
        v_b = Version.objects.create(name="27B", pm_user=self.pm_b, status="active")
        self.b_a = Branch.objects.create(version=v_a, name="master")
        self.b_b = Branch.objects.create(version=v_b, name="master")
        template = StrategyTemplate.objects.create(
            name="晚间全量冒烟", smoke_minutes=480, analysis_minutes=120
        )
        # 27A 与 27B 各一条策略，用于区分「待我审批」的版本归属
        self.s_a = Strategy.objects.create(
            branch=self.b_a, template=template, name="27A-主",
            build_start_time="22:00", push_mode="normal", created_by=self.pm_a,
        )
        self.s_b = Strategy.objects.create(
            branch=self.b_b, template=template, name="27B-主",
            build_start_time="23:00", push_mode="normal", created_by=self.pm_b,
        )
        self.slot_template = SlotTemplate.objects.create(
            name="夜间回归", start_time=time(19, 0), end_time=time(22, 0)
        )
        self.today = timezone.localdate()

    def _auth(self, user):
        resp = self.client.post(
            "/api/auth/login",
            {"username": user.username, "password": "123456"},
            format="json",
        )
        token = resp.json()["data"]["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def _flow(self, strategy, borrower, target, status="pending"):
        return BorrowFlow.objects.create(
            strategy=strategy, borrower=borrower, target_branch=target,
            new_build_time="21:30", status=status,
        )

    def _booking(self, date, user, status="reserved"):
        return SlotBooking.objects.create(
            date=date, template=self.slot_template,
            start_snapshot=self.slot_template.start_time,
            end_snapshot=self.slot_template.end_time,
            status=status, user=user, purpose="回归抢占",
            version=self.b_a.version, branch=self.b_a,
        )

    def _todos(self, user):
        self._auth(user)
        resp = self.client.get("/api/panorama/todos")
        self.assertEqual(resp.status_code, 200)
        return resp.json()["data"]

    def test_pending_approval_scope_by_role(self):
        """admin 全量；pm 仅「被借用策略所属版本 = 自己绑定版本」的申请。"""
        self._flow(self.s_a, self.builder, self.b_b)
        self._flow(self.s_a, self.pm_b, self.b_b)
        self._flow(self.s_b, self.builder, self.b_a)
        # 已处理的不计入
        self._flow(self.s_a, self.pm_b, self.b_b, status="rejected")

        self.assertEqual(self._todos(self.admin)["pending_approval"], 3)
        self.assertEqual(self._todos(self.pm_a)["pending_approval"], 2)
        self.assertEqual(self._todos(self.pm_b)["pending_approval"], 1)
        # 非 admin/pm 无审批权
        self.assertEqual(self._todos(self.builder)["pending_approval"], 0)

    def test_my_counts_ignore_others_and_inactive(self):
        self._flow(self.s_a, self.builder, self.b_b)
        self._flow(self.s_a, self.pm_b, self.b_b)
        self._booking(self.today + timedelta(days=1), self.builder)
        # 过期 / 已释放 / 他人 均不计入我的有效抢占
        self._booking(self.today - timedelta(days=3), self.builder)
        self._booking(self.today + timedelta(days=2), self.builder, status="released")
        self._booking(self.today + timedelta(days=3), self.pm_a)

        data = self._todos(self.builder)
        self.assertEqual(data["my_reserved_slots"], 1)
        self.assertEqual(data["my_pending_borrows"], 1)

    def test_requires_auth_and_get_only(self):
        resp = self.client.get("/api/panorama/todos")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], 40100)

        self._auth(self.builder)
        resp = self.client.post("/api/panorama/todos", {}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
