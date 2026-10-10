"""执行/变更日志 views。"""
from ..api import ok
from ..models import ExecutionLog, StrategyChangeLog
from . import authed_user, fail_resp, first_error, fmt_dt, json_resp


def execution_logs(request):
    _, resp = authed_user(request)
    if resp:
        return resp
    qs = ExecutionLog.objects.select_related("round", "round__strategy").order_by("-id")[:200]
    result = [
        {"id": lg.id, "round_id": lg.round_id, "strategy": lg.round.strategy.name,
         "stage": lg.stage, "message": lg.message, "created_at": fmt_dt(lg.created_at)}
        for lg in qs
    ]
    return json_resp(ok(result))


def change_logs(request):
    _, resp = authed_user(request)
    if resp:
        return resp
    qs = StrategyChangeLog.objects.select_related("strategy", "operator").order_by("-id")[:200]
    result = [
        {"id": cl.id, "strategy": cl.strategy.name,
         "operator": cl.operator.username if cl.operator else "",
         "change_desc": cl.change_desc, "created_at": fmt_dt(cl.created_at)}
        for cl in qs
    ]
    return json_resp(ok(result))