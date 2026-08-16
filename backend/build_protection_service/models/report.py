"""验证报告领域模型：报告主表与修改记录表。

设计约定：两表均不与其他表建立外键关联，报告功能数据库表独立；
版本/策略/作者等信息以文本快照保存，记录修改时由 ReportRevisionLog 留痕。
"""
from django.db import models


class VerificationReport(models.Model):
    """验证报告：独立单表，版本 / 策略 / 作者均为文本快照（不使用外键）。"""

    CONCLUSION_CHOICES = (("pass", "通过"), ("fail", "不通过"), ("risk", "有风险"))
    STATUS_CHOICES = (("draft", "草稿"), ("published", "已发布"))

    title = models.CharField("标题", max_length=200)
    version_name = models.CharField("版本", max_length=100, blank=True, default="")
    strategy_name = models.CharField("策略", max_length=200, blank=True, default="")
    conclusion = models.CharField("结论", max_length=20, choices=CONCLUSION_CHOICES)
    environment = models.CharField("验证环境", max_length=255, blank=True, default="")
    summary = models.TextField("验证内容")
    risks = models.TextField("问题与风险", blank=True, default="")
    remark = models.TextField("备注", blank=True, default="")
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default="draft")
    created_by_username = models.CharField("作者账号", max_length=100, blank=True, default="")
    published_at = models.DateTimeField("发布时间", null=True, blank=True)
    publish_count = models.PositiveIntegerField("发布次数", default=0)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "验证报告"
        verbose_name_plural = "验证报告"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title


class ReportRevisionLog(models.Model):
    """报告修改记录：独立单表，report_id 仅存整数标识（不使用外键）。

    action 取值：create（创建）/ update（修改）/ publish（发布）；
    字段级留痕：field_name 记录被修改字段，before_value / after_value 记录前后内容。
    """

    ACTION_CHOICES = (("create", "创建"), ("update", "修改"), ("publish", "发布"))

    report_id = models.IntegerField("报告ID")
    report_title = models.CharField("报告标题", max_length=200, blank=True, default="")
    action = models.CharField("动作", max_length=20, choices=ACTION_CHOICES)
    field_name = models.CharField("修改字段", max_length=100, blank=True, default="")
    before_value = models.TextField("修改前内容", blank=True, default="")
    after_value = models.TextField("修改后内容", blank=True, default="")
    operator_username = models.CharField("操作人账号", max_length=100)
    created_at = models.DateTimeField("操作时间", auto_now_add=True)

    class Meta:
        verbose_name = "报告修改记录"
        verbose_name_plural = "报告修改记录"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"报告#{self.report_id}-{self.action}"