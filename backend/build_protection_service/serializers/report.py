"""报告序列化器：报告主表与修改记录表（一一对应 ORM 模型）。"""
from rest_framework import serializers

from ..models import ReportRevisionLog, Strategy, VerificationReport

# 结论合法取值（与模型 CONCLUSION_CHOICES 一致）
VALID_CONCLUSIONS = tuple(dict(VerificationReport.CONCLUSION_CHOICES).keys())


class ReportSerializer(serializers.ModelSerializer):
    """验证报告序列化：结论/状态中文标签 + 更新标记计算字段。"""

    # 显式声明可写字段：allow_blank 放行空串，由 validate() 统一输出中文错误
    #（若走 ModelSerializer 默认，空串会在字段级被“该字段不能为空”拦截，丢失定制消息）
    title = serializers.CharField(allow_blank=True, max_length=200)
    version_name = serializers.CharField(allow_blank=True, max_length=100, required=False)
    strategy_name = serializers.CharField(allow_blank=True, max_length=200, required=False)
    conclusion = serializers.CharField(allow_blank=True, max_length=20)
    environment = serializers.CharField(allow_blank=True, max_length=255, required=False)
    summary = serializers.CharField(allow_blank=True)
    risks = serializers.CharField(allow_blank=True, required=False)
    remark = serializers.CharField(allow_blank=True, required=False)
    conclusion_label = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()
    is_updated = serializers.SerializerMethodField()
    update_count = serializers.SerializerMethodField()
    published_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S", read_only=True)
    created_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S", read_only=True)

    class Meta:
        model = VerificationReport
        fields = [
            "id",
            "title",
            "version_name",
            "strategy_name",
            "conclusion",
            "conclusion_label",
            "environment",
            "summary",
            "risks",
            "remark",
            "status",
            "status_label",
            "created_by_username",
            "published_at",
            "publish_count",
            "is_updated",
            "update_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by_username", "status", "publish_count"]

    def get_conclusion_label(self, obj: VerificationReport) -> str:
        return dict(VerificationReport.CONCLUSION_CHOICES).get(obj.conclusion, obj.conclusion)

    def get_status_label(self, obj: VerificationReport) -> str:
        return dict(VerificationReport.STATUS_CHOICES).get(obj.status, obj.status)

    def get_is_updated(self, obj: VerificationReport) -> bool:
        """是否为更新报告：发布次数大于 1 即视为更新发布。"""
        return obj.publish_count > 1

    def get_update_count(self, obj: VerificationReport) -> int:
        """更新次数：发布次数减 1。"""
        return max(obj.publish_count - 1, 0)

    def validate(self, attrs: dict) -> dict:
        title = (attrs.get("title") or "").strip()
        conclusion = attrs.get("conclusion")
        summary = (attrs.get("summary") or "").strip()
        if not title:
            raise serializers.ValidationError({"title": "标题不能为空"})
        if conclusion not in VALID_CONCLUSIONS:
            raise serializers.ValidationError({"conclusion": "结论必须为 pass/fail/risk"})
        if not summary:
            raise serializers.ValidationError({"summary": "验证内容不能为空"})
        version_name = (attrs.get("version_name") or "").strip()
        strategy_name = (attrs.get("strategy_name") or "").strip()
        if bool(version_name) != bool(strategy_name):
            raise serializers.ValidationError({"strategy_name": "版本与策略须同时选择或均不选择"})
        if strategy_name:
            strategy_exists = Strategy.objects.filter(
                name=strategy_name, branch__version__name=version_name
            ).exists()
            if not strategy_exists:
                raise serializers.ValidationError({"strategy_name": "策略不属于所选版本"})
        return attrs


class ReportRevisionLogSerializer(serializers.ModelSerializer):
    """报告修改记录序列化：动作中文标签 + 操作时间格式化。"""

    action_label = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S", read_only=True)

    class Meta:
        model = ReportRevisionLog
        fields = [
            "id",
            "report_id",
            "report_title",
            "action",
            "action_label",
            "field_name",
            "before_value",
            "after_value",
            "operator_username",
            "created_at",
        ]
        read_only_fields = fields

    def get_action_label(self, obj: ReportRevisionLog) -> str:
        return dict(ReportRevisionLog.ACTION_CHOICES).get(obj.action, obj.action)