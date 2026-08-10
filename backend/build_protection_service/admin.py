from django.contrib import admin

from .models import (
    AdminOpLog, Branch, ExecutionLog, ExecutionRound, SecurityLog,
    Strategy, StrategyChangeLog, StrategyTemplate, User, Version,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "role", "display_name", "is_active")


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