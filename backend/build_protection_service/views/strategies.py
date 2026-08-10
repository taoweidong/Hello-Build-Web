"""策略 views：列表/预览/创建/更新/启停/删除，含互斥与阶段冲突校验。"""
import re

from django.conf import settings
from django.contrib.auth import get_user_model

from ..api import err, ok
from ..models import Branch, Strategy, StrategyChangeLog, StrategyTemplate
from ..services.config import get_config
from ..services.mutex import check_build_mutex
from ..services.timeline import build_timeline
from . import authed_user, json_resp, parse_body

User = get_user_model()


def _authed(request):
    """手动认证，未认证返回响应。"""
    user, resp = authed_user(request)
    if resp:
        return resp
    request.user = user
    return None


def _strategy_payload(s):
    return {
        "id": s.id,
        "branch_id": s.branch_id,
        "branch_name": s.branch.name,
        "version_id": s.branch.version_id,
        "version_name": s.branch.version.name,
        "template_id": s.template_id,
        "template_name": s.template.name,
        "name": s.name,
        "build_start_time": s.build_start_time,
        "push_start_time": s.push_start_time,
        "push_mode": s.push_mode,
        "enabled": s.enabled,
    }


def _check_pm_bound(user, branch):
    if user.role == "admin":
        return None
    if user.role != "pm":
        return {"code": 40301, "message": "无权限操作策略", "status": 403}
    if branch.version.pm_user_id != user.id:
        return {"code": 40301, "message": "仅可操作本版本分支", "status": 403}
    return None


class SimpleNamespaceTpl:
    def __init__(self, smoke, analysis):
        self.smoke_minutes = smoke
        self.analysis_minutes = analysis


def _validate(branch, template, build_start_time, push_start_time, push_mode="normal", exclude_id=None):
    """互斥 + 阶段冲突校验，返回 (err_dict_or_None, conflict_dict_or_None)。"""
    for field, val in (("build_start_time", build_start_time), ("push_start_time", push_start_time)):
        if val is not None and not re.fullmatch(r"\d{2}:\d{2}", val):
            return {"code": 42201, "message": f"{field} 格式应为 HH:MM", "status": 422}, None
    version_id = branch.version_id
    build_minutes = get_config("build_minutes", settings.BUILD_MINUTES)
    push_minutes = get_config("push_minutes", settings.PUSH_MINUTES)
    sync_buffer_minutes = get_config("sync_buffer_minutes", settings.SYNC_BUFFER_MINUTES)
    mutex_hits = check_build_mutex(version_id, build_start_time, build_minutes, exclude_id)
    if mutex_hits:
        return ({"code": 40902, "message": "同一时间节点仅允许一个分支构建（资源互斥）", "status": 409},
                {"mutex": mutex_hits})
    same_branch = Strategy.objects.filter(branch=branch, enabled=True)
    if exclude_id:
        same_branch = same_branch.exclude(id=exclude_id)
    existing = [{
        "build_start_time": s.build_start_time,
        "template": SimpleNamespaceTpl(s.template.smoke_minutes, s.template.analysis_minutes),
        "push_mode": s.push_mode,
        "strategy_name": s.name,
        "push_start_time": s.push_start_time,
    } for s in same_branch]
    cand = [{
        "build_start_time": build_start_time,
        "template": SimpleNamespaceTpl(template.smoke_minutes, template.analysis_minutes),
        "push_mode": push_mode,
        "strategy_name": "candidate",
        "push_start_time": push_start_time,
    }]
    from ..services.conflict import detect_conflicts
    hits = detect_conflicts("2026-08-10", cand, existing, build_minutes,
                            push_minutes, sync_buffer_minutes)
    if hits:
        return ({"code": 40901, "message": "阶段时间冲突，请调整构建时间", "status": 409},
                {"conflicts": hits})
    return None, None


def list_strategies(request):
    authed = _authed(request)
    if authed:
        return authed
    qs = Strategy.objects.select_related("branch", "branch__version", "template").all()
    version_id = request.GET.get("version_id")
    branch_id = request.GET.get("branch_id")
    if version_id:
        qs = qs.filter(branch__version_id=version_id)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    # PM 仅可见其绑定版本策略（管理员可见全部）
    bound_version_id = getattr(request.user, "bound_version_id", None)
    if request.user.role == "pm" and bound_version_id:
        qs = qs.filter(branch__version_id=bound_version_id)
    return json_resp(ok([_strategy_payload(s) for s in qs]))


def preview_strategy(request):
    if request.method != "POST":
        return json_resp(err(42201, "不支持的请求方法"), status=422)
    authed = _authed(request)
    if authed:
        return authed
    body = parse_body(request)
    branch = Branch.objects.filter(id=body.get("branch_id")).first()
    template = StrategyTemplate.objects.filter(id=body.get("template_id")).first()
    if not branch or not template:
        return json_resp(err(42201, "分支或模板不存在"), status=422)
    build_start_time = body.get("build_start_time", "22:00")
    push_start_time = body.get("push_start_time")
    push_mode = body.get("push_mode", "normal")
    err_resp, conflict_obj = _validate(
        branch, template, build_start_time, push_start_time,
        push_mode=push_mode, exclude_id=body.get("id"))
    if err_resp:
        conflict_obj = conflict_obj or {}
        return json_resp(ok({"conflict": {**err_resp, **conflict_obj}}))
    # 计算时间线供前端实时预览（与 _validate 同一基准日期）
    build_minutes = get_config("build_minutes", settings.BUILD_MINUTES)
    push_minutes = get_config("push_minutes", settings.PUSH_MINUTES)
    sync_buffer_minutes = get_config("sync_buffer_minutes", settings.SYNC_BUFFER_MINUTES)
    timeline = build_timeline(
        "2026-08-10", build_start_time, template.smoke_minutes, template.analysis_minutes,
        build_minutes, push_minutes, sync_buffer_minutes, push_mode, push_start_time)
    return json_resp(ok({"conflict": None, "timeline": timeline}))


def create_strategy(request):
    authed = _authed(request)
    if authed:
        return authed
    body = parse_body(request)
    branch = Branch.objects.filter(id=body.get("branch_id")).first()
    template = StrategyTemplate.objects.filter(id=body.get("template_id")).first()
    if not branch or not template:
        return json_resp(err(42201, "分支或模板不存在"), status=422)
    perr = _check_pm_bound(request.user, branch)
    if perr:
        return json_resp(err(perr["code"], perr["message"]), status=perr["status"])
    build_start_time = body.get("build_start_time", "22:00")
    push_start_time = body.get("push_start_time")
    err_resp, _ = _validate(
        branch, template, build_start_time, push_start_time,
        push_mode=body.get("push_mode", "normal"))
    if err_resp:
        return json_resp(err(err_resp["code"], err_resp["message"]), status=err_resp["status"])
    s = Strategy.objects.create(
        branch=branch, template=template, name=body.get("name"),
        build_start_time=build_start_time,
        push_start_time=push_start_time or None,
        push_mode=body.get("push_mode", "normal"),
        enabled=body.get("enabled", True),
        created_by=request.user,
    )
    return json_resp(ok(_strategy_payload(s)))


def update_strategy(request, sid):
    authed = _authed(request)
    if authed:
        return authed
    s = Strategy.objects.select_related("branch").filter(id=sid).first()
    if not s:
        return json_resp(err(40401, "策略不存在"), status=404)
    perr = _check_pm_bound(request.user, s.branch)
    if perr:
        return json_resp(err(perr["code"], perr["message"]), status=perr["status"])
    body = parse_body(request)
    branch = s.branch
    template = s.template
    build_start_time = body.get("build_start_time", s.build_start_time)
    push_start_time = body.get("push_start_time", s.push_start_time)
    err_resp, _ = _validate(branch, template, build_start_time, push_start_time,
                            push_mode=body.get("push_mode", s.push_mode), exclude_id=s.id)
    if err_resp:
        return json_resp(err(err_resp["code"], err_resp["message"]), status=err_resp["status"])
    old = _strategy_payload(s)
    s.name = body.get("name", s.name)
    s.build_start_time = build_start_time
    s.push_start_time = push_start_time or None
    s.push_mode = body.get("push_mode", s.push_mode)
    s.enabled = body.get("enabled", s.enabled)
    s.save()
    StrategyChangeLog.objects.create(strategy=s, operator=request.user,
                                     change_desc=f"更新策略: {old['name']}")
    return json_resp(ok(_strategy_payload(s)))


def toggle_strategy(request, sid):
    authed = _authed(request)
    if authed:
        return authed
    s = Strategy.objects.filter(id=sid).first()
    if not s:
        return json_resp(err(40401, "策略不存在"), status=404)
    perr = _check_pm_bound(request.user, s.branch)
    if perr:
        return json_resp(err(perr["code"], perr["message"]), status=perr["status"])
    s.enabled = not s.enabled
    s.save()
    return json_resp(ok(_strategy_payload(s)))


def delete_strategy(request, sid):
    authed = _authed(request)
    if authed:
        return authed
    s = Strategy.objects.filter(id=sid).first()
    if not s:
        return json_resp(err(40401, "策略不存在"), status=404)
    perr = _check_pm_bound(request.user, s.branch)
    if perr:
        return json_resp(err(perr["code"], perr["message"]), status=perr["status"])
    s.delete()
    return json_resp(ok())


def strategies_view(request):
    if request.method == "GET":
        return list_strategies(request)
    if request.method == "POST":
        return create_strategy(request)
    return json_resp(err(42201, "不支持的请求方法"), status=422)


def strategy_detail_view(request, sid):
    if request.method == "PATCH":
        return update_strategy(request, sid)
    if request.method == "DELETE":
        return delete_strategy(request, sid)
    return json_resp(err(42201, "不支持的请求方法"), status=422)