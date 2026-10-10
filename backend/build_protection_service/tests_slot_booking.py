"""时段抢占模块测试：模型约束 / 服务层 / API 三层。"""
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

    def test_detect_template_overlap(self):
        from .services.slot_booking import detect_template_overlap

        overlap = SlotTemplate.objects.create(
            name="上午二段", start_time=time(10, 0), end_time=time(11, 0),
            weekdays="1,2,3,4,5", sort_order=3,
        )
        warnings = detect_template_overlap(self.morning)
        self.assertTrue(any("上午二段" in w for w in warnings))
        self.assertFalse(any("夜间回归" in w for w in warnings))  # 时间不重叠
        # 星期不相交：仅周末模板 vs 工作日上午
        weekend_only = SlotTemplate.objects.create(
            name="周末窗口", start_time=time(9, 0), end_time=time(10, 0),
            weekdays="6,7", sort_order=4,
        )
        self.assertFalse(any("周末窗口" in w for w in detect_template_overlap(self.morning)))
        self.assertFalse(any("上午窗口" in w for w in detect_template_overlap(weekend_only)))
