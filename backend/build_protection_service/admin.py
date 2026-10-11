from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    AdminOpLog, Branch, ExecutionLog, ExecutionRound, SecurityLog,
    Strategy, StrategyChangeLog, StrategyTemplate, User, Version,
)

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


admin.site.register(Branch)
admin.site.register(StrategyTemplate)
admin.site.register(ExecutionRound)
admin.site.register(ExecutionLog)
admin.site.register(StrategyChangeLog)
admin.site.register(AdminOpLog)
admin.site.register(SecurityLog)