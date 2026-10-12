"""视图辅助：统一 JSON 响应 + 安全日志 + 共享解析/认证/错误组装。"""
import logging

from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.utils import timezone

from ..api import err
from ..errors import CODE_FORBIDDEN, CODE_NOT_FOUND, CODE_STATUS, CODE_UNAUTHENTICATED, CODE_UNPROCESSABLE
from ..models import SecurityLog
from ..parsing import parse_int  # noqa: F401  re-export：视图层沿用 from . import parse_int

logger = logging.getLogger(__name__)

User = get_user_model()

# 对外时间戳统一格式（Asia/Shanghai 墙钟、不带 offset，见 fmt_dt 与 R3-B3 口径）
_FMT_DT = "%Y-%m-%dT%H:%M:%S"


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
    """统一时间序列化：Asia/Shanghai 墙钟 '%Y-%m-%dT%H:%M:%S'（不带 offset），空值返回 None。

    必须先 timezone.localtime 再 strftime（R3-B3，2026-10-13 评估 B-P1-3）：
    USE_TZ=True 下 ORM 读出的是 aware UTC datetime，直接 strftime 输出 UTC 墙钟
    （比上海早 8 小时）且无时区标记，前端按本地时间解析必然错位。本函数与
    DRF DateTimeField（经 enforce_timezone 输出上海墙钟）口径一致。
    """
    if not dt:
        return None
    if timezone.is_naive(dt):
        # USE_TZ=True 下 DB 读出恒为 aware；naive 值防御性按墙钟直出，避免
        # localtime() 对 naive 抛 ValueError 冒成 500。
        return dt.strftime(_FMT_DT)
    return timezone.localtime(dt).strftime(_FMT_DT)


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
        # 拼接后统一截断到字段上限（R3-B12）：业务 detail + ip + ua(200) 可超
        # max_length=255，SQLite 放行但迁 Postgres 即报错（2026-10-13 评估 B-P3-3）。
        SecurityLog.objects.create(
            username=username or "", action=action, detail=(detail or "")[:255]
        )
    except Exception:
        # exception 保留完整堆栈：审计旁路若静默失败，没有堆栈无法排查
        logger.exception("安全日志写入失败：action=%s username=%s", action, username)


def parse_body(request):
    """普通 Django 视图无 request.data，手动解析 JSON body。

    非法 JSON 与「合法 JSON 但非对象」（如 [1,2] / "str" / null / 42）统一归一为
    {}（R3-B2，2026-10-13 评估 B-P1-2）：调用方 body.get(...) 按既有"缺参/必填"
    分支返回 42201，杜绝非 dict 载荷上 .get 冒 AttributeError 变 500。
    """
    import json

    try:
        body = json.loads(request.body or "{}")
    except (ValueError, TypeError):
        return {}
    return body if isinstance(body, dict) else {}


def body_str(body, key, *, default="", max_len=None, strip=True):
    """从 body 安全提取字符串字段（R3-B2 共享助手）：非 str 一律回退 default。

    - 口径：非字符串值取 "" 走调用点既有「必填/非法」校验分支（42201），
      不引入新错误码，杜绝 (123 or "").strip() / {}.encode() 之类 500；
    - strip=False 保留原值（密码/base64 截图等首尾空白有语义的场景）；
    - max_len 按调用点既有语义超长截断（不拒绝）。
    """
    value = body.get(key) if isinstance(body, dict) else None
    if not isinstance(value, str):
        return default
    if strip:
        value = value.strip()
    if max_len is not None:
        value = value[:max_len]
    return value


# 分页页大小常量（集中定义，R3-B11）
PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 100


def paginate_qs(qs, request, serializer) -> dict:
    """简单页码分页共享助手（R3-B11 收敛：原 slot_booking._paginate 与 reports
    内联分页两份实现合一，行为保持不变）。

    page 从 1 起（非法/缺省回退 1）；page_size 默认 20、最大 100（非法/缺省/0
    回退默认值）；serializer 为逐行序列化可调用对象。返回 {items,total,page,page_size}。
    """
    page = max(1, parse_int(request.query_params.get("page")) or 1)
    page_size = min(PAGE_SIZE_MAX,
                    max(1, parse_int(request.query_params.get("page_size")) or PAGE_SIZE_DEFAULT))
    total = qs.count()
    rows = qs[(page - 1) * page_size: page * page_size]
    return {
        "items": [serializer(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def authed_user(request):
    """手动 JWT 认证，返回 (user, None) 或 (None, JsonResponse)。"""
    from ..auth import JWTAuthentication

    result = JWTAuthentication().authenticate(request)
    if result is None:
        return None, fail_resp(CODE_UNAUTHENTICATED, "未认证")
    user, _ = result
    return user, None
