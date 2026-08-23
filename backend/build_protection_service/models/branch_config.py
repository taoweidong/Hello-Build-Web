"""分支配置领域模型：工程库 / 分支-工程关联 / 启动配置 / 分支授权 / 运行实例。"""
from django.db import models


class Project(models.Model):
    """工程库：独立实体，分支通过 BranchProject 关联。"""

    name = models.CharField("工程名", max_length=100, unique=True)
    repository_url = models.CharField("仓库地址", max_length=255, blank=True, default="")
    description = models.TextField("描述", blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "工程"
        verbose_name_plural = "工程"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name


class BranchProject(models.Model):
    """分支↔工程关联：唯一约束 + 启用标记。"""

    branch = models.ForeignKey(
        "Branch", on_delete=models.CASCADE, related_name="branch_projects"
    )
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="branch_projects"
    )
    enabled = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "分支工程关联"
        verbose_name_plural = "分支工程关联"
        unique_together = ("branch", "project")
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.branch}/{self.project}"


class StartupConfig(models.Model):
    """启动配置：每条分支工程关联一份（OneToOne）。"""

    branch_project = models.OneToOneField(
        BranchProject, on_delete=models.CASCADE, related_name="startup_config"
    )
    command = models.CharField("启动命令", max_length=255, blank=True, default="")
    args = models.JSONField("参数", default=list, blank=True)
    env_vars = models.JSONField("环境变量", default=dict, blank=True)
    working_directory = models.CharField("工作目录", max_length=255, blank=True, default="")
    timeout_seconds = models.PositiveIntegerField("启动超时(秒)", default=60)
    auto_restart = models.BooleanField("自动重启", default=False)
    raw_json = models.TextField("原始配置JSON", blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "启动配置"
        verbose_name_plural = "启动配置"

    def __str__(self) -> str:
        return f"config#{self.branch_project_id}"


class BranchPermission(models.Model):
    """分支级授权：VIEWER/OPERATOR/ADMIN，分支+用户唯一。"""

    ROLE_CHOICES = (
        ("VIEWER", "查看者"),
        ("OPERATOR", "操作者"),
        ("ADMIN", "管理员"),
    )

    branch = models.ForeignKey(
        "Branch", on_delete=models.CASCADE, related_name="permissions"
    )
    user = models.ForeignKey(
        "User", on_delete=models.CASCADE, related_name="branch_permissions"
    )
    role = models.CharField("角色", max_length=10, choices=ROLE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "分支授权"
        verbose_name_plural = "分支授权"
        unique_together = ("branch", "user")

    def __str__(self) -> str:
        return f"{self.branch}/{self.user}/{self.role}"


class Instance(models.Model):
    """运行实例：纯状态机模拟（STARTING/RUNNING/STOPPED/ERROR）。"""

    STATUS_CHOICES = (
        ("STARTING", "启动中"),
        ("RUNNING", "运行中"),
        ("STOPPED", "已停止"),
        ("ERROR", "异常"),
    )

    branch_project = models.ForeignKey(
        BranchProject, on_delete=models.CASCADE, related_name="instances"
    )
    status = models.CharField("状态", max_length=10, choices=STATUS_CHOICES, default="STOPPED")
    pid = models.IntegerField("进程号", null=True, blank=True)
    started_at = models.DateTimeField("启动时间", null=True, blank=True)
    stopped_at = models.DateTimeField("停止时间", null=True, blank=True)
    last_heartbeat_at = models.DateTimeField("最近心跳", null=True, blank=True)
    exit_code = models.IntegerField("退出码", null=True, blank=True)
    log_tail = models.TextField("日志尾部", blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "运行实例"
        verbose_name_plural = "运行实例"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"instance#{self.id}-{self.status}"