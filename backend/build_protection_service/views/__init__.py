"""视图辅助：统一 JSON 响应 + 安全日志 + 共享解析/认证。"""
from django.contrib.auth import get_user_model
from django.http import JsonResponse

from ..api import err
from ..models import SecurityLog

User = get_user_model()


def json_resp(payload, status=200):
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})


def security_log(action, username=""):
    try:
        SecurityLog.objects.create(username=username, action=action)
    except Exception:
        pass


def parse_body(request):
    """普通 Django 视图无 request.data，手动解析 JSON body。"""
    import json

    body = {}
    try:
        body = json.loads(request.body or "{}")
    except (ValueError, TypeError):
        body = {}
    return body


def authed_user(request):
    """手动 JWT 认证，返回 (user, None) 或 (None, JsonResponse)。"""
    from ..auth import JWTAuthentication

    result = JWTAuthentication().authenticate(request)
    if result is None:
        return None, json_resp(err(40100, "未认证"), status=401)
    user, _ = result
    return user, None