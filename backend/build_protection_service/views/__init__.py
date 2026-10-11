"""视图辅助：统一 JSON 响应 + 安全日志 + 共享解析/认证/错误组装。"""
import logging

from django.contrib.auth import get_user_model
from django.http import JsonResponse

from ..api import err
from ..errors import CODE_FORBIDDEN, CODE_NOT_FOUND, CODE_STATUS, CODE_UNPROCESSABLE
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
    """安全转 int；None/非数字返回 None，供 id 过滤前兜底（避免 ValueError 500）。

    Django 对 ``filter(id="abc")`` 会抛 ValueError（未捕获即 500，破坏统一响应契约），
    因此所有来自 query/body 的 ID 参数必须先经本函数转换。

    仅接受 ASCII 十进制数字：``int()`` 会接受全角数字（"０"）与 Unicode 数字，
    这些值不该进入 ID 过滤，故先用 str.isascii() 拦掉。
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text or not text.isascii() or not text.lstrip("-").isdigit():
            return None
        return int(text)
    return None


def query_int(request, name, default=None):
    """从 query string 取整数参数；非数字返回 default（调用方决定是否报错）。"""
    return parse_int(request.GET.get(name, default))


def body_int(body, name, default=None):
    """从已解析的 JSON body 取整数参数；非数字返回 default。"""
    return parse_int(body.get(name, default))


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
