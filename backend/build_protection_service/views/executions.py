"""执行轮次 views：列表/详情/测试结论提交。"""
from datetime import timedelta

from django.conf import settings
from django.utils.timezone import now

from ..api import err, ok
from ..models import ExecutionRound
from ..services.config import get_config
from . import authed_user, json_resp, parse_body


def _fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


def _round_payload(r):
    return {
        "id": r.id,
        "strategy_id": r.strategy_id,
        "strategy_name": r.strategy.name,
        "exec_date": r.exec_date.strftime("%Y-%m-%d"),
        "build_start_at": _fmt(r.build_start_at),
        "build_end_at": _fmt(r.build_end_at),
        "smoke_start_at": _fmt(r.smoke_start_at),
        "smoke_end_at": _fmt(r.smoke_end_at),
        "conclusion": r.conclusion,
        "note": r.note,
        "push_status": r.push_status,
    }


def executions_view(request):
    user, resp = authed_user(request)
    if resp:
        return resp
    qs = ExecutionRound.objects.select_related("strategy", "strategy__branch").order_by("-id")
    if user.role == "pm":
        qs = qs.filter(strategy__branch__version__pm_user=user)
    return json_resp(ok([_round_payload(r) for r in qs[:200]]))


def round_detail(request, rid):
    _, resp = authed_user(request)
    if resp:
        return resp
    r = ExecutionRound.objects.select_related("strategy").filter(id=rid).first()
    if not r:
        return json_resp(err(40401, "执行轮次不存在"), status=404)
    logs = [
        {"id": lg.id, "stage": lg.stage, "message": lg.message, "created_at": _fmt(lg.created_at)}
        for lg in r.logs.all().order_by("id")
    ]
    return json_resp(ok({"round": _round_payload(r), "logs": logs}))


def conclusion_view(request, rid):
    user, resp = authed_user(request)
    if resp:
        return resp
    r = ExecutionRound.objects.select_related("strategy").filter(id=rid).first()
    if not r:
        return json_resp(err(40401, "执行轮次不存在"), status=404)
    if user.role != "tester":
        return json_resp(err(40301, "仅测试人员可提交结论"), status=403)
    body = parse_body(request)
    r.conclusion = body.get("conclusion")
    r.note = body.get("note", r.note or "")
    r.analysis_end_at = now()
    if r.conclusion == "pass" and r.strategy.push_mode == "normal":
        push_minutes = get_config("push_minutes", settings.PUSH_MINUTES)
        r.push_start_at = r.analysis_end_at
        r.push_end_at = r.analysis_end_at + timedelta(minutes=push_minutes)
        r.push_status = "pushed"
    r.save()
    return json_resp(ok(_round_payload(r)))