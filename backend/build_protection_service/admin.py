from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.core.exceptions import ValidationError

from .models import (
    AdminOpLog, Branch, ExecutionLog, ExecutionRound, SecurityLog,
    Strategy, StrategyChangeLog, StrategyTemplate, User, Version,
)
from .services.strategies import StrategyValidationError, validate_strategy

_BIZ_FIELDSET = ("业务信息", {"fields": ("role", "display_name")})


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """复用 Django 内置 UserAdmin：密码经哈希组件读写，避免裸 ModelAdmin 明文存密码。"""

    list_display = ("username", "role", "display_name", "is_active")
    fieldsets = DjangoUserAdmin.fieldsets + (_BIZ_FIELDSET,)
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (_BIZ_FIELDSET,)


@admin.register(Version)
class VersionAdmin(admin.ModelAdmin):
    list_display = ("name", "pm_user", "status")


@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "template", "build_start_time", "push_start_time", "enabled")

    def save_model(self, request, obj, form, change):
        """后台写路径最小加固（R4-B11/B4-11）：保存前重跑服务层校验。

        django-admin 面板可绕过 API 服务层直改 build_start_time/push_mode/enabled
        等字段，无校验会让互斥/阶段冲突数据静默入库。此处复用
        services.strategies.validate_strategy（参数 42201 / 互斥 40902 / 阶段
        冲突 40901），失败转 Django 表单 ValidationError 阻止保存。
        停用策略不占时段（唯一约束与冲突检测均仅覆盖 enabled=True），跳过
        校验以便把冲突策略先停用归档——与服务层 toggle 语义一致。
        部署面收敛（生产关闭/改名 admin、强口令、IP 白名单）为部署清单项，
        记录在第四轮评估报告，不在本轮代码改动。
        """
        if obj.enabled:
            try:
                validate_strategy(
                    obj.branch, obj.template,
                    obj.build_start_time, obj.push_start_time,
                    push_mode=obj.push_mode, exclude_id=obj.pk,
                )
            except StrategyValidationError as exc:
                raise ValidationError(exc.message)
        super().save_model(request, obj, form, change)


admin.site.register(Branch)
admin.site.register(StrategyTemplate)
admin.site.register(ExecutionRound)
admin.site.register(ExecutionLog)
admin.site.register(StrategyChangeLog)
admin.site.register(AdminOpLog)
admin.site.register(SecurityLog)