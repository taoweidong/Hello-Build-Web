"""其余业务模型：用户 / 版本 / 分支 / 策略 / 执行 / 日志等。"""
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

    @property
    def bound_version_id(self):
        """PM 绑定版本 id（反向 OneToOne 无自动 *_id 透传属性，显式暴露）。"""
        version = getattr(self, "bound_version", None)
        return version.id if version else None

    def __str__(self) -> str:
        return self.username


class Version(models.Model):
    name = models.CharField("版本号", max_length=100, unique=True)
    pm_user = models.OneToOneField(
        User, on_delete=models.PROTECT, related_name="bound_version", verbose_name="PM"
    )
    status = models.CharField("状态", max_length=20, default="active")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class Branch(models.Model):
    version = models.ForeignKey(
        Version, on_delete=models.CASCADE, related_name="branches"
    )
    name = models.CharField("分支名", max_length=100)
    repository_url = models.CharField("仓库地址", max_length=255, blank=True, default="")
    description = models.TextField("描述", blank=True, default="")

    class Meta:
        unique_together = ("version", "name")

    def __str__(self) -> str:
        return f"{self.version.name}/{self.name}"


class StrategyTemplate(models.Model):
    name = models.CharField("模板名", max_length=100)
    smoke_minutes = models.PositiveIntegerField(default=0)
    analysis_minutes = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=255, blank=True, default="")

    def __str__(self) -> str:
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
        constraints = [
            # 并发兜底（见 specs/2026-10-11-strategy-concurrency-guard-design.md）：
            # 同分支同一构建时刻至多一条启用策略（构建时长相同则区间必重叠，
            # 业务上必然冲突）；跨分支互斥无法用等值约束表达，由事务串行化兜底。
            models.UniqueConstraint(
                fields=["branch", "build_start_time"],
                condition=models.Q(enabled=True),
                name="uniq_active_strategy_branch_time",
            ),
        ]

    def __str__(self) -> str:
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

    def __str__(self) -> str:
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


class RevokedToken(models.Model):
    """登出拉黑的访问令牌：jti 唯一；到期后自然失效，无需人工清理。"""
    jti = models.CharField("令牌唯一标识", max_length=64, unique=True)
    expires_at = models.DateTimeField("过期时间", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.jti


class RuntimeConfig(models.Model):
    """运行期配置（KV 持久化）：admin 修改落库，重启不丢；领域逻辑经 services.config 读取。"""
    key = models.CharField("配置键", max_length=50, unique=True)
    value = models.IntegerField("配置值")
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    def __str__(self) -> str:
        return f"{self.key}={self.value}"