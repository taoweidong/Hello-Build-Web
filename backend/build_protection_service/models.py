"""全部数据模型。对应原 FastAPI 表结构，用 Django ORM 重建。"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """扩展用户：继承 Django 默认认证，新增业务角色字段。"""
    ROLE_CHOICES = (
        ("admin", "管理员"),
        ("pm", "版本负责人"),
        ("builder", "构建人员"),
        ("tester", "测试人员"),
        ("integrator", "集成人员"),
    )
    role = models.CharField("角色", max_length=20, choices=ROLE_CHOICES, default="builder")
    display_name = models.CharField("显示名", max_length=100, blank=True, default="")

    def __str__(self):
        return self.username


class Version(models.Model):
    name = models.CharField("版本号", max_length=100, unique=True)
    pm_user = models.OneToOneField(
        User, on_delete=models.PROTECT, related_name="bound_version", verbose_name="PM"
    )
    status = models.CharField("状态", max_length=20, default="active")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Branch(models.Model):
    version = models.ForeignKey(
        Version, on_delete=models.CASCADE, related_name="branches"
    )
    name = models.CharField("分支名", max_length=100)

    class Meta:
        unique_together = ("version", "name")

    def __str__(self):
        return f"{self.version.name}/{self.name}"


class StrategyTemplate(models.Model):
    name = models.CharField("模板名", max_length=100)
    smoke_minutes = models.PositiveIntegerField(default=0)
    analysis_minutes = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=255, blank=True, default="")

    def __str__(self):
        return self.name


class Strategy(models.Model):
    PUSH_MODE_CHOICES = (("normal", "正常流程推送"), ("sync", "同步推送冒烟"))
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="strategies")
    template = models.ForeignKey(
        StrategyTemplate, on_delete=models.PROTECT, related_name="strategies"
    )
    name = models.CharField("策略名", max_length=200)
    build_start_time = models.CharField("构建开始时间", max_length=5)  # "HH:MM"
    push_start_time = models.CharField("推送开始时间", max_length=5, null=True, blank=True)  # "HH:MM" 可空
    push_mode = models.CharField("推送模式", max_length=10, choices=PUSH_MODE_CHOICES, default="normal")
    enabled = models.BooleanField("启用", default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_strategies", null=True, blank=True
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["build_start_time"]

    def __str__(self):
        return self.name


class ExecutionRound(models.Model):
    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, related_name="rounds")
    exec_date = models.DateField()
    build_start_at = models.DateTimeField(null=True, blank=True)
    build_end_at = models.DateTimeField(null=True, blank=True)
    smoke_start_at = models.DateTimeField(null=True, blank=True)
    smoke_end_at = models.DateTimeField(null=True, blank=True)
    analysis_start_at = models.DateTimeField(null=True, blank=True)
    analysis_end_at = models.DateTimeField(null=True, blank=True)
    push_start_at = models.DateTimeField(null=True, blank=True)
    push_end_at = models.DateTimeField(null=True, blank=True)
    conclusion = models.CharField("结论", max_length=20, null=True, blank=True)
    note = models.CharField(max_length=255, blank=True, default="")
    push_status = models.CharField("推送状态", max_length=20, null=True, blank=True)
    release_approved = models.BooleanField(default=False)

    class Meta:
        unique_together = ("strategy", "exec_date")

    def __str__(self):
        return f"{self.strategy.name}@{self.exec_date}"


class ExecutionLog(models.Model):
    round = models.ForeignKey(ExecutionRound, on_delete=models.CASCADE, related_name="logs")
    stage = models.CharField(max_length=20)
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)


class StrategyChangeLog(models.Model):
    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, related_name="change_logs")
    operator = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    change_desc = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)


class AdminOpLog(models.Model):
    operator = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=50, blank=True, default="")
    target_id = models.CharField(max_length=50, blank=True, default="")
    detail = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class SecurityLog(models.Model):
    username = models.CharField(max_length=100, blank=True, default="")
    action = models.CharField(max_length=100)
    detail = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class VerificationReport(models.Model):
    """验证报告：独立实体，可选关联版本/策略。"""
    CONCLUSION_CHOICES = (("pass", "通过"), ("fail", "不通过"), ("risk", "有风险"))
    STATUS_CHOICES = (("draft", "草稿"), ("published", "已发布"))
    title = models.CharField("标题", max_length=200)
    version = models.ForeignKey(Version, on_delete=models.SET_NULL, null=True, blank=True, related_name="reports")
    strategy = models.ForeignKey(Strategy, on_delete=models.SET_NULL, null=True, blank=True, related_name="reports")
    conclusion = models.CharField("结论", max_length=20, choices=CONCLUSION_CHOICES)
    environment = models.CharField("验证环境", max_length=255, blank=True, default="")
    summary = models.TextField("验证内容")
    risks = models.TextField("问题与风险", blank=True, default="")
    remark = models.TextField("备注", blank=True, default="")
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default="draft")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_reports")
    published_at = models.DateTimeField(null=True, blank=True)
    publish_count = models.PositiveIntegerField("发布次数", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class ReportPublishRecord(models.Model):
    """发布暨推送记录：每次发布追加一条，含截图与模拟推送摘要。"""
    report = models.ForeignKey(VerificationReport, on_delete=models.CASCADE, related_name="publish_records")
    publisher = models.ForeignKey(User, on_delete=models.PROTECT, related_name="report_publishes")
    screenshot = models.TextField("页面截图 base64")
    push_status = models.CharField("推送状态", max_length=20, default="pushed")
    push_target = models.CharField("模拟接收人", max_length=100, default="构建通知群")
    message = models.CharField("推送摘要", max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.report.title} 发布于 {self.created_at:%m-%d %H:%M}"