"""视图辅助：统一 JSON 响应 + 安全日志 + 共享解析/认证/错误组装。"""
import logging

from django.contrib.auth import get_user_model
from django.http import JsonResponse

from ..api import err
from ..errors import CODE_FORBIDDEN, CODE_NOT_FOUND, CODE_STATUS, CODE_UNAUTHENTICATED, CODE_UNPROCESSABLE
from ..models import SecurityLog
from ..parsing import parse_int  # noqa: F401  re-export：视图层沿用 from . import parse_int

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


def validation_error_resp(exc):
    """StrategyValidationError → 统一错误响应；HTTP 状态由 CODE_STATUS 真源映射。

    exc 为鸭子类型入参（code/message/extra），PM 与 admin 两入口共用一份实现
    （原 views/strategies.py 与 views/admin.py 各持一份完全相同的副本）。
    """
    return json_resp(err(exc.code, exc.message, exc.extra),
                     status=CODE_STATUS.get(exc.code, 422))


def fetch_by_id(model, raw_id, *, not_found="资源不存在", extra_queryset=None):
    """按主键取对象，统一处理两类失败，避免调用点各写一套。

    返回 (obj, err_response)：
    - raw_id 为空或非数字 → (None, 42201「参数非法」)，杜绝 ValueError 500；
    - ID 合法但记录不存在 → (None, 40401 not_found)。

    extra_queryset 可传入已带 select_related 的 QuerySet 以避免 N+1。
    """
    pk = parse_int(raw_id)
    if pk is None:
        return None, fail_resp(CODE_UNPROCESSABLE, "id 参数非法，应为整数")
    qs = extra_queryset if extra_queryset is not None else model.objects.all()
    obj = qs.filter(pk=pk).first()
    if obj is None:
        return None, fail_resp(CODE_NOT_FOUND, not_found)
    return obj, None


def security_log(action, username="", detail="", request=None):
    """写安全日志；失败仅告警不阻断业务（审计旁路，不能影响主流程）。

    request 传入时自动附加客户端 IP 与 User-Agent 到 detail —— 登录类事件
    （成功/失败/锁定）依赖它做溯源，业务操作日志的 detail 已含业务上下文可不传。
    """
    meta = ""
    if request is not None:
        ip = request.META.get("REMOTE_ADDR", "") or request.META.get("HTTP_X_FORWARDED_FOR", "")
        ua = (request.META.get("HTTP_USER_AGENT", "") or "")[:200]
        meta = f"ip={ip} ua={ua}"
        detail = f"{detail}; {meta}" if detail else meta
    try:
        SecurityLog.objects.create(username=username or "", action=action, detail=detail or "")
    except Exception:
        # exception 保留完整堆栈：审计旁路若静默失败，没有堆栈无法排查
        logger.exception("安全日志写入失败：action=%s username=%s", action, username)


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
        return None, fail_resp(CODE_UNAUTHENTICATED, "未认证")
    user, _ = result
    return user, None
