"""角色权限：基于 user.role 字段。"""
from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    message = "仅管理员可操作"

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == "admin")


class IsPmOrAdmin(BasePermission):
    message = "仅版本负责人或管理员可操作"

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.role in ("pm", "admin")
        )