"""业务 API 路由。"""
from django.urls import path

from . import executions, login, logs, plan, reports, strategies, weekly
from . import admin

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

    path("reports", reports.reports_view, name="reports"),
    path("reports/<int:rid>", reports.report_detail_view, name="report_detail"),
    path("reports/<int:rid>/publish", reports.publish_view, name="report_publish"),
    path("reports/<int:rid>/publishes", reports.publishes_view, name="report_publishes"),
]