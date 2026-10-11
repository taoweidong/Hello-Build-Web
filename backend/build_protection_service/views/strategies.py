"""策略 views：列表/预览/创建/更新/启停/删除。

校验与写路径统一在 services.strategies（PM 与 admin 两入口共用），
本模块只负责认证、角色门槛、请求体解析与统一响应组装。
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone

from ..api import err, ok
from ..errors import (
    CODE_DUPLICATE,
    CODE_FORBIDDEN,
    CODE_NOT_FOUND,
    CODE_STATUS,
    CODE_UNPROCESSABLE,
)
from ..models import Branch, Strategy, StrategyTemplate
from ..services.config import get_config
from ..services.strategies import (
    StrategyValidationError,
    create_strategy as svc_create,
    strategy_payload,
    update_strategy as svc_update,
    validate_strategy,
)
from ..services.timeline import build_timeline
from . import authed_user, fail_resp, json_resp, parse_body, parse_int

User = get_user_model()


def _authed(request):
    """手动认证，未认证返回响应。"""
    user, resp = authed_user(request)
    if resp:
        return resp
    request.user = user
    return None


def _check_pm_bound(user, branch):
    if user.role == "admin":
        return None
    if user.role != "pm":
        return fail_resp(CODE_FORBIDDEN, "无权限操作策略")
    if branch.version.pm_user_id != user.id:
        return fail_resp(CODE_FORBIDDEN, "仅可操作本版本分支")
    return None


def _validation_error(exc: StrategyValidationError):
    """StrategyValidationError → 统一错误响应；HTTP 状态由 CODE_STATUS 真源映射。"""
    return json_resp(err(exc.code, exc.message, exc.extra), status=CODE_STATUS.get(exc.code, 422))


def list_strategies(request):
    authed = _authed(request)
    if authed:
        return authed
    qs = Strategy.objects.select_related("branch", "branch__version", "template").all()
    raw_version_id = request.GET.get("version_id")
    raw_branch_id = request.GET.get("branch_id")
    for name, raw in (("version_id", raw_version_id), ("branch_id", raw_branch_id)):
        if raw and parse_int(raw) is None:
            return fail_resp(CODE_UNPROCESSABLE, f"{name} 应为整数")
    version_id = parse_int(raw_version_id)
    branch_id = parse_int(raw_branch_id)
    if version_id:
        qs = qs.filter(branch__version_id=version_id)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    # PM 仅可见其绑定版本策略（管理员可见全部）；未绑定版本的 PM 取空集
    # （fail-closed，避免过滤条件整体跳过导致越权可见全部策略）。
    if request.user.role == "pm":
        bound_version_id = getattr(request.user, "bound_version_id", None)
        if bound_version_id is None:
            qs = qs.none()
        else:
            qs = qs.filter(branch__version_id=bound_version_id)
    return json_resp(ok([strategy_payload(s) for s in qs]))


def preview_strategy(request):
    if request.method != "POST":
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
    authed = _authed(request)
    if authed:
        return authed
    body = parse_body(request)
    branch_id = parse_int(body.get("branch_id"))
    template_id = parse_int(body.get("template_id"))
    if branch_id is None or template_id is None:
        return fail_resp(CODE_UNPROCESSABLE, "branch_id / template_id 应为整数")
    branch = Branch.objects.filter(id=branch_id).first()
    template = StrategyTemplate.objects.filter(id=template_id).first()
    if not branch or not template:
        return fail_resp(CODE_UNPROCESSABLE, "分支或模板不存在")
    build_start_time = body.get("build_start_time", "22:00")
    push_start_time = body.get("push_start_time")
    push_mode = body.get("push_mode", "normal")
    try:
        validate_strategy(branch, template, build_start_time, push_start_time,
                          push_mode=push_mode, exclude_id=parse_int(body.get("id")))
    except StrategyValidationError as exc:
        if exc.code == CODE_UNPROCESSABLE:
            # 参数本身非法（时间格式/push_mode 值域）走错误响应；
            # 冲突类（40901/40902）才是预览要回传的 conflict 载荷。
            return _validation_error(exc)
        return json_resp(ok({"conflict": {"code": exc.code, "message": exc.message, **exc.extra}}))
    # 计算时间线供前端实时预览（与校验同一基准日期：当天）
    build_minutes = get_config("build_minutes", settings.BUILD_MINUTES)
    push_minutes = get_config("push_minutes", settings.PUSH_MINUTES)
    sync_buffer_minutes = get_config("sync_buffer_minutes", settings.SYNC_BUFFER_MINUTES)
    timeline = build_timeline(
        timezone.localdate().strftime("%Y-%m-%d"),
        build_start_time, template.smoke_minutes, template.analysis_minutes,
        build_minutes, push_minutes, sync_buffer_minutes, push_mode, push_start_time)
    return json_resp(ok({"conflict": None, "timeline": timeline}))


def create_strategy(request):
    authed = _authed(request)
    if authed:
        return authed
    body = parse_body(request)
    branch_id = parse_int(body.get("branch_id"))
    template_id = parse_int(body.get("template_id"))
    if branch_id is None or template_id is None:
        return fail_resp(CODE_UNPROCESSABLE, "branch_id / template_id 应为整数")
    branch = Branch.objects.filter(id=branch_id).first()
    template = StrategyTemplate.objects.filter(id=template_id).first()
    if not branch or not template:
        return fail_resp(CODE_UNPROCESSABLE, "分支或模板不存在")
    perr = _check_pm_bound(request.user, branch)
    if perr:
        return perr
    try:
        s = svc_create(
            branch, template, request.user, name=body.get("name"),
            build_start_time=body.get("build_start_time", "22:00"),
            push_start_time=body.get("push_start_time"),
            push_mode=body.get("push_mode", "normal"),
            enabled=body.get("enabled", True),
        )
    except StrategyValidationError as exc:
        return _validation_error(exc)
    return json_resp(ok(strategy_payload(s)))


def update_strategy(request, sid):
    authed = _authed(request)
    if authed:
        return authed
    s = Strategy.objects.select_related("branch", "branch__version", "template").filter(id=sid).first()
    if not s:
        return fail_resp(CODE_NOT_FOUND, "策略不存在")
    perr = _check_pm_bound(request.user, s.branch)
    if perr:
        return perr
    try:
        svc_update(s, parse_body(request), request.user)
    except StrategyValidationError as exc:
        return _validation_error(exc)
    return json_resp(ok(strategy_payload(s)))


def toggle_strategy(request, sid):
    # 方法守卫：翻转是写操作，GET/HEAD 等读方法不得产生副作用
    # （前端用 PATCH，既有集成方用 POST，两者均放行；admin 侧同款端点强制 PATCH）。
    if request.method not in ("POST", "PATCH"):
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
    authed = _authed(request)
    if authed:
        return authed
    s = Strategy.objects.select_related("branch", "branch__version", "template").filter(id=sid).first()
    if not s:
        return fail_resp(CODE_NOT_FOUND, "策略不存在")
    perr = _check_pm_bound(request.user, s.branch)
    if perr:
        return perr
    s.enabled = not s.enabled
    try:
        # 启用时可能撞 uniq_active_strategy_branch_time 约束（两条同刻策略
        # 先后停用再先后启用的场景），服务层校验不含 toggle 路径，此处兜底。
        # SQLite 的 IntegrityError 不含约束名，按字段组合匹配（见 services 层同款注释）。
        s.save()
    except IntegrityError as exc:
        msg = str(exc)
        if "strategy.branch_id" in msg and "build_start_time" in msg:
            return fail_resp(
                CODE_DUPLICATE, "该分支已存在同一构建时刻的启用策略，无法启用"
            )
        raise
    return json_resp(ok(strategy_payload(s)))


def delete_strategy(request, sid):
    authed = _authed(request)
    if authed:
        return authed
    s = Strategy.objects.filter(id=sid).first()
    if not s:
        return fail_resp(CODE_NOT_FOUND, "策略不存在")
    perr = _check_pm_bound(request.user, s.branch)
    if perr:
        return perr
    s.delete()
    return json_resp(ok())


def strategies_view(request):
    if request.method == "GET":
        return list_strategies(request)
    if request.method == "POST":
        return create_strategy(request)
    return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")


def strategy_detail_view(request, sid):
    if request.method == "PATCH":
        return update_strategy(request, sid)
    if request.method == "DELETE":
        return delete_strategy(request, sid)
    return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
