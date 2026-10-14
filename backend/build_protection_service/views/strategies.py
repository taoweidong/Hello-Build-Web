"""策略 views：列表/预览/创建/更新/启停/删除。

校验与写路径统一在 services.strategies（PM 与 admin 两入口共用），
本模块只负责认证、角色门槛、请求体解析与统一响应组装。
"""
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..api import ok
from ..errors import (
    CODE_FORBIDDEN,
    CODE_NOT_FOUND,
    CODE_UNPROCESSABLE,
)
from ..models import AdminOpLog, Branch, Strategy, StrategyChangeLog, StrategyTemplate
from ..services.config import get_config
from ..services.strategies import (
    StrategyValidationError,
    create_strategy as svc_create,
    delete_strategy as svc_delete,
    strategy_payload,
    toggle_strategy as svc_toggle,
    update_strategy as svc_update,
    validate_strategy,
)
from ..services.timeline import build_timeline
from . import authed_user, fail_resp, json_resp, parse_body, parse_int, validation_error_resp

logger = logging.getLogger(__name__)


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


def filter_strategies_qs(qs, request):
    """version_id/branch_id 查询参数校验与过滤（PM 与 admin 列表入口共用）。

    返回 (qs, err_response)：非法参数 → (None, 42201 响应)。
    """
    raw_version_id = request.GET.get("version_id")
    raw_branch_id = request.GET.get("branch_id")
    for name, raw in (("version_id", raw_version_id), ("branch_id", raw_branch_id)):
        if raw and parse_int(raw) is None:
            return None, fail_resp(CODE_UNPROCESSABLE, f"{name} 应为整数")
    version_id = parse_int(raw_version_id)
    branch_id = parse_int(raw_branch_id)
    if version_id:
        qs = qs.filter(branch__version_id=version_id)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    return qs, None


def list_strategies(request):
    authed = _authed(request)
    if authed:
        return authed
    qs = Strategy.objects.select_related("branch", "branch__version", "template").all()
    qs, err_resp = filter_strategies_qs(qs, request)
    if err_resp:
        return err_resp
    # 可见性设计决策（R3-B10，2026-10-13 第三轮评估 B-P2-6 定案，行为不变）：
    # 1. 策略计划对全员可见——/plan 与 /weekly 本就对全部登录用户公开，
    #    策略列表与其口径一致，不作为安全边界；builder/tester/integrator
    #    可见全部版本的全部策略；
    # 2. PM 的过滤是「默认视图」语义（默认只看自己绑定版本，降低误操作面），
    #    而非越权拦截；
    # 3. 未绑定版本的 PM 取空集（fail-closed）：宁可少看不可多看，防止
    #    过滤条件整体跳过导致 PM 误操作他版策略。
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
            return validation_error_resp(exc)
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
        return validation_error_resp(exc)
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
        return validation_error_resp(exc)
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
    # R3-B4：写路径统一走 services.strategies.toggle_strategy（启用方向重跑
    # 互斥/阶段校验 + 条件 UPDATE 防并发 + IntegrityError 兜底），
    # 与 update 路径同款"校验抛 StrategyValidationError → validation_error_resp"。
    # R3-B5：翻转与审计留痕同一事务（PM 侧此前零留痕，admin 侧有 AdminOpLog 双轨不一致）。
    old_enabled = s.enabled
    try:
        with transaction.atomic():
            svc_toggle(s)
            StrategyChangeLog.objects.create(
                strategy=s, operator=request.user,
                change_desc=f"启停策略: {s.name}（启用: {old_enabled}→{not old_enabled}）"[:255],
            )
    except StrategyValidationError as exc:
        return validation_error_resp(exc)
    return json_resp(ok(strategy_payload(s)))


def delete_strategy(request, sid):
    # 方法守卫由 strategy_detail_view 分发保证（仅 PATCH/DELETE 进入写路径）
    authed = _authed(request)
    if authed:
        return authed
    s = Strategy.objects.filter(id=sid).first()
    if not s:
        return fail_resp(CODE_NOT_FOUND, "策略不存在")
    perr = _check_pm_bound(request.user, s.branch)
    if perr:
        return perr
    # R3-B5/R4-B1：pending 借用流拦截 + 删除收敛到 services.strategies.delete_strategy
    # （PM 与 admin 两入口共用同一实现，行为不变）：BorrowFlow.strategy 为
    # CASCADE，直接删除会静默抹掉进行中的电子流与执行历史（B-P2-2/B4-01）。
    name, strategy_id = s.name, s.id
    try:
        with transaction.atomic():
            svc_delete(s)
            # 审计留痕（R3-B5）：StrategyChangeLog.strategy 为 CASCADE，随策略删除
            # 会被级联抹掉，故删除类审计落到独立存续的 AdminOpLog（action 沿用既有
            # "delete_strategy" 枚举，operator=当前用户，管理端"操作日志"可溯源）。
            try:
                AdminOpLog.objects.create(
                    operator=request.user, action="delete_strategy",
                    target_type="strategy", target_id=str(strategy_id), detail=name[:255],
                )
            except Exception:
                # 审计旁路不阻断业务，但保留堆栈便于排查（与 admin._admin_log 同口径）
                logger.exception("PM 删除策略审计写入失败：strategy=%s", strategy_id)
    except StrategyValidationError as exc:
        return validation_error_resp(exc)
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
