"""执行轮次 views：列表/详情/测试结论提交。"""
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.timezone import now

from ..api import ok
from ..models import ExecutionRound
from ..services.config import get_config
from . import authed_user, body_str, fail_resp, fmt_dt, json_resp, parse_body, parse_int
from ..errors import CODE_DUPLICATE, CODE_FORBIDDEN, CODE_NOT_FOUND, CODE_UNPROCESSABLE


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
    # 方法守卫（R3-B16）：读端点仅 GET
    if request.method != "GET":
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
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
            return fail_resp(CODE_UNPROCESSABLE, "strategy_id 应为整数")
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
        return fail_resp(CODE_UNPROCESSABLE, "日期筛选格式非法，应为 YYYY-MM-DD")
    return json_resp(ok([_round_payload(r) for r in qs[:200]]))


def _round_or_denied(user, rid):
    """按 id 取执行轮次并做 PM 版本隔离（与列表端点同口径，堵住枚举 rid 越权读取）。

    返回 (round, err_response)：不存在 → 40401；PM 访问他版轮次 → 40301。
    """
    r = ExecutionRound.objects.select_related(
        "strategy", "strategy__branch", "strategy__branch__version"
    ).filter(id=rid).first()
    if not r:
        return None, fail_resp(CODE_NOT_FOUND, "执行轮次不存在")
    if user.role == "pm" and r.strategy.branch.version.pm_user_id != user.id:
        return None, fail_resp(CODE_FORBIDDEN, "仅可查看本版本执行轮次")
    return r, None


def round_detail(request, rid):
    # 方法守卫（R3-B16）：读端点仅 GET
    if request.method != "GET":
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
    user, resp = authed_user(request)
    if resp:
        return resp
    r, denied = _round_or_denied(user, rid)
    if denied:
        return denied
    logs = [
        {"id": lg.id, "stage": lg.stage, "message": lg.message, "created_at": fmt_dt(lg.created_at)}
        for lg in r.logs.all().order_by("id")
    ]
    return json_resp(ok({"round": _round_payload(r), "logs": logs}))


def conclusion_view(request, rid):
    if request.method != "POST":
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
    user, resp = authed_user(request)
    if resp:
        return resp
    r, denied = _round_or_denied(user, rid)
    if denied:
        return denied
    if user.role != "tester":
        return fail_resp(CODE_FORBIDDEN, "仅测试人员可提交结论")
    body = parse_body(request)
    conclusion = body.get("conclusion")
    if conclusion not in ("pass", "fail"):
        return fail_resp(CODE_UNPROCESSABLE, "非法结论")
    # 防重：已有结论的轮次不可重复提交（初始 conclusion 为 None，对应前端 40902「结论已录入」处理）
    if r.conclusion is not None:
        return fail_resp(CODE_DUPLICATE, "结论已录入，不可重复提交")
    analysis_end = now()
    fields = {
        "conclusion": conclusion,
        # note 统一走 body_str（R4-B4/B4-04，全项目字符串提取"一律 body_str"的
        # 最后一处漏网）：传对象/数字此前直进 update(**fields)，对象存成
        # "{'a': 1}" 垃圾数据、非 str 撞 NOT NULL 冒 500；非 str 回退原值，
        # 超长截断到 max_length=255（审计备注类字段，口径同 security_log R3-B12）
        "note": body_str(body, "note", default=r.note or "", max_len=255),
        "analysis_end_at": analysis_end,
    }
    if conclusion == "pass" and r.strategy.push_mode == "normal":
        push_minutes = get_config("push_minutes", settings.PUSH_MINUTES)
        fields.update(
            push_start_at=analysis_end,
            push_end_at=analysis_end + timedelta(minutes=push_minutes),
            push_status="pushed",
        )
    else:
        fields.update(push_start_at=None, push_end_at=None, push_status="")
    # 原子抢占：单条 UPDATE 仅在 conclusion 仍为 NULL 时写入（对齐 borrow_flow 审批
    # 范式），并发双提交后到者更新 0 行 → 40902，消除 check-then-act 竞态。
    updated = ExecutionRound.objects.filter(id=rid, conclusion__isnull=True).update(**fields)
    if not updated:
        return fail_resp(CODE_DUPLICATE, "结论已录入，不可重复提交")
    r.refresh_from_db()
    return json_resp(ok(_round_payload(r)))