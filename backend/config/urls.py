"""根路由。全部业务接口挂载在 /api 下。"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/", include("build_protection_service.views.urls")),
]