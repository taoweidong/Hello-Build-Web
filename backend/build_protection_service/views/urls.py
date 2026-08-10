"""业务 API 路由。plan/strategies/weekly 在后续任务追加。"""
from django.urls import path

from . import login

app_name = "build_protection_service"

urlpatterns = [
    path("auth/login", login.login_view, name="login"),
    path("auth/logout", login.logout_view, name="logout"),
    path("auth/me", login.me_view, name="me"),
]