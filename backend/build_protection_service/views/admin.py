"""系统管理 views：版本/用户/模板/配置/日志，仅 admin（模板 GET 允许 admin+pm）。"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from ..api import ok
from ..errors import (
    CODE_ASSOCIATION,
    CODE_DUPLICATE,
    CODE_FORBIDDEN,
    CODE_NOT_FOUND,
    CODE_UNPROCESSABLE,
)
from ..models import AdminOpLog, Branch, SecurityLog, Strategy, StrategyTemplate, Version
from ..services.config import get_config, set_config
from ..services.strategies import (
    StrategyValidationError,
    create_strategy as svc_create_strategy,
    strategy_payload,
    update_strategy as svc_update_strategy,
)
from . import (
    authed_user,
    fail_resp,
    fetch_by_id,
    json_resp,
    parse_body,
    parse_int,
    require_admin,
    validation_error_resp,
)
from .strategies import filter_strategies_qs

User = get_user_model()

_VALID_ROLES = {"admin", "pm", "builder", "tester", "integrator"}
_VALID_STATUSES = {"active", "archived"}


def _admin_log(user, action, target_type="", target_id="", detail=""):
    """写管理员操作日志，异常仅告警（审计旁路不阻断业务，但保留堆栈便于排查）。"""
    import logging

    try:
        AdminOpLog.objects.create(
            operator=user, action=action,
            target_type=target_type, target_id=str(target_id), detail=detail,
        )
    except Exception:
        logging.getLogger(__name__).exception(
            "管理操作日志写入失败：action=%s target=%s", action, target_id)


# ---------- 版本 ----------

def list_versions(user):
    qs = Version.objects.select_related("pm_user").prefetch_related("branches").all()
    return json_resp(ok([{
        "id": v.id, "name": v.name, "pm_user_id": v.pm_user_id, "status": v.status,
        "branches": [{"id": b.id, "name": b.name} for b in v.branches.all()],
    } for v in qs]))


def create_version(user, body):
    name = body.get("name")
    pm_user_id = parse_int(body.get("pm_user_id"))
    if not isinstance(name, str) or not name.strip() or pm_user_id is None:
        return fail_resp(CODE_UNPROCESSABLE, "版本名与 PM 必填")
    name = name.strip()
    if Version.objects.filter(name=name).exists():
        return fail_resp(CODE_DUPLICATE, "版本号已存在")
    pm = User.objects.filter(id=pm_user_id).first()
    if not pm:
        return fail_resp(CODE_UNPROCESSABLE, "PM 用户不存在")
    # 版本挂给非 PM 角色会形成"无主版本"（该用户不会获得 PM 权限），入口拒绝
    if pm.role != "pm":
        return fail_resp(CODE_UNPROCESSABLE, "pm_user_id 必须为 PM 角色用户")
    status = body.get("status", "active")
    if status not in _VALID_STATUSES:
        return fail_resp(CODE_UNPROCESSABLE, "非法状态")
    try:
        v = Version.objects.create(name=name, pm_user=pm, status=status)
    except IntegrityError:
        return fail_resp(CODE_DUPLICATE, "版本号已存在")
    _admin_log(user, "create_version", target_type="version", target_id=v.id, detail=name)
    return json_resp(ok({"id": v.id, "name": v.name, "pm_user_id": v.pm_user_id, "status": v.status}))


def extra_view(request):
    user, resp = authed_user(request)
    if resp:
        return resp
    perr = require_admin(user)
    if perr:
        return perr
    if request.method == "GET":
        return list_versions(user)
    if request.method == "POST":
        return create_version(user, parse_body(request))
    return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")


def update_version(request, vid):
    # 方法守卫：此前 GET 会执行空 body 的 save 并写审计日志、DELETE 不删数据
    # 却返回"成功"payload（对客户端是删除成功假象），统一拒绝非写方法。
    if request.method not in ("PUT", "PATCH"):
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
    user, resp = authed_user(request)
    if resp:
        return resp
    perr = require_admin(user)
    if perr:
        return perr
    v = Version.objects.filter(id=vid).first()
    if not v:
        return fail_resp(CODE_NOT_FOUND, "版本不存在")
    body = parse_body(request)
    if body.get("name") is not None:
        if not isinstance(body["name"], str) or not body["name"].strip():
            return fail_resp(CODE_UNPROCESSABLE, "版本名不能为空")
        dup = Version.objects.filter(name=body["name"].strip()).exclude(id=vid).exists()
        if dup:
            return fail_resp(CODE_DUPLICATE, "版本号已存在")
        v.name = body["name"].strip()
    if body.get("pm_user_id") is not None:
        pm_id = parse_int(body["pm_user_id"])
        if pm_id is None:
            return fail_resp(CODE_UNPROCESSABLE, "pm_user_id 应为整数")
        pm = User.objects.filter(id=pm_id).first()
        if not pm:
            return fail_resp(CODE_UNPROCESSABLE, "PM 用户不存在")
        if pm.role != "pm":
            return fail_resp(CODE_UNPROCESSABLE, "pm_user_id 必须为 PM 角色用户")
        v.pm_user = pm
    if body.get("status") is not None:
        if body["status"] not in _VALID_STATUSES:
            return fail_resp(CODE_UNPROCESSABLE, "非法状态")
        v.status = body["status"]
    try:
        v.save()
    except IntegrityError:
        return fail_resp(CODE_DUPLICATE, "版本号或 PM 已占用")
    _admin_log(user, "update_version", target_type="version", target_id=vid)
    return json_resp(ok({"id": v.id, "name": v.name, "pm_user_id": v.pm_user_id, "status": v.status}))


def add_branch(request, vid):
    if request.method != "POST":
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
    user, resp = authed_user(request)
    if resp:
        return resp
    perr = require_admin(user)
    if perr:
        return perr
    v = Version.objects.filter(id=vid).first()
    if not v:
        return fail_resp(CODE_NOT_FOUND, "版本不存在")
    body = parse_body(request)
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        return fail_resp(CODE_UNPROCESSABLE, "分支名必填")
    name = name.strip()
    if Branch.objects.filter(version=v, name=name).exists():
        return fail_resp(CODE_DUPLICATE, "该版本下分支已存在")
    try:
        b = Branch.objects.create(version=v, name=name)
    except IntegrityError:
        return fail_resp(CODE_DUPLICATE, "该版本下分支已存在")
    _admin_log(user, "add_branch", target_type="branch", target_id=b.id, detail=f"{v.name}/{name}")
    return json_resp(ok({"id": b.id, "version_id": v.id, "name": b.name}))


# ---------- 用户 ----------

def users_view(request):
    user, resp = authed_user(request)
    if resp:
        return resp
    perr = require_admin(user)
    if perr:
        return perr
    if request.method == "GET":
        qs = User.objects.all()
        return json_resp(ok([{
            "id": u.id, "username": u.username, "display_name": u.display_name,
            "role": u.role, "is_active": u.is_active,
        } for u in qs]))
    if request.method == "POST":
        body = parse_body(request)
        username = body.get("username")
        role = body.get("role", "builder")
        password = body.get("password")
        display_name = body.get("display_name", "")
        if not isinstance(username, str) or not username.strip():
            return fail_resp(CODE_UNPROCESSABLE, "用户名必填")
        # 密码必填：不再回退默认弱口令 "123456"（2026-10-12 评估 B-P1-14）
        if not isinstance(password, str) or not password.strip():
            return fail_resp(CODE_UNPROCESSABLE, "密码必填")
        if role not in _VALID_ROLES:
            return fail_resp(CODE_UNPROCESSABLE, "非法角色")
        if not isinstance(display_name, str):
            return fail_resp(CODE_UNPROCESSABLE, "display_name 应为字符串")
        if User.objects.filter(username=username).exists():
            return fail_resp(CODE_DUPLICATE, "用户名已存在")
        try:
            u = User.objects.create_user(
                username=username.strip(), password=password,
                role=role, display_name=display_name,
            )
        except IntegrityError:
            return fail_resp(CODE_DUPLICATE, "用户名已存在")
        _admin_log(user, "create_user", target_type="user", target_id=u.id, detail=username)
        return json_resp(ok({"id": u.id, "username": u.username, "role": u.role}))
    return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")


def update_user(request, uid):
    if request.method != "PATCH":
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
    user, resp = authed_user(request)
    if resp:
        return resp
    perr = require_admin(user)
    if perr:
        return perr
    u = User.objects.filter(id=uid).first()
    if not u:
        return fail_resp(CODE_NOT_FOUND, "用户不存在")
    body = parse_body(request)
    # 记录变更前身份，用于"最后一个 admin"保护判定
    orig_role, orig_is_active = u.role, u.is_active
    if body.get("password"):
        if not isinstance(body["password"], str):
            return fail_resp(CODE_UNPROCESSABLE, "密码应为字符串")
        u.set_password(body["password"])
    if body.get("role") is not None:
        if body["role"] not in _VALID_ROLES:
            return fail_resp(CODE_UNPROCESSABLE, "非法角色")
        u.role = body["role"]
    if body.get("display_name") is not None:
        if not isinstance(body["display_name"], str):
            return fail_resp(CODE_UNPROCESSABLE, "display_name 应为字符串")
        u.display_name = body["display_name"]
    if body.get("is_active") is not None:
        # 严格布尔：此前 str(...).lower() in ("true","1") 会把任意垃圾值静默解析成"停用"
        if not isinstance(body["is_active"], bool):
            return fail_resp(CODE_UNPROCESSABLE, "is_active 应为布尔值")
        u.is_active = body["is_active"]
    # 最后一个启用状态的 admin 不可被停用/降级，避免系统失去管理入口；
    # 检查与保存同一事务（SQLite BEGIN IMMEDIATE 串行化写路径），并发互降级不会双双通过。
    with transaction.atomic():
        losing_admin = (
            orig_role == "admin" and orig_is_active
            and (u.is_active is False or u.role != "admin")
        )
        if losing_admin:
            others = User.objects.filter(role="admin", is_active=True).exclude(id=u.id).exists()
            if not others:
                return fail_resp(CODE_DUPLICATE, "系统至少保留一名启用状态的管理员")
        u.save()
    _admin_log(user, "update_user", target_type="user", target_id=uid)
    return json_resp(ok({"id": u.id, "username": u.username, "role": u.role, "is_active": u.is_active}))


# ---------- 模板 ----------

def _parse_template_minutes(body):
    """解析 body 中的 smoke_minutes/analysis_minutes（POST/PATCH 共用）。

    仅处理显式提供且非 None 的字段；非法类型/负数 → 42201 响应，
    避免落库时 ValueError/CHECK 约束 IntegrityError/TypeError 冒成 500
    （2026-10-12 质量评估 B-P0-4）。返回 (parsed_dict, err_response)。
    """
    parsed = {}
    for field in ("smoke_minutes", "analysis_minutes"):
        if body.get(field) is None:
            continue
        val = parse_int(body[field])
        if val is None or val < 0:
            return None, fail_resp(CODE_UNPROCESSABLE, f"{field} 应为非负整数")
        parsed[field] = val
    return parsed, None


def templates_view(request):
    user, resp = authed_user(request)
    if resp:
        return resp
    if user.role not in ("admin", "pm"):
        return fail_resp(CODE_FORBIDDEN, "无权限操作模板")
    if request.method == "GET":
        qs = StrategyTemplate.objects.all()
        return json_resp(ok([{
            "id": t.id, "name": t.name, "smoke_minutes": t.smoke_minutes,
            "analysis_minutes": t.analysis_minutes, "description": t.description,
        } for t in qs]))
    if request.method == "POST":
        perr = require_admin(user)
        if perr:
            return perr
        body = parse_body(request)
        name = body.get("name")
        if not isinstance(name, str) or not name.strip():
            return fail_resp(CODE_UNPROCESSABLE, "模板名必填")
        if StrategyTemplate.objects.filter(name=name.strip()).exists():
            return fail_resp(CODE_DUPLICATE, "模板名已存在")
        parsed, verr = _parse_template_minutes(body)
        if verr:
            return verr
        description = body.get("description", "")
        if not isinstance(description, str):
            return fail_resp(CODE_UNPROCESSABLE, "description 应为字符串")
        t = StrategyTemplate.objects.create(
            name=name.strip(),
            smoke_minutes=parsed.get("smoke_minutes", 0),
            analysis_minutes=parsed.get("analysis_minutes", 0),
            description=description,
        )
        _admin_log(user, "create_template", target_type="template", target_id=t.id, detail=t.name)
        return json_resp(ok(_template_payload(t)))
    return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")


def _template_payload(t):
    return {
        "id": t.id, "name": t.name, "smoke_minutes": t.smoke_minutes,
        "analysis_minutes": t.analysis_minutes, "description": t.description,
    }


def _get_template_or_404(tid):
    # 共享 fetch-or-404 实现（原先各视图手写一份）
    return fetch_by_id(StrategyTemplate, tid, not_found="模板不存在")


def update_template(request, user, tid):
    perr = require_admin(user)
    if perr:
        return perr
    t, notfound = _get_template_or_404(tid)
    if notfound:
        return notfound
    body = parse_body(request)
    if body.get("name") is not None:
        if not isinstance(body["name"], str) or not body["name"].strip():
            return fail_resp(CODE_UNPROCESSABLE, "模板名不能为空")
        new_name = body["name"].strip()
        if StrategyTemplate.objects.filter(name=new_name).exclude(id=tid).exists():
            return fail_resp(CODE_DUPLICATE, "模板名已存在")
        t.name = new_name
    parsed, verr = _parse_template_minutes(body)
    if verr:
        return verr
    for field, val in parsed.items():
        setattr(t, field, val)
    if body.get("description") is not None:
        if not isinstance(body["description"], str):
            return fail_resp(CODE_UNPROCESSABLE, "description 应为字符串")
        t.description = body["description"]
    try:
        t.save()
    except IntegrityError:
        # 并发重命名撞 unique 约束兜底（StrategyTemplate.name 唯一）
        return fail_resp(CODE_DUPLICATE, "模板名已存在")
    _admin_log(user, "update_template", target_type="template", target_id=tid)
    return json_resp(ok(_template_payload(t)))


def delete_template(request, user, tid):
    perr = require_admin(user)
    if perr:
        return perr
    t, notfound = _get_template_or_404(tid)
    if notfound:
        return notfound
    try:
        t.delete()
    except ProtectedError:
        # Strategy.template 为 PROTECT，被引用时抛 ProtectedError 而非 IntegrityError
        return fail_resp(CODE_ASSOCIATION, "模板正在被策略引用，无法删除")
    _admin_log(user, "delete_template", target_type="template", target_id=tid)
    return json_resp(ok())


def template_detail_view(request, tid):
    user, resp = authed_user(request)
    if resp:
        return resp
    if request.method == "PATCH":
        return update_template(request, user, tid)
    if request.method == "DELETE":
        return delete_template(request, user, tid)
    return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")


# ---------- 配置 ----------

# 运行期配置覆盖层统一在 ..services.config，admin 可改，领域逻辑经
# get_config 读取，未覆盖时回退 settings 默认值；避免直接改写全局 settings。


def _config_payload():
    return {
        "build_minutes": get_config("build_minutes", settings.BUILD_MINUTES),
        "push_minutes": get_config("push_minutes", settings.PUSH_MINUTES),
        "sync_buffer_minutes": get_config("sync_buffer_minutes", settings.SYNC_BUFFER_MINUTES),
    }


def config_view(request):
    user, resp = authed_user(request)
    if resp:
        return resp
    perr = require_admin(user)
    if perr:
        return perr
    if request.method == "GET":
        return json_resp(ok(_config_payload()))
    if request.method == "PUT":
        body = parse_body(request)
        for key in ("build_minutes", "push_minutes", "sync_buffer_minutes"):
            if body.get(key) is not None:
                try:
                    set_config(key, int(body[key]))
                except (TypeError, ValueError):
                    return fail_resp(CODE_UNPROCESSABLE, f"{key} 应为整数")
        _admin_log(user, "update_config", target_type="config", detail=str(body))
        return json_resp(ok(_config_payload()))
    return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")


# ---------- 日志 ----------

def logs_view(request, kind):
    user, resp = authed_user(request)
    if resp:
        return resp
    perr = require_admin(user)
    if perr:
        return perr
    if kind not in ("operations", "security"):
        return fail_resp(CODE_UNPROCESSABLE, "kind 应为 operations 或 security")
    items = []
    if kind == "operations":
        qs = AdminOpLog.objects.select_related("operator").order_by("-id")[:200]
        for log in qs:
            items.append({
                "id": log.id,
                "operator": log.operator.username if log.operator else "",
                "action": log.action,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "detail": log.detail,
                "created_at": log.created_at,
            })
    else:
        qs = SecurityLog.objects.order_by("-id")[:200]
        for log in qs:
            items.append({
                "id": log.id,
                "operator": log.username,
                "action": log.action,
                "target_type": "",
                "detail": log.detail,
                "created_at": log.created_at,
            })
    return json_resp(ok(items))


# ---------- 策略管理（管理员全量 CRUD，写入管理操作日志） ----------
# 校验与写路径复用 services.strategies（与 PM 入口同一实现），仅 admin 可调用。


def _list_admin_strategies(request):
    qs = Strategy.objects.select_related("branch", "branch__version", "template").all()
    # 参数校验与过滤逻辑与 PM 列表入口共用同一实现（消除克隆）
    qs, err_resp = filter_strategies_qs(qs, request)
    if err_resp:
        return err_resp
    return json_resp(ok([strategy_payload(s) for s in qs]))


def _create_admin_strategy(request, user):
    body = parse_body(request)
    branch_id = parse_int(body.get("branch_id"))
    template_id = parse_int(body.get("template_id"))
    if branch_id is None or template_id is None:
        return fail_resp(CODE_UNPROCESSABLE, "branch_id / template_id 应为整数")
    branch = Branch.objects.filter(id=branch_id).first()
    template = StrategyTemplate.objects.filter(id=template_id).first()
    if not branch or not template:
        return fail_resp(CODE_UNPROCESSABLE, "分支或模板不存在")
    try:
        s = svc_create_strategy(
            branch, template, user, name=body.get("name"),
            build_start_time=body.get("build_start_time", "22:00"),
            push_start_time=body.get("push_start_time"),
            push_mode=body.get("push_mode", "normal"),
            enabled=body.get("enabled", True),
        )
    except StrategyValidationError as exc:
        return validation_error_resp(exc)
    _admin_log(user, "create_strategy", target_type="strategy", target_id=s.id, detail=s.name)
    return json_resp(ok(strategy_payload(s)))


def admin_strategies_view(request):
    user, resp = authed_user(request)
    if resp:
        return resp
    perr = require_admin(user)
    if perr:
        return perr
    if request.method == "GET":
        return _list_admin_strategies(request)
    if request.method == "POST":
        return _create_admin_strategy(request, user)
    return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")


def _update_admin_strategy(request, user, sid):
    s = Strategy.objects.select_related("branch", "branch__version", "template").filter(id=sid).first()
    if not s:
        return fail_resp(CODE_NOT_FOUND, "策略不存在")
    body = parse_body(request)
    try:
        svc_update_strategy(s, body, user)
    except StrategyValidationError as exc:
        return validation_error_resp(exc)
    _admin_log(user, "update_strategy", target_type="strategy", target_id=sid, detail=s.name)
    return json_resp(ok(strategy_payload(s)))


def _toggle_admin_strategy(request, user, sid):
    s = Strategy.objects.select_related("branch", "branch__version", "template").filter(id=sid).first()
    if not s:
        return fail_resp(CODE_NOT_FOUND, "策略不存在")
    s.enabled = not s.enabled
    try:
        # 启用可能撞 uniq_active_strategy_branch_time（同分支同刻已有启用策略），
        # 与 PM 路由 toggle 同款兜底，避免裸 IntegrityError → 500 破坏统一契约；
        # 包子事务防止冲突污染外层事务（否则后续查询报 TransactionManagementError）。
        with transaction.atomic():
            s.save()
    except IntegrityError as exc:
        msg = str(exc)
        if "strategy.branch_id" in msg and "build_start_time" in msg:
            return fail_resp(
                CODE_DUPLICATE, "该分支已存在同一构建时刻的启用策略，无法启用"
            )
        raise
    _admin_log(user, "toggle_strategy", target_type="strategy", target_id=sid)
    return json_resp(ok(strategy_payload(s)))


def _delete_admin_strategy(request, user, sid):
    s = Strategy.objects.filter(id=sid).first()
    if not s:
        return fail_resp(CODE_NOT_FOUND, "策略不存在")
    s.delete()
    _admin_log(user, "delete_strategy", target_type="strategy", target_id=sid)
    return json_resp(ok())


def admin_strategy_detail_view(request, sid):
    user, resp = authed_user(request)
    if resp:
        return resp
    perr = require_admin(user)
    if perr:
        return perr
    if request.method == "PATCH":
        return _update_admin_strategy(request, user, sid)
    if request.method == "DELETE":
        return _delete_admin_strategy(request, user, sid)
    return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")


def admin_strategy_toggle_view(request, sid):
    user, resp = authed_user(request)
    if resp:
        return resp
    perr = require_admin(user)
    if perr:
        return perr
    if request.method != "PATCH":
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
    return _toggle_admin_strategy(request, user, sid)