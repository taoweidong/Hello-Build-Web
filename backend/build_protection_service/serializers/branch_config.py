"""启动配置序列化器：分支工程关联的启动参数写入（env_vars 值统一转字符串）。"""
from rest_framework import serializers

from ..models import StartupConfig
from ..services.branch_config import dump_raw_config


class StartupConfigSerializer(serializers.ModelSerializer):
    """启动参数写入：字段可选（partial 更新），原始配置 JSON 只读回显。"""

    command = serializers.CharField(allow_blank=True, required=False, max_length=255)
    args = serializers.ListField(
        child=serializers.CharField(allow_blank=True), required=False
    )
    env_vars = serializers.DictField(
        child=serializers.JSONField(), required=False
    )
    working_directory = serializers.CharField(allow_blank=True, required=False, max_length=255)
    timeout_seconds = serializers.IntegerField(min_value=1, max_value=3600, required=False)
    auto_restart = serializers.BooleanField(required=False)
    raw_json = serializers.CharField(read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S", read_only=True)

    class Meta:
        model = StartupConfig
        fields = [
            "command",
            "args",
            "env_vars",
            "working_directory",
            "timeout_seconds",
            "auto_restart",
            "raw_json",
            "updated_at",
        ]

    def validate_env_vars(self, value: dict) -> dict:
        """环境变量值统一转字符串（兼容数字/布尔）。"""
        return {str(k): str(v) for k, v in (value or {}).items()}

    def update(self, instance: StartupConfig, validated_data: dict) -> StartupConfig:
        instance.command = validated_data.get("command", instance.command)
        instance.args = list(validated_data.get("args", instance.args or []))
        instance.env_vars = dict(validated_data.get("env_vars", instance.env_vars or {}))
        instance.working_directory = validated_data.get(
            "working_directory", instance.working_directory
        )
        instance.timeout_seconds = validated_data.get(
            "timeout_seconds", instance.timeout_seconds
        )
        instance.auto_restart = validated_data.get(
            "auto_restart", instance.auto_restart
        )
        instance.raw_json = dump_raw_config(instance)
        instance.save()
        return instance