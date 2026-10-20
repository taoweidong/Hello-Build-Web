"""时段抢占模块测试：模型约束 / 服务层 / API 三层。

2026-10-20 页面精简：时段模板 CRUD 与 admin 全量记录列表随时段配置页下线，
模板改经 seed / django-admin 写入，相应用例已删；未授权契约改经 mine 端点锁定。
"""
from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Branch, SlotBooking, SlotTemplate, Version

User = get_user_model()


def _auth(client, user):
    """登录并携带 token，失败会抛异常暴露契约问题。"""
    resp = client.post(
        "/api/auth/login", {"username": user.username, "password": "123456"}, format="json"
    )
    token = resp.json()["data"]["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


def _next_date_with(weekday_iso: int, start=None):
    """从 start（默认今天）起找第一个指定星期的日期（1=周一…7=周日）。"""
    d = start or timezone.localdate()
    for i in range(14):
        cand = d + timedelta(days=i)
        if cand.isoweekday() == weekday_iso:
            return cand
    raise AssertionError("14 天内未找到目标星期")


class SlotBookingFixture(TestCase):
    """共享夹具：admin/pm/builder 用户 + 两版本两分支 + 两个时段模板。"""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin1", password="123456", role="admin", display_name="管理员"
        )
        self.pm = User.objects.create_user(
            username="pm1", password="123456", role="pm", display_name="27A负责人"
        )
        self.pm_b = User.objects.create_user(
            username="pm2", password="123456", role="pm", display_name="27B负责人"
        )
        self.builder = User.objects.create_user(
            username="bob", password="123456", role="builder", display_name="构建人员"
        )
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.version_b = Version.objects.create(name="27B", pm_user=self.pm_b, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")
        self.branch_b = Branch.objects.create(version=self.version_b, name="master")
        # 上午窗口：仅工作日；夜间回归：每天
        self.morning = SlotTemplate.objects.create(
            name="上午窗口", start_time=time(8, 0), end_time=time(12, 0),
            weekdays="1,2,3,4,5", sort_order=1, color="#67c23a",
        )
        self.evening = SlotTemplate.objects.create(
            name="夜间回归", start_time=time(19, 0), end_time=time(22, 0), sort_order=2,
        )
        self.today = timezone.localdate()
        self.client = APIClient()


class SlotBookingModelTests(SlotBookingFixture):
    def test_partial_unique_blocks_double_booking(self):
        """同日同模板两条 reserved 触发唯一约束；释放后可再占。"""
        d = _next_date_with(1)  # 下一个周一
        SlotBooking.objects.create(
            date=d, template=self.morning,
            start_snapshot=self.morning.start_time, end_snapshot=self.morning.end_time,
            user=self.pm, purpose="首次抢占", version=self.version, branch=self.branch,
        )
        with self.assertRaises(IntegrityError):
            SlotBooking.objects.create(
                date=d, template=self.morning,
                start_snapshot=self.morning.start_time, end_snapshot=self.morning.end_time,
                user=self.builder, purpose="并发抢占", version=self.version, branch=self.branch,
            )

    def test_released_allows_rebooking(self):
        d = _next_date_with(2)
        first = SlotBooking.objects.create(
            date=d, template=self.evening,
            start_snapshot=self.evening.start_time, end_snapshot=self.evening.end_time,
            user=self.pm, purpose="首次", version=self.version, branch=self.branch,
        )
        first.status = "released"
        first.save(update_fields=["status"])
        second = SlotBooking.objects.create(
            date=d, template=self.evening,
            start_snapshot=self.evening.start_time, end_snapshot=self.evening.end_time,
            user=self.builder, purpose="再次抢占", version=self.version, branch=self.branch,
        )
        self.assertEqual(second.status, "reserved")

    def test_str_representations(self):
        self.assertIn("上午窗口", str(self.morning))
        booking = SlotBooking.objects.create(
            date=self.today, template=self.evening,
            start_snapshot=self.evening.start_time, end_snapshot=self.evening.end_time,
            user=self.pm, purpose="演示", version=self.version, branch=self.branch,
        )
        self.assertIn("夜间回归", str(booking))


class SlotBookingServiceTests(SlotBookingFixture):
    """服务层：校验链 / 日历聚合 / 释放 / 重叠检测。"""

    def test_create_booking_success_with_snapshots(self):
        from .services.slot_booking import create_booking

        d = _next_date_with(1)
        data, err = create_booking(
            self.pm,
            {"date": d.isoformat(), "template_id": self.morning.id,
             "purpose": "27A 回归验证", "version_id": self.version.id,
             "branch_id": self.branch.id},
        )
        self.assertIsNone(err)
        booking = SlotBooking.objects.get(id=data["id"])
        self.assertEqual(booking.start_snapshot, self.morning.start_time)
        self.assertEqual(booking.end_snapshot, self.morning.end_time)
        self.assertEqual(booking.user_id, self.pm.id)
        self.assertTrue(data["is_mine"])

    def test_create_booking_past_date_rejected(self):
        from .services.slot_booking import create_booking

        past = self.today - timedelta(days=1)
        _, err = create_booking(
            self.pm,
            {"date": past.isoformat(), "template_id": self.evening.id,
             "purpose": "过去日期", "version_id": self.version.id,
             "branch_id": self.branch.id},
        )
        self.assertEqual(err["code"], 42201)
        self.assertIn("过去", err["message"])

    def test_create_booking_beyond_horizon_rejected(self):
        from django.conf import settings
        from .services.slot_booking import create_booking

        far = self.today + timedelta(days=int(settings.SLOT_BOOKING_HORIZON_DAYS) + 1)
        _, err = create_booking(
            self.pm,
            {"date": far.isoformat(), "template_id": self.evening.id,
             "purpose": "超窗口", "version_id": self.version.id,
             "branch_id": self.branch.id},
        )
        self.assertEqual(err["code"], 42201)
        self.assertIn("窗口", err["message"])

    def test_create_booking_horizon_boundary_ok(self):
        from django.conf import settings
        from .services.slot_booking import create_booking

        edge = self.today + timedelta(days=int(settings.SLOT_BOOKING_HORIZON_DAYS))
        data, err = create_booking(
            self.pm,
            {"date": edge.isoformat(), "template_id": self.evening.id,
             "purpose": "窗口边界", "version_id": self.version.id,
             "branch_id": self.branch.id},
        )
        self.assertIsNone(err)
        self.assertTrue(data["id"])

    def test_create_booking_weekday_mismatch_rejected(self):
        from .services.slot_booking import create_booking

        saturday = _next_date_with(6)
        _, err = create_booking(
            self.pm,
            {"date": saturday.isoformat(), "template_id": self.morning.id,
             "purpose": "周六抢上午", "version_id": self.version.id,
             "branch_id": self.branch.id},
        )
        self.assertEqual(err["code"], 42201)
        self.assertIn("适用", err["message"])

    def test_create_booking_effective_range_rejected(self):
        from .services.slot_booking import create_booking

        limited = SlotTemplate.objects.create(
            name="限时窗口", start_time=time(9, 0), end_time=time(10, 0),
            effective_from=self.today + timedelta(days=20),
            effective_to=self.today + timedelta(days=30),
        )
        soon = self.today + timedelta(days=1)
        _, err = create_booking(
            self.pm,
            {"date": soon.isoformat(), "template_id": limited.id,
             "purpose": "生效期外", "version_id": self.version.id,
             "branch_id": self.branch.id},
        )
        self.assertEqual(err["code"], 42201)
        self.assertIn("生效", err["message"])

    def test_create_booking_disabled_template_rejected(self):
        from .services.slot_booking import create_booking

        self.evening.enabled = False
        self.evening.save(update_fields=["enabled"])
        _, err = create_booking(
            self.pm,
            {"date": (self.today + timedelta(days=1)).isoformat(),
             "template_id": self.evening.id, "purpose": "停用模板",
             "version_id": self.version.id, "branch_id": self.branch.id},
        )
        self.assertEqual(err["code"], 42201)
        self.assertIn("停用", err["message"])

    def test_create_booking_branch_version_mismatch_rejected(self):
        from .services.slot_booking import create_booking

        _, err = create_booking(
            self.pm,
            {"date": (self.today + timedelta(days=1)).isoformat(),
             "template_id": self.evening.id, "purpose": "跨版本分支",
             "version_id": self.version.id, "branch_id": self.branch_b.id},
        )
        self.assertEqual(err["code"], 42201)
        self.assertIn("不属于", err["message"])

    def test_create_booking_purpose_length_rejected(self):
        from .services.slot_booking import create_booking

        _, err = create_booking(
            self.pm,
            {"date": (self.today + timedelta(days=1)).isoformat(),
             "template_id": self.evening.id, "purpose": "短",
             "version_id": self.version.id, "branch_id": self.branch.id},
        )
        self.assertEqual(err["code"], 42201)
        self.assertIn("用途", err["message"])

    def test_create_booking_duplicate_returns_40904(self):
        from .services.slot_booking import create_booking

        d = _next_date_with(3)
        payload = {"date": d.isoformat(), "template_id": self.morning.id,
                   "purpose": "先到先得", "version_id": self.version.id,
                   "branch_id": self.branch.id}
        data, err = create_booking(self.pm, payload)
        self.assertIsNone(err)
        data2, err2 = create_booking(self.builder, payload)
        self.assertIsNone(data2)
        self.assertEqual(err2["code"], 40904)
        self.assertIn("27A负责人", err2["message"])  # message 带占有人显示名

    def test_create_booking_invalid_date_format(self):
        from .services.slot_booking import create_booking

        _, err = create_booking(
            self.pm,
            {"date": "2026/10/14", "template_id": self.evening.id, "purpose": "格式错",
             "version_id": self.version.id, "branch_id": self.branch.id},
        )
        self.assertEqual(err["code"], 42201)

    def test_build_calendar_basic_shape(self):
        from .services.slot_booking import build_slot_calendar

        data, err = build_slot_calendar(self.today.strftime("%Y-%m"), self.pm)
        self.assertIsNone(err)
        self.assertEqual(data["month"], self.today.strftime("%Y-%m"))
        self.assertEqual(len(data["templates"]), 2)
        self.assertIn("horizon_days", data)
        # 一个月内每天（无论周末）都应存在"夜间回归"条目（每天适用）
        saturday = _next_date_with(6)
        sat_key = saturday.isoformat() if saturday.month == self.today.month else None
        if sat_key:
            entries = data["days"][sat_key]
            evening_entry = next(e for e in entries if e["template_id"] == self.evening.id)
            self.assertEqual(evening_entry["status"], "available")
            morning_entries = [e for e in entries if e["template_id"] == self.morning.id]
            self.assertEqual(morning_entries, [])  # 周六上午窗口不适用

    def test_build_calendar_marks_mine_and_reserved(self):
        from .services.slot_booking import build_slot_calendar, create_booking

        d = _next_date_with(4)
        create_booking(self.pm, {"date": d.isoformat(), "template_id": self.evening.id,
                                 "purpose": "占坑测试", "version_id": self.version.id,
                                 "branch_id": self.branch.id})
        data, _ = build_slot_calendar(d.strftime("%Y-%m"), self.pm)
        entry = next(e for e in data["days"][d.isoformat()]
                     if e["template_id"] == self.evening.id)
        self.assertEqual(entry["status"], "reserved")
        self.assertTrue(entry["booking"]["is_mine"])
        self.assertEqual(entry["booking"]["user_name"], "27A负责人")
        # 他人视角
        data2, _ = build_slot_calendar(d.strftime("%Y-%m"), self.builder)
        entry2 = next(e for e in data2["days"][d.isoformat()]
                      if e["template_id"] == self.evening.id)
        self.assertFalse(entry2["booking"]["is_mine"])

    def test_build_calendar_invalid_month(self):
        from .services.slot_booking import build_slot_calendar

        _, err = build_slot_calendar("2026/10", self.pm)
        self.assertEqual(err["code"], 42201)

    def test_release_owner_ok(self):
        from .services.slot_booking import create_booking, release_booking

        d = _next_date_with(5)
        data, _ = create_booking(self.pm, {"date": d.isoformat(), "template_id": self.evening.id,
                                           "purpose": "待释放", "version_id": self.version.id,
                                           "branch_id": self.branch.id})
        result, err = release_booking(SlotBooking.objects.get(id=data["id"]), self.pm, "")
        self.assertIsNone(err)
        self.assertEqual(result["status"], "released")
        booking = SlotBooking.objects.get(id=data["id"])
        self.assertIsNotNone(booking.released_at)

    def test_release_by_other_rejected(self):
        from .services.slot_booking import create_booking, release_booking

        d = _next_date_with(5)
        data, _ = create_booking(self.pm, {"date": d.isoformat(), "template_id": self.evening.id,
                                           "purpose": "他人释放", "version_id": self.version.id,
                                           "branch_id": self.branch.id})
        _, err = release_booking(SlotBooking.objects.get(id=data["id"]), self.builder, "想抢")
        self.assertEqual(err["code"], 40301)

    def test_release_by_admin_requires_reason(self):
        from .services.slot_booking import create_booking, release_booking

        d = _next_date_with(5)
        data, _ = create_booking(self.pm, {"date": d.isoformat(), "template_id": self.evening.id,
                                           "purpose": "admin释放", "version_id": self.version.id,
                                           "branch_id": self.branch.id})
        booking = SlotBooking.objects.get(id=data["id"])
        _, err = release_booking(booking, self.admin, "")
        self.assertEqual(err["code"], 42201)
        result, err2 = release_booking(booking, self.admin, "资源调度调整")
        self.assertIsNone(err2)
        self.assertEqual(result["status"], "released")

    def test_release_twice_rejected(self):
        from .services.slot_booking import create_booking, release_booking

        d = _next_date_with(5)
        data, _ = create_booking(self.pm, {"date": d.isoformat(), "template_id": self.evening.id,
                                           "purpose": "重复释放", "version_id": self.version.id,
                                           "branch_id": self.branch.id})
        booking = SlotBooking.objects.get(id=data["id"])
        release_booking(booking, self.pm, "")
        _, err = release_booking(booking, self.pm, "")
        self.assertEqual(err["code"], 42201)

class SlotBookingApiTests(SlotBookingFixture):
    """全接口集成：认证、权限矩阵、校验链、并发冲突、分页筛选。"""

    def _booking_payload(self, date=None, template=None, version=None, branch=None, purpose="回归验证"):
        return {
            "date": (date or _next_date_with(1)).isoformat(),
            "template_id": (template or self.morning).id,
            "purpose": purpose,
            "version_id": (version or self.version).id,
            "branch_id": (branch or self.branch).id,
        }

    def test_unauthorized_returns_40100(self):
        """无 token 访问 mine → 40100（模板列表端点随时段配置页下线，改锁 mine）。"""
        resp = self.client.get("/api/slot-bookings/mine")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], 40100)

    def test_booking_create_and_conflict_40904(self):
        _auth(self.client, self.pm)
        resp = self.client.post("/api/slot-bookings", self._booking_payload(), format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["user_name"], "27A负责人")
        self.assertTrue(data["is_mine"])

        # 并发双抢 → 40904，message 带占有人
        _auth(self.client, self.builder)
        resp = self.client.post("/api/slot-bookings", self._booking_payload(), format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40904)
        self.assertIn("27A负责人", resp.json()["message"])

        # 本人释放后，他人可再抢
        _auth(self.client, self.pm)
        resp = self.client.post(f"/api/slot-bookings/{data['id']}/release", {}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["status"], "released")
        _auth(self.client, self.builder)
        resp = self.client.post("/api/slot-bookings", self._booking_payload(), format="json")
        self.assertEqual(resp.status_code, 200)

    def test_booking_validation_errors(self):
        _auth(self.client, self.pm)
        # 过去日期
        resp = self.client.post(
            "/api/slot-bookings",
            self._booking_payload(date=self.today - timedelta(days=1), template=self.evening),
            format="json",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        # 分支不属于所选版本
        resp = self.client.post(
            "/api/slot-bookings",
            self._booking_payload(template=self.evening, branch=self.branch_b),
            format="json",
        )
        self.assertEqual(resp.json()["code"], 42201)
        self.assertIn("不属于", resp.json()["message"])
        # 用途过短
        resp = self.client.post(
            "/api/slot-bookings", self._booking_payload(template=self.evening, purpose="短"),
            format="json",
        )
        self.assertEqual(resp.json()["code"], 42201)
        # 模板不存在
        resp = self.client.post(
            "/api/slot-bookings",
            self._booking_payload(template=self.evening, purpose="模板缺失") | {"template_id": 99999},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["code"], 40401)

    def test_mine_pagination(self):
        _auth(self.client, self.pm)
        for offset in range(3):
            self.client.post(
                "/api/slot-bookings",
                self._booking_payload(
                    date=self.today + timedelta(days=1 + offset), template=self.evening,
                    purpose=f"分页{offset}",
                ),
                format="json",
            )
        resp = self.client.get("/api/slot-bookings/mine?page=1&page_size=2")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()["data"]
        self.assertEqual(body["total"], 3)
        self.assertEqual(len(body["items"]), 2)
        self.assertEqual(body["page_size"], 2)

    def test_calendar_endpoint(self):
        _auth(self.client, self.pm)
        self.client.post("/api/slot-bookings", self._booking_payload(), format="json")
        resp = self.client.get("/api/slot-calendar")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["month"], self.today.strftime("%Y-%m"))
        self.assertEqual(len(data["templates"]), 2)
        self.assertTrue(data["days"])

    def test_calendar_endpoint_invalid_month(self):
        _auth(self.client, self.pm)
        resp = self.client.get("/api/slot-calendar?month=2026/10")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_release_permission_matrix(self):
        # builder 抢占
        _auth(self.client, self.builder)
        resp = self.client.post(
            "/api/slot-bookings",
            self._booking_payload(template=self.evening, purpose="他人测试"),
            format="json",
        )
        booking_id = resp.json()["data"]["id"]
        # pm 无权释放他人 → 40301
        _auth(self.client, self.pm)
        resp = self.client.post(f"/api/slot-bookings/{booking_id}/release", {}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], 40301)
        # admin 释放他人缺原因 → 42201
        _auth(self.client, self.admin)
        resp = self.client.post(f"/api/slot-bookings/{booking_id}/release", {}, format="json")
        self.assertEqual(resp.json()["code"], 42201)
        # admin 释放他人带原因 → 200
        resp = self.client.post(
            f"/api/slot-bookings/{booking_id}/release",
            {"release_reason": "资源调度调整"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["status"], "released")
        # 再释放 → 42201
        resp = self.client.post(
            f"/api/slot-bookings/{booking_id}/release",
            {"release_reason": "重复"},
            format="json",
        )
        self.assertEqual(resp.json()["code"], 42201)
        # 不存在的记录 → 40401
        resp = self.client.post("/api/slot-bookings/99999/release", {}, format="json")
        self.assertEqual(resp.status_code, 404)


class SlotBookingRescheduleTests(SlotBookingFixture):
    """抢占改期（P2-R2）：PATCH /api/slot-bookings/<pk>。"""

    def _make(self, date=None, template=None, user=None, status="reserved"):
        tpl = template or self.morning
        return SlotBooking.objects.create(
            date=date or _next_date_with(1), template=tpl,
            start_snapshot=tpl.start_time, end_snapshot=tpl.end_time,
            status=status, user=user or self.builder, purpose="原始用途",
            version=self.version, branch=self.branch,
        )

    def _patch(self, booking_id, payload):
        return self.client.patch(
            f"/api/slot-bookings/{booking_id}", payload, format="json"
        )

    def test_owner_reschedules_date_and_template(self):
        """本人改期：日期 + 时段 + 用途一并更新，快照随模板刷新。"""
        b = self._make()
        _auth(self.client, self.builder)
        target = _next_date_with(2)
        resp = self._patch(
            b.id,
            {
                "date": target.isoformat(),
                "template_id": self.evening.id,
                "purpose": "改期用途",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["status"], "reserved")
        b.refresh_from_db()
        self.assertEqual(b.date, target)
        self.assertEqual(b.template_id, self.evening.id)
        self.assertEqual(b.purpose, "改期用途")
        self.assertEqual(b.start_snapshot, self.evening.start_time)
        self.assertEqual(b.end_snapshot, self.evening.end_time)

    def test_partial_payload_keeps_original_values(self):
        """空载荷 = 原样保留（缺省字段沿用原值，不误清）。"""
        original_date = _next_date_with(1)
        b = self._make(date=original_date)
        _auth(self.client, self.builder)
        resp = self._patch(b.id, {})
        self.assertEqual(resp.status_code, 200)
        b.refresh_from_db()
        self.assertEqual(b.date, original_date)
        self.assertEqual(b.template_id, self.morning.id)
        self.assertEqual(b.purpose, "原始用途")

    def test_forbidden_for_other_user(self):
        b = self._make(user=self.builder)
        _auth(self.client, self.pm)
        resp = self._patch(b.id, {"date": _next_date_with(3).isoformat()})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], 40301)

    def test_admin_can_reschedule_others(self):
        b = self._make(user=self.builder)
        _auth(self.client, self.admin)
        target = _next_date_with(3)
        resp = self._patch(b.id, {"date": target.isoformat()})
        self.assertEqual(resp.status_code, 200)
        b.refresh_from_db()
        self.assertEqual(b.date, target)

    def test_target_conflict_returns_40904(self):
        """目标 (date, template) 已被他人 reserved → 40904 且原记录不动。"""
        d1 = _next_date_with(1)
        d2 = _next_date_with(2)
        mine = self._make(date=d1)
        SlotBooking.objects.create(
            date=d2, template=self.morning,
            start_snapshot=self.morning.start_time, end_snapshot=self.morning.end_time,
            user=self.pm, purpose="他人占用", version=self.version_b, branch=self.branch_b,
        )
        _auth(self.client, self.builder)
        resp = self._patch(mine.id, {"date": d2.isoformat()})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40904)
        mine.refresh_from_db()
        self.assertEqual(mine.date, d1)

    def test_released_record_cannot_reschedule(self):
        b = self._make(status="released")
        _auth(self.client, self.builder)
        resp = self._patch(b.id, {"date": _next_date_with(3).isoformat()})
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

    def test_past_date_rejected(self):
        b = self._make()
        _auth(self.client, self.builder)
        resp = self._patch(b.id, {"date": (self.today - timedelta(days=1)).isoformat()})
        self.assertEqual(resp.json()["code"], 42201)
        self.assertIn("过去", resp.json()["message"])

    def test_beyond_horizon_rejected(self):
        b = self._make()
        _auth(self.client, self.builder)
        resp = self._patch(b.id, {"date": (self.today + timedelta(days=90)).isoformat()})
        self.assertEqual(resp.json()["code"], 42201)
        self.assertIn("窗口", resp.json()["message"])

    def test_weekday_mismatch_rejected(self):
        """morning 仅工作日，改到周日 → 42201（与抢占同一套适用性校验）。"""
        b = self._make()
        _auth(self.client, self.builder)
        resp = self._patch(b.id, {"date": _next_date_with(7).isoformat()})
        self.assertEqual(resp.json()["code"], 42201)
        self.assertIn("适用范围", resp.json()["message"])

    def test_not_found(self):
        _auth(self.client, self.builder)
        resp = self._patch(999999, {"date": _next_date_with(2).isoformat()})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["code"], 40401)

    def test_get_method_not_allowed(self):
        """该路径只映射 PATCH；未支持的方法经契约异常处理器归一为 42201（R3-B16）。"""
        b = self._make()
        _auth(self.client, self.builder)
        resp = self.client.get(f"/api/slot-bookings/{b.id}")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)

