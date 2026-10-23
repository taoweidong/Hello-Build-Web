from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.core.exceptions import ValidationError

from .models import (
    AdminOpLog, BorrowFlow, Branch, ExecutionRound, SecurityLog, SlotBooking,
    SlotTemplate, Strategy, StrategyChangeLog, StrategyTemplate, User, Version,
)
from .services.strategies import (
    StrategyValidationError, delete_strategy, validate_strategy,
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

    def delete_model(self, request, obj):
        """删除路由到共享服务层（R6-B1）：pending 借用流拦截在 admin 面板同样生效。

        默认 ModelAdmin 走 queryset 级联删除，BorrowFlow.strategy 为 CASCADE，
        会静默抹掉进行中的待审批电子流——R4-B1 的拦截此前只覆盖了 API 入口。
        拦截时（40903）转 ValidationError 让 admin 报错页可读。
        """
        try:
            delete_strategy(obj)
        except StrategyValidationError as exc:
            raise ValidationError(exc.message)

    def delete_queryset(self, request, queryset):
        """批量删除同款逐条走服务层，保持拦截语义一致。"""
        for obj in queryset:
            self.delete_model(request, obj)


@admin.register(SlotTemplate)
class SlotTemplateAdmin(admin.ModelAdmin):
    """时段模板唯一管理入口（R6-B1）：CRUD 端点随时段配置页下线后，写入面
    按 views/slot_booking.py 约定收敛到本面板与 seed 命令，此前从未注册导致
    生产无法新增/修改/停用模板。"""

    list_display = ("name", "weekdays", "effective_from", "effective_to", "sort_order", "enabled")
    list_editable = ("sort_order", "enabled")


class _ReadOnlyAdmin(admin.ModelAdmin):
    """只读 ModelAdmin（R6-B12）：抢占记录 / 借用电子流 / 审计三表禁增删改。

    审计记录必须经业务链路落库（留痕语义完整），后台手工增删改会破坏审计
    不可篡改性；抢占/借用记录直改会绕过条件 UPDATE 与状态机校验。
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Branch)
admin.site.register(StrategyTemplate)
admin.site.register(ExecutionRound)
admin.site.register(StrategyChangeLog, _ReadOnlyAdmin)
admin.site.register(AdminOpLog, _ReadOnlyAdmin)
admin.site.register(SecurityLog, _ReadOnlyAdmin)
admin.site.register(SlotBooking, _ReadOnlyAdmin)
admin.site.register(BorrowFlow, _ReadOnlyAdmin)