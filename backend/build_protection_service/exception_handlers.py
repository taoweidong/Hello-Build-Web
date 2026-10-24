"""DRF 异常 → 统一响应契约 {code,message,data}。

ViewSet 路径的 request.data 解析失败（非法 JSON → ParseError）、DRF 内置
认证/权限/限流异常等，默认 handler 返回 {"detail": ...} 不带 code 字段，
前端 api/http.ts 的信封解析拿不到 code 会破坏契约。本模块经
REST_FRAMEWORK["EXCEPTION_HANDLER"] 挂载，把 DRF 异常归一化为业务错误码；
非 DRF 异常返回 None，保持 Django 默认 500 路径（不吞堆栈）。
"""
from django.http import Http404, JsonResponse
from rest_framework.exceptions import (
    APIException,
    MethodNotAllowed,
    NotAcceptable,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied,
    Throttled,
    UnsupportedMediaType,
    ValidationError,
)
from rest_framework.views import exception_handler as drf_exception_handler

from .api import err
from .errors import (
    CODE_FORBIDDEN,
    CODE_INTERNAL,
    CODE_NOT_FOUND,
    CODE_RATE_LIMITED,
    CODE_STATUS,
    CODE_UNAUTHENTICATED,
    CODE_UNPROCESSABLE,
)


def _message_of(data) -> str:
    """从 DRF 异常 payload 提取可读消息：detail 字符串直取，字段字典取第一条。"""
    if isinstance(data, str) and data:
        return data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list) and value:
                return str(value[0])
            if isinstance(value, str) and value:
                return value
    if isinstance(data, list) and data:
        return str(data[0])
    return "请求处理失败"


def contract_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        # 非 DRF 异常（含未捕获 bug）：交回 Django 默认 500 处理，保留堆栈可排查
        return None
    if isinstance(exc, (NotAuthenticated,)):
        code = CODE_UNAUTHENTICATED
    elif isinstance(exc, (PermissionDenied,)):
        code = CODE_FORBIDDEN
    elif isinstance(exc, (NotFound, Http404)):
        code = CODE_NOT_FOUND
    elif isinstance(exc, (ParseError, ValidationError, UnsupportedMediaType, NotAcceptable)):
        # 415/406 一并归入参数非法（R7-B8）：此前落入 else 兜底被误标 50000/500，
        # 客户端错误（如 text/plain Content-Type）混入服务端错误监控口径
        code = CODE_UNPROCESSABLE
    elif isinstance(exc, MethodNotAllowed):
        # 契约无 405 语义，归入「不支持的请求方法」的 42201（与函数视图口径一致）
        code, message = CODE_UNPROCESSABLE, "不支持的请求方法"
        return JsonResponse(err(code, message), status=CODE_STATUS[code],
                            json_dumps_params={"ensure_ascii": False})
    elif isinstance(exc, Throttled):
        code = CODE_RATE_LIMITED
    else:
        # 走到这里 response 必非 None，即 exc 必为 APIException（Http404 已被
        # DRF handler 归一为 NotFound 并在上方分支命中）。未枚举的 4xx APIException
        # 归参数非法、5xx 归内部错误（R7-B8：此前一律 CODE_INTERNAL）。
        code = CODE_UNPROCESSABLE if response.status_code < 500 else CODE_INTERNAL
    return JsonResponse(
        err(code, _message_of(response.data)),
        status=CODE_STATUS.get(code, response.status_code),
        json_dumps_params={"ensure_ascii": False},
    )
