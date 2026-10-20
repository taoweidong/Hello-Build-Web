"""业务 API 路由（2026-10-20 页面精简：仅保留调度全景 + 策略配置两页消费的端点）。"""
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from . import admin, borrow_flow, login, panorama, plan, slot_booking, strategies, weekly

app_name = "build_protection_service"

# 业务 API 一律走 JWT Authorization 头认证、无会话面，统一豁免 CSRF；
# 全局 CsrfViewMiddleware 仅为保护 django-admin 的会话认证而存在（见 settings）。
# DRF ViewSet 的 as_view() 自带 csrf_exempt，无需包装。
_api = csrf_exempt

urlpatterns = [
    path("auth/login", _api(login.login_view), name="login"),
    path("auth/logout", _api(login.logout_view), name="logout"),
    path("auth/me", _api(login.me_view), name="me"),

    path("strategies", _api(strategies.strategies_view), name="strategies"),
    path("strategies/preview", _api(strategies.preview_strategy), name="strategies_preview"),
    path("strategies/<int:sid>", _api(strategies.strategy_detail_view), name="strategy_detail"),
    path("strategies/<int:sid>/toggle", _api(strategies.toggle_strategy), name="strategies_toggle"),

    path("plan", _api(plan.plan_view), name="plan"),

    # 调度全景聚合（P2-R3）：一次返回待我审批 / 我的有效抢占 / 我发起的待审批借用
    path("panorama/todos", _api(panorama.todos_view), name="panorama_todos"),

    path("weekly", _api(weekly.weekly_view), name="weekly"),

    # 策略模板只读（系统管理页下线后仅存列表，供策略配置页下拉选项）
    path("admin/templates", _api(admin.templates_view), name="admin_templates"),

    # 时段抢占：月历聚合 / 抢占 / 释放 / 改期 / 我的抢占（模板 CRUD 随时段配置页下线）
    path("slot-calendar", _api(slot_booking.slot_calendar), name="slot_calendar"),
    path("slot-bookings", slot_booking.SlotBookingViewSet.as_view({"post": "create"}), name="slot_bookings"),
    path("slot-bookings/mine", slot_booking.SlotBookingViewSet.as_view({"get": "mine"}), name="slot_bookings_mine"),
    path("slot-bookings/<int:pk>", slot_booking.SlotBookingViewSet.as_view({"patch": "partial_update"}), name="slot_booking_reschedule"),
    path("slot-bookings/<int:pk>/release", slot_booking.SlotBookingViewSet.as_view({"post": "release"}), name="slot_booking_release"),

    # 借用电子流：发起/列表/审批（通过=在目标分支实际创建借用策略）
    path("borrow-flows", _api(borrow_flow.borrow_flow_list_view), name="borrow_flows"),
    path("borrow-flows/<int:fid>/approve", _api(borrow_flow.borrow_flow_approve_view), name="borrow_flow_approve"),
    path("borrow-flows/<int:fid>/reject", _api(borrow_flow.borrow_flow_reject_view), name="borrow_flow_reject"),
    path("borrow-flows/<int:fid>/cancel", _api(borrow_flow.borrow_flow_cancel_view), name="borrow_flow_cancel"),
]
