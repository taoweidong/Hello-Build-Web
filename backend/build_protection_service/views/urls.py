"""业务 API 路由。"""
from django.urls import path

from . import login, strategies

app_name = "build_protection_service"

urlpatterns = [
    path("auth/login", login.login_view, name="login"),
    path("auth/logout", login.logout_view, name="logout"),
    path("auth/me", login.me_view, name="me"),

    path("strategies", strategies.strategies_view, name="strategies"),
    path("strategies/preview", strategies.preview_strategy, name="strategies_preview"),
    path("strategies/<int:sid>", strategies.strategy_detail_view, name="strategy_detail"),
    path("strategies/<int:sid>/toggle", strategies.toggle_strategy, name="strategies_toggle"),
]