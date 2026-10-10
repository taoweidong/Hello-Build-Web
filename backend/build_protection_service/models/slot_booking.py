"""时段抢占领域模型：时间段模板 / 抢占记录。

- 模板由管理员提前配置（每日循环 + 适用星期 + 生效范围）；
- 抢占记录保留模板时间快照，模板后续改动不影响历史抢占展示；
- date+template 在 reserved 状态下数据库层唯一，根绝并发双抢。
"""
from django.db import models
from django.db.models import Q


class SlotTemplate(models.Model):
    """时间段模板：每日循环的可抢占时段（不支持跨天，强制 start < end）。"""

    name = models.CharField("时段名称", max_length=50, unique=True)
    start_time = models.TimeField("开始时间")
    end_time = models.TimeField("结束时间")
    weekdays = models.CharField(
        "适用星期", max_length=20, blank=True, default="",
        help_text='逗号分隔，1=周一 … 7=周日；空表示每天',
    )
    effective_from = models.DateField("生效起始日", null=True, blank=True)
    effective_to = models.DateField("生效截止日", null=True, blank=True)
    color = models.CharField("标识色", max_length=20, default="#409eff")
    sort_order = models.IntegerField("排序", default=0)
    enabled = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "时间段模板"
        verbose_name_plural = "时间段模板"
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return f"{self.name} {self.start_time:%H:%M}-{self.end_time:%H:%M}"


class SlotBooking(models.Model):
    """抢占记录：先到先得，一人可抢同日多个不同时段。"""

    STATUS_CHOICES = (
        ("reserved", "已抢占"),
        ("released", "已释放"),
        ("expired", "已过期"),
    )

    date = models.DateField("抢占日期")
    template = models.ForeignKey(
        SlotTemplate, on_delete=models.PROTECT, related_name="bookings", verbose_name="时段模板"
    )
    start_snapshot = models.TimeField("开始时间快照")
    end_snapshot = models.TimeField("结束时间快照")
    status = models.CharField("状态", max_length=10, choices=STATUS_CHOICES, default="reserved")
    user = models.ForeignKey(
        "User", on_delete=models.PROTECT, related_name="slot_bookings", verbose_name="抢占人"
    )
    purpose = models.CharField("用途说明", max_length=200)
    version = models.ForeignKey(
        "Version", on_delete=models.PROTECT, related_name="slot_bookings", verbose_name="关联版本"
    )
    branch = models.ForeignKey(
        "Branch", on_delete=models.PROTECT, related_name="slot_bookings", verbose_name="关联分支"
    )
    created_at = models.DateTimeField("抢占时刻", auto_now_add=True)
    released_at = models.DateTimeField("释放时刻", null=True, blank=True)
    release_reason = models.CharField("释放原因", max_length=200, blank=True, default="")

    class Meta:
        verbose_name = "时段抢占记录"
        verbose_name_plural = "时段抢占记录"
        ordering = ["date", "start_snapshot", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["date", "template"],
                condition=Q(status="reserved"),
                name="uniq_slot_booking_active",
            ),
        ]
        indexes = [
            models.Index(fields=["date"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.date} {self.template.name} @{self.user}"
