"""登录/登出/当前用户。"""
import json

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

from ..api import ok
from ..auth import JWTAuthentication
from . import json_resp, security_log

User = get_user_model()


def _user_payload(user):
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "role": user.role,
        "bound_version_id": getattr(user, "bound_version_id", None),
        "bound_version_name": getattr(getattr(user, "bound_version", None), "name", None),
    }


def _parse_body(request):
    """普通 Django 视图无 request.data，手动解析 JSON body。"""
    body = {}
    try:
        body = json.loads(request.body or "{}")
    except (ValueError, TypeError):
        body = {}
    return body


def login_view(request):
    body = _parse_body(request)
    username = body.get("username", "")
    password = body.get("password", "")
    user = User.objects.filter(username=username).first()
    if user is None or not user.check_password(password):
        security_log("login_failed", username=username)
        return json_resp({"code": 40101, "message": "用户名或密码错误", "data": None}, status=401)
    if not user.is_active:
        return json_resp({"code": 40301, "message": "账号已停用", "data": None}, status=403)
    refresh = RefreshToken.for_user(user)
    security_log("login_success", username=username)
    return json_resp(ok({"token": str(refresh.access_token), "user": _user_payload(user)}))


def logout_view(request):
    security_log("logout", username=getattr(getattr(request, "user", None), "username", "") or "")
    return json_resp(ok())


def me_view(request):
    # 普通 Django 视图不会自动执行 DRF JWT 认证，手动校验 Authorization header。
    result = JWTAuthentication().authenticate(request)
    if result is None:
        return json_resp({"code": 40100, "message": "未登录", "data": None}, status=401)
    user, _ = result
    return json_resp(ok(_user_payload(user)))