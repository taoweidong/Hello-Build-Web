"""业务 API 路由。"""
from django.urls import path

from . import executions, login, logs, plan, reports, strategies, weekly
from . import admin
from . import branch_config

app_name = "build_protection_service"

urlpatterns = [
    path("auth/login", login.login_view, name="login"),
    path("auth/logout", login.logout_view, name="logout"),
    path("auth/me", login.me_view, name="me"),

    path("strategies", strategies.strategies_view, name="strategies"),
    path("strategies/preview", strategies.preview_strategy, name="strategies_preview"),
    path("strategies/<int:sid>", strategies.strategy_detail_view, name="strategy_detail"),
    path("strategies/<int:sid>/toggle", strategies.toggle_strategy, name="strategies_toggle"),

    path("plan", plan.plan_view, name="plan"),

    path("weekly", weekly.weekly_view, name="weekly"),

    path("executions", executions.executions_view, name="executions"),
    path("executions/rounds/<int:rid>", executions.round_detail, name="round_detail"),
    path("executions/rounds/<int:rid>/conclusion", executions.conclusion_view, name="round_conclusion"),

    path("logs/execution", logs.execution_logs, name="execution_logs"),
    path("logs/changes", logs.change_logs, name="change_logs"),

    path("admin/versions", admin.extra_view, name="admin_versions"),
    path("admin/versions/<int:vid>", admin.update_version, name="admin_version_update"),
    path("admin/versions/<int:vid>/branches", admin.add_branch, name="admin_branch_add"),
    path("admin/users", admin.users_view, name="admin_users"),
    path("admin/users/<int:uid>", admin.update_user, name="admin_user_update"),
    path("admin/templates", admin.templates_view, name="admin_templates"),
    path("admin/templates/<int:tid>", admin.template_detail_view, name="admin_template_detail"),
    path("admin/strategies", admin.admin_strategies_view, name="admin_strategies"),
    path("admin/strategies/<int:sid>", admin.admin_strategy_detail_view, name="admin_strategy_detail"),
    path("admin/strategies/<int:sid>/toggle", admin.admin_strategy_toggle_view, name="admin_strategy_toggle"),
    path("admin/config", admin.config_view, name="admin_config"),
    path("admin/logs/<str:kind>", admin.logs_view, name="admin_logs"),

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
    path("users/all", branch_config.users_all, name="users_all"),
    path("projects", branch_config.projects_view, name="projects"),
]