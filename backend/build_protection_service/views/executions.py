"""执行轮次 views：列表/详情/测试结论提交。"""
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.timezone import now

from ..api import err, ok
from ..models import ExecutionRound
from ..services.config import get_config
from . import authed_user, fail_resp, first_error, fmt_dt, json_resp, parse_body, parse_int


def _round_payload(r):
    return {
        "id": r.id,
        "strategy_id": r.strategy_id,
        "strategy_name": r.strategy.name,
        "exec_date": r.exec_date.strftime("%Y-%m-%d"),
        "build_start_at": fmt_dt(r.build_start_at),
        "build_end_at": fmt_dt(r.build_end_at),
        "smoke_start_at": fmt_dt(r.smoke_start_at),
        "smoke_end_at": fmt_dt(r.smoke_end_at),
        "conclusion": r.conclusion,
        "conclusion_note": r.note,
        "push_status": r.push_status,
    }


def executions_view(request):
    user, resp = authed_user(request)
    if resp:
        return resp
    qs = ExecutionRound.objects.select_related("strategy", "strategy__branch").order_by("-id")
    if user.role == "pm":
        qs = qs.filter(strategy__branch__version__pm_user=user)
    # 前端按策略/日期范围过滤（详情面板近 7 天历史、执行看板按日）
    raw_strategy_id = request.GET.get("strategy_id")
    if raw_strategy_id:
        strategy_id = parse_int(raw_strategy_id)
        if strategy_id is None:
            return fail_resp(42201, "strategy_id 应为整数")
        qs = qs.filter(strategy_id=strategy_id)
    # 日期过滤参数须校验，非法值返回 42201（避免 exec_date="abc" → ValidationError → 500）
    try:
        date_ = request.GET.get("date")
        if date_:
            qs = qs.filter(exec_date=date_)
        from_date = request.GET.get("from")
        to_date = request.GET.get("to")
        if from_date:
            qs = qs.filter(exec_date__gte=from_date)
        if to_date:
            qs = qs.filter(exec_date__lte=to_date)
    except (ValueError, ValidationError):
        return fail_resp(42201, "日期筛选格式非法，应为 YYYY-MM-DD")
    return json_resp(ok([_round_payload(r) for r in qs[:200]]))


def round_detail(request, rid):
    _, resp = authed_user(request)
    if resp:
        return resp
    r = ExecutionRound.objects.select_related("strategy").filter(id=rid).first()
    if not r:
        return fail_resp(40401, "执行轮次不存在")
    logs = [
        {"id": lg.id, "stage": lg.stage, "message": lg.message, "created_at": fmt_dt(lg.created_at)}
        for lg in r.logs.all().order_by("id")
    ]
    return json_resp(ok({"round": _round_payload(r), "logs": logs}))


def conclusion_view(request, rid):
    if request.method != "POST":
        return fail_resp(42201, "不支持的请求方法")
    user, resp = authed_user(request)
    if resp:
        return resp
    r = ExecutionRound.objects.select_related("strategy").filter(id=rid).first()
    if not r:
        return fail_resp(40401, "执行轮次不存在")
    if user.role != "tester":
        return fail_resp(40301, "仅测试人员可提交结论")
    body = parse_body(request)
    conclusion = body.get("conclusion")
    if conclusion not in ("pass", "fail"):
        return fail_resp(42201, "非法结论")
    # 防重：已有结论的轮次不可重复提交（初始 conclusion 为 None，对应前端 40902「结论已录入」处理）
    if r.conclusion is not None:
        return fail_resp(40902, "结论已录入，不可重复提交")
    r.conclusion = conclusion
    r.note = body.get("note", r.note or "")
    r.analysis_end_at = now()
    if r.conclusion == "pass" and r.strategy.push_mode == "normal":
        push_minutes = get_config("push_minutes", settings.PUSH_MINUTES)
        r.push_start_at = r.analysis_end_at
        r.push_end_at = r.analysis_end_at + timedelta(minutes=push_minutes)
        r.push_status = "pushed"
    else:
        r.push_start_at = r.push_end_at = None
        r.push_status = ""
    r.save()
    return json_resp(ok(_round_payload(r)))