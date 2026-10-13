"""业务 API 路由。"""
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from . import executions, login, logs, plan, reports, strategies, weekly
from . import admin
from . import borrow_flow, branch_config, panorama, slot_booking

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

    path("executions", _api(executions.executions_view), name="executions"),
    path("executions/rounds/<int:rid>", _api(executions.round_detail), name="round_detail"),
    path("executions/rounds/<int:rid>/conclusion", _api(executions.conclusion_view), name="round_conclusion"),

    path("logs/execution", _api(logs.execution_logs), name="execution_logs"),
    path("logs/changes", _api(logs.change_logs), name="change_logs"),

    path("admin/versions", _api(admin.extra_view), name="admin_versions"),
    path("admin/versions/<int:vid>", _api(admin.update_version), name="admin_version_update"),
    path("admin/versions/<int:vid>/branches", _api(admin.add_branch), name="admin_branch_add"),
    path("admin/users", _api(admin.users_view), name="admin_users"),
    path("admin/users/<int:uid>", _api(admin.update_user), name="admin_user_update"),
    path("admin/templates", _api(admin.templates_view), name="admin_templates"),
    path("admin/templates/<int:tid>", _api(admin.template_detail_view), name="admin_template_detail"),
    path("admin/strategies", _api(admin.admin_strategies_view), name="admin_strategies"),
    path("admin/strategies/<int:sid>", _api(admin.admin_strategy_detail_view), name="admin_strategy_detail"),
    path("admin/strategies/<int:sid>/toggle", _api(admin.admin_strategy_toggle_view), name="admin_strategy_toggle"),
    path("admin/config", _api(admin.config_view), name="admin_config"),
    path("admin/logs/<str:kind>", _api(admin.logs_view), name="admin_logs"),

    # 验证报告：DRF ViewSet（列表/新建/详情/修改 + 发布/修改记录），废弃功能已移除
    path("reports", reports.ReportViewSet.as_view({"get": "list", "post": "create"}), name="reports"),
    path("reports/<int:pk>", reports.ReportViewSet.as_view({"get": "retrieve", "put": "update"}), name="report_detail"),
    path("reports/<int:pk>/publish", reports.ReportViewSet.as_view({"post": "publish"}), name="report_publish"),
    path("reports/<int:pk>/revisions", reports.ReportViewSet.as_view({"get": "revisions"}), name="report_revisions"),

    # 分支配置：分支/工程关联/启动参数/授权/实例（DRF ViewSet + 轻量视图）
    path("branches", branch_config.BranchViewSet.as_view({"get": "list", "post": "create"}), name="branches"),
    path("branches/<int:pk>", branch_config.BranchViewSet.as_view({"delete": "destroy"}), name="branch_detail"),
    path("branches/<int:pk>/config", branch_config.BranchViewSet.as_view({"get": "config"}), name="branch_config"),
    path("branches/<int:pk>/projects", branch_config.BranchViewSet.as_view({"post": "projects"}), name="branch_projects"),
    path("branches/<int:pk>/permissions", branch_config.BranchViewSet.as_view({"post": "permissions"}), name="branch_permissions"),
    path("branches/<int:pk>/instances", branch_config.BranchViewSet.as_view({"get": "instances"}), name="branch_instances"),
    path("branch-projects/<int:pk>", branch_config.BranchProjectViewSet.as_view({"delete": "destroy"}), name="branch_project"),
    path("branch-projects/<int:pk>/config", branch_config.BranchProjectViewSet.as_view({"put": "config"}), name="branch_project_config"),
    path("branch-projects/<int:pk>/start", branch_config.BranchProjectViewSet.as_view({"post": "start"}), name="branch_project_start"),
    path("branch-projects/<int:pk>/stop", branch_config.BranchProjectViewSet.as_view({"post": "stop"}), name="branch_project_stop"),
    path("branch-permissions/<int:pk>", branch_config.BranchPermissionViewSet.as_view({"delete": "destroy"}), name="branch_permission"),
    path("users/all", _api(branch_config.users_all), name="users_all"),
    path("projects", _api(branch_config.projects_view), name="projects"),

    # 时段抢占：模板/日历聚合/抢占/释放（DRF ViewSet + 函数视图）
    path("slot-templates", slot_booking.SlotTemplateViewSet.as_view({"get": "list", "post": "create"}), name="slot_templates"),
    path("slot-templates/<int:pk>", slot_booking.SlotTemplateViewSet.as_view({"put": "update", "delete": "destroy"}), name="slot_template_detail"),
    path("slot-calendar", _api(slot_booking.slot_calendar), name="slot_calendar"),
    path("slot-bookings", slot_booking.SlotBookingViewSet.as_view({"get": "list", "post": "create"}), name="slot_bookings"),
    path("slot-bookings/mine", slot_booking.SlotBookingViewSet.as_view({"get": "mine"}), name="slot_bookings_mine"),
    path("slot-bookings/<int:pk>", slot_booking.SlotBookingViewSet.as_view({"patch": "partial_update"}), name="slot_booking_reschedule"),
    path("slot-bookings/<int:pk>/release", slot_booking.SlotBookingViewSet.as_view({"post": "release"}), name="slot_booking_release"),

    # 借用电子流：发起/列表/审批（通过=在目标分支实际创建借用策略）
    path("borrow-flows", _api(borrow_flow.borrow_flow_list_view), name="borrow_flows"),
    path("borrow-flows/<int:fid>/approve", _api(borrow_flow.borrow_flow_approve_view), name="borrow_flow_approve"),
    path("borrow-flows/<int:fid>/reject", _api(borrow_flow.borrow_flow_reject_view), name="borrow_flow_reject"),
    path("borrow-flows/<int:fid>/cancel", _api(borrow_flow.borrow_flow_cancel_view), name="borrow_flow_cancel"),
]
