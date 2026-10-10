"""视图辅助：统一 JSON 响应 + 安全日志 + 共享解析/认证。"""
import logging

from django.contrib.auth import get_user_model
from django.http import JsonResponse

from ..api import err
from ..models import SecurityLog

logger = logging.getLogger(__name__)

User = get_user_model()


def json_resp(payload, status=200):
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})


def security_log(action, username="", detail=""):
    """写安全日志；失败仅告警不阻断业务（审计旁路，不能影响主流程）。"""
    try:
        SecurityLog.objects.create(username=username or "", action=action, detail=detail or "")
    except Exception:
        logger.warning("安全日志写入失败：action=%s username=%s", action, username)


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