"""视图辅助：统一 JSON 响应 + 安全日志 + 共享解析/认证/错误组装。"""
import logging

from django.contrib.auth import get_user_model
from django.http import JsonResponse

from ..api import err
from ..errors import CODE_FORBIDDEN, CODE_STATUS
from ..models import SecurityLog

logger = logging.getLogger(__name__)

User = get_user_model()


def json_resp(payload, status=200):
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})


def fail_resp(code, message, data=None):
    """按错误码组装统一错误响应；HTTP 状态由 CODE_STATUS 映射决定。"""
    return json_resp(err(code, message, data), status=CODE_STATUS.get(code, 400))


def first_error(errors) -> str:
    """取 serializer/DRF 错误第一条消息用于统一提示。"""
    for value in errors.values():
        if isinstance(value, list) and value:
            return str(value[0])
        if isinstance(value, str) and value:
            return value
    return "参数校验失败"


def require_admin(user, message="仅管理员可操作"):
    """admin 门槛：非 admin 返回 40301 响应，否则 None。"""
    if getattr(user, "role", "") != "admin":
        return fail_resp(CODE_FORBIDDEN, message)
    return None


def fmt_dt(dt):
    """统一时间序列化：'%Y-%m-%dT%H:%M:%S'，空值返回 None。"""
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


def parse_int(value):
    """安全转 int；None/非数字返回 None，供 id 过滤前兜底（避免 ValueError 500）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def security_log(action, username="", detail=""):
    """写安全日志；失败仅告警不阻断业务（审计旁路，不能影响主流程）。"""
    try:
        SecurityLog.objects.create(username=username or "", action=action, detail=detail or "")
    except Exception:
        logger.warning("安全日志写入失败：action=%s username=%s", action, username)


def parse_body(request):
    """普通 Django 视图无 request.data，手动解析 JSON body；非法 JSON 视为空 body。"""
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
        return None, fail_resp(40100, "未认证")
    user, _ = result
    return user, None
