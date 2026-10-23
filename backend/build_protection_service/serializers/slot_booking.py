"""时段抢占序列化器：抢占入参校验（跨天拦截 / 版本分支归属校验）。

2026-10-20 页面精简：SlotTemplateSerializer 随时段模板 CRUD 端点（时段配置页）下线删除。
"""
from rest_framework import serializers

from ..models import Branch, Version


class StrictCharField(serializers.CharField):
    """非 str 拒绝（R6-B4）：CharField 默认把 int/float 静默强转为 str
    （仅拒绝 bool/dict/list），导致同一载荷在 create（经序列化器）与改期
    （服务层 R5-B9 非 str 拒绝）两条写路径行为相反。本字段对齐服务层口径，
    字段级类型校验拒绝优于静默转换。"""

    default_error_messages = {
        "invalid": "该字段应为字符串",
    }

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class SlotBookingCreateSerializer(serializers.Serializer):
    """抢占入参：全字段必填，用途 2~200 字，分支必须归属所选版本。

    注意：purpose 长度与版本/分支归属校验在 services.slot_booking.create_booking
    中有一份同口径实现（服务层是唯一裁决点，直调服务的路径也受保护）；
    修改任一处校验语义时必须同步另一处（2026-10-12 质量评估 B-P2-21 记录在案）。
    """

    date = serializers.DateField()
    template_id = serializers.IntegerField()
    purpose = StrictCharField(max_length=200, error_messages={"invalid": "purpose 应为字符串"})
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

    release_reason = StrictCharField(
        max_length=200, required=False, allow_blank=True, default="",
        error_messages={"invalid": "释放原因应为字符串"},
    )
