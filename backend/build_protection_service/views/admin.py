"""系统管理 views：版本/用户/模板/配置/日志，仅 admin（模板 GET 允许 admin+pm）。"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from ..api import err, ok
from ..models import AdminOpLog, Branch, SecurityLog, StrategyTemplate, Version
from . import authed_user, json_resp, parse_body

User = get_user_model()

_VALID_ROLES = {"admin", "pm", "builder", "tester", "integrator"}


def _admin_log(user, action, target_type="", target_id="", detail=""):
    """写管理员操作日志，异常静默。"""
    try:
        AdminOpLog.objects.create(
            operator=user, action=action,
            target_type=target_type, target_id=str(target_id), detail=detail,
        )
    except Exception:
        pass


def _require_admin(user):
    if user.role != "admin":
        return json_resp(err(40301, "仅管理员可操作"), status=403)
    return None


# ---------- 版本 ----------

def list_versions(user):
    qs = Version.objects.select_related("pm_user").all()
    return json_resp(ok([{
        "id": v.id, "name": v.name, "pm_user_id": v.pm_user_id, "status": v.status,
    } for v in qs]))


def create_version(user, body):
    name = body.get("name")
    pm_user_id = body.get("pm_user_id")
    if not name or not pm_user_id:
        return json_resp(err(42201, "版本名与 PM 必填"), status=422)
    if Version.objects.filter(name=name).exists():
        return json_resp(err(40902, "版本号已存在"), status=409)
    pm = User.objects.filter(id=pm_user_id).first()
    if not pm:
        return json_resp(err(42201, "PM 用户不存在"), status=422)
    try:
        v = Version.objects.create(name=name, pm_user=pm, status=body.get("status", "active"))
    except IntegrityError:
        return json_resp(err(40902, "版本号已存在"), status=409)
    _admin_log(user, "create_version", target_type="version", target_id=v.id, detail=name)
    return json_resp(ok({"id": v.id, "name": v.name, "pm_user_id": v.pm_user_id, "status": v.status}))


def extra_view(request):
    user, resp = authed_user(request)
    if resp:
        return resp
    perr = _require_admin(user)
    if perr:
        return perr
    if request.method == "GET":
        return list_versions(user)
    if request.method == "POST":
        return create_version(user, parse_body(request))
    return json_resp(err(42201, "不支持的请求方法"), status=422)


def update_version(request, vid):
    user, resp = authed_user(request)
    if resp:
        return resp
    perr = _require_admin(user)
    if perr:
        return perr
    v = Version.objects.filter(id=vid).first()
    if not v:
        return json_resp(err(40401, "版本不存在"), status=404)
    body = parse_body(request)
    if body.get("name") is not None:
        dup = Version.objects.filter(name=body["name"]).exclude(id=vid).exists()
        if dup:
            return json_resp(err(40902, "版本号已存在"), status=409)
        v.name = body["name"]
    if body.get("pm_user_id") is not None:
        pm = User.objects.filter(id=body["pm_user_id"]).first()
        if not pm:
            return json_resp(err(42201, "PM 用户不存在"), status=422)
        v.pm_user = pm
    if body.get("status") is not None:
        v.status = body["status"]
    try:
        v.save()
    except IntegrityError:
        return json_resp(err(40902, "版本号或 PM 已占用"), status=409)
    _admin_log(user, "update_version", target_type="version", target_id=vid)
    return json_resp(ok({"id": v.id, "name": v.name, "pm_user_id": v.pm_user_id, "status": v.status}))


def add_branch(request, vid):
    user, resp = authed_user(request)
    if resp:
        return resp
    perr = _require_admin(user)
    if perr:
        return perr
    v = Version.objects.filter(id=vid).first()
    if not v:
        return json_resp(err(40401, "版本不存在"), status=404)
    body = parse_body(request)
    name = body.get("name")
    if not name:
        return json_resp(err(42201, "分支名必填"), status=422)
    if Branch.objects.filter(version=v, name=name).exists():
        return json_resp(err(40902, "该版本下分支已存在"), status=409)
    try:
        b = Branch.objects.create(version=v, name=name)
    except IntegrityError:
        return json_resp(err(40902, "该版本下分支已存在"), status=409)
    _admin_log(user, "add_branch", target_type="branch", target_id=b.id, detail=f"{v.name}/{name}")
    return json_resp(ok({"id": b.id, "version_id": v.id, "name": b.name}))


# ---------- 用户 ----------

def users_view(request):
    user, resp = authed_user(request)
    if resp:
        return resp
    perr = _require_admin(user)
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
        if not username:
            return json_resp(err(42201, "用户名必填"), status=422)
        if role not in _VALID_ROLES:
            return json_resp(err(42201, "非法角色"), status=422)
        if User.objects.filter(username=username).exists():
            return json_resp(err(40902, "用户名已存在"), status=409)
        try:
            u = User.objects.create_user(
                username=username, password=body.get("password") or "123456",
                role=role, display_name=body.get("display_name", ""),
            )
        except IntegrityError:
            return json_resp(err(40902, "用户名已存在"), status=409)
        _admin_log(user, "create_user", target_type="user", target_id=u.id, detail=username)
        return json_resp(ok({"id": u.id, "username": u.username, "role": u.role}))
    return json_resp(err(42201, "不支持的请求方法"), status=422)


def update_user(request, uid):
    user, resp = authed_user(request)
    if resp:
        return resp
    perr = _require_admin(user)
    if perr:
        return perr
    u = User.objects.filter(id=uid).first()
    if not u:
        return json_resp(err(40401, "用户不存在"), status=404)
    body = parse_body(request)
    if body.get("password"):
        u.set_password(body["password"])
    if body.get("role") is not None:
        if body["role"] not in _VALID_ROLES:
            return json_resp(err(42201, "非法角色"), status=422)
        u.role = body["role"]
    if body.get("display_name") is not None:
        u.display_name = body["display_name"]
    if body.get("is_active") is not None:
        u.is_active = bool(body["is_active"])
    u.save()
    _admin_log(user, "update_user", target_type="user", target_id=uid)
    return json_resp(ok({"id": u.id, "username": u.username, "role": u.role, "is_active": u.is_active}))


# ---------- 模板 ----------

def templates_view(request):
    user, resp = authed_user(request)
    if resp:
        return resp
    if user.role not in ("admin", "pm"):
        return json_resp(err(40301, "无权限操作模板"), status=403)
    if request.method == "GET":
        qs = StrategyTemplate.objects.all()
        return json_resp(ok([{
            "id": t.id, "name": t.name, "smoke_minutes": t.smoke_minutes,
            "analysis_minutes": t.analysis_minutes, "description": t.description,
        } for t in qs]))
    if request.method == "POST":
        perr = _require_admin(user)
        if perr:
            return perr
        body = parse_body(request)
        name = body.get("name")
        if not name:
            return json_resp(err(42201, "模板名必填"), status=422)
        t = StrategyTemplate.objects.create(
            name=name,
            smoke_minutes=body.get("smoke_minutes", 0),
            analysis_minutes=body.get("analysis_minutes", 0),
            description=body.get("description", ""),
        )
        _admin_log(user, "create_template", target_type="template", target_id=t.id, detail=name)
        return json_resp(ok({"id": t.id, "name": t.name, "smoke_minutes": t.smoke_minutes,
                             "analysis_minutes": t.analysis_minutes, "description": t.description}))
    return json_resp(err(42201, "不支持的请求方法"), status=422)


def _template_payload(t):
    return {
        "id": t.id, "name": t.name, "smoke_minutes": t.smoke_minutes,
        "analysis_minutes": t.analysis_minutes, "description": t.description,
    }


def _get_template_or_404(tid):
    t = StrategyTemplate.objects.filter(id=tid).first()
    if not t:
        return None, json_resp(err(40401, "模板不存在"), status=404)
    return t, None


def update_template(request, user, tid):
    perr = _require_admin(user)
    if perr:
        return perr
    t, notfound = _get_template_or_404(tid)
    if notfound:
        return notfound
    body = parse_body(request)
    if body.get("name") is not None:
        t.name = body["name"]
    if body.get("smoke_minutes") is not None:
        t.smoke_minutes = body["smoke_minutes"]
    if body.get("analysis_minutes") is not None:
        t.analysis_minutes = body["analysis_minutes"]
    if body.get("description") is not None:
        t.description = body["description"]
    t.save()
    _admin_log(user, "update_template", target_type="template", target_id=tid)
    return json_resp(ok(_template_payload(t)))


def delete_template(request, user, tid):
    perr = _require_admin(user)
    if perr:
        return perr
    t, notfound = _get_template_or_404(tid)
    if notfound:
        return notfound
    try:
        t.delete()
    except IntegrityError:
        return json_resp(err(40901, "模板正在被策略引用，无法删除"), status=409)
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
    return json_resp(err(42201, "不支持的请求方法"), status=422)


# ---------- 配置 ----------

# 运行时配置覆盖：避免直接改写全局 settings（会污染其他测试/请求），
# 未覆盖的字段回退到 settings 默认值。
_RUNTIME_CONFIG = {}


def _config_value(key, default):
    return _RUNTIME_CONFIG.get(key, default)


def config_view(request):
    user, resp = authed_user(request)
    if resp:
        return resp
    perr = _require_admin(user)
    if perr:
        return perr
    if request.method == "GET":
        return json_resp(ok({
            "build_minutes": _config_value("build_minutes", settings.BUILD_MINUTES),
            "push_minutes": _config_value("push_minutes", settings.PUSH_MINUTES),
            "sync_buffer_minutes": _config_value("sync_buffer_minutes", settings.SYNC_BUFFER_MINUTES),
        }))
    if request.method == "PUT":
        body = parse_body(request)
        for key in ("build_minutes", "push_minutes", "sync_buffer_minutes"):
            if body.get(key) is not None:
                try:
                    _RUNTIME_CONFIG[key] = int(body[key])
                except (TypeError, ValueError):
                    return json_resp(err(42201, f"{key} 应为整数"), status=422)
        _admin_log(user, "update_config", target_type="config", detail=str(body))
        return json_resp(ok({
            "build_minutes": _config_value("build_minutes", settings.BUILD_MINUTES),
            "push_minutes": _config_value("push_minutes", settings.PUSH_MINUTES),
            "sync_buffer_minutes": _config_value("sync_buffer_minutes", settings.SYNC_BUFFER_MINUTES),
        }))
    return json_resp(err(42201, "不支持的请求方法"), status=422)


# ---------- 日志 ----------

def logs_view(request, kind):
    user, resp = authed_user(request)
    if resp:
        return resp
    perr = _require_admin(user)
    if perr:
        return perr
    items = []
    if kind == "operations":
        qs = AdminOpLog.objects.select_related("operator").order_by("-id")[:200]
        for log in qs:
            items.append({
                "id": log.id,
                "operator": log.operator.username if log.operator else "",
                "action": log.action,
                "target_type": log.target_type,
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