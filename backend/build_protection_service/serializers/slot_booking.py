"""时段抢占序列化器：模板与抢占入参校验（跨天拦截 / 版本分支归属校验）。"""
from rest_framework import serializers

from ..models import Branch, SlotTemplate, Version


class SlotTemplateSerializer(serializers.ModelSerializer):
    """时间段模板写入：强制同日（start < end），不支持跨天时段。"""

    class Meta:
        model = SlotTemplate
        fields = [
            "id", "name", "start_time", "end_time", "weekdays",
            "effective_from", "effective_to", "color", "sort_order", "enabled",
        ]
        read_only_fields = ["id"]

    def validate_name(self, value: str) -> str:
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("时段名称必填")
        qs = SlotTemplate.objects.filter(name=name)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("时段名称已存在")
        return name

    def validate_weekdays(self, value) -> str:
        """生效星期校验：逗号分隔的 isoweekday 1-7（1=周一…7=周日）。

        口径唯一真源：与 services.slot_booking.template_applies_on 的 isoweekday()
        匹配逻辑、模型 help_text、seed 数据及前端 TemplateDialog 选项保持一致；
        拦截 "0,8,abc" 之类永不匹配或错位的脏数据。
        """
        raw = (value or "").strip()
        if not raw:
            return raw
        parts = [x.strip() for x in raw.split(",")]
        for part in parts:
            if not part.isdigit() or not 1 <= int(part) <= 7:
                raise serializers.ValidationError("生效星期应为 1-7 的逗号分隔数字（1=周一…7=周日）")
        return ",".join(str(int(x)) for x in parts)

    def validate(self, attrs: dict) -> dict:
        start = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start is not None and end is not None and start >= end:
            raise serializers.ValidationError(
                "不支持跨天时段，结束时间需晚于开始时间"
            )
        return attrs


class SlotBookingCreateSerializer(serializers.Serializer):
    """抢占入参：全字段必填，用途 2~200 字，分支必须归属所选版本。

    注意：purpose 长度与版本/分支归属校验在 services.slot_booking.create_booking
    中有一份同口径实现（服务层是唯一裁决点，直调服务的路径也受保护）；
    修改任一处校验语义时必须同步另一处（2026-10-12 质量评估 B-P2-21 记录在案）。
    """

    date = serializers.DateField()
    template_id = serializers.IntegerField()
    purpose = serializers.CharField(max_length=200)
    version_id = serializers.IntegerField()
    branch_id = serializers.IntegerField()

    def validate_purpose(self, value: str) -> str:
        purpose = (value or "").strip()
        if not 2 <= len(purpose) <= 200:
            raise serializers.ValidationError("用途说明需 2~200 字")
        return purpose

    def validate(self, attrs: dict) -> dict:
        version = Version.objects.filter(id=attrs.get("version_id")).first()
        branch = Branch.objects.filter(id=attrs.get("branch_id")).first()
        if version is None or branch is None:
            raise serializers.ValidationError("版本或分支不存在")
        if branch.version_id != version.id:
            raise serializers.ValidationError("分支不属于所选版本")
        return attrs


class ReleaseBookingSerializer(serializers.Serializer):
    """释放入参：admin 释放他人时 reason 必填（服务层按操作人判定）。"""

    release_reason = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
