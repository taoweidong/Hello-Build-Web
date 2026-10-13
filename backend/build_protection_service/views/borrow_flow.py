"""借用电子流 views：列表/发起/审批（通过/驳回）。

- 发起：任意登录用户；目标版本不能是被借用策略所属版本，不允许重复的待审批申请。
- 审批：仅被借用策略所属版本的 PM（或 admin）。
- 通过 = 在目标分支按新时间实际创建借用策略（复用 services.strategies.create_strategy
  统一校验：资源互斥/阶段冲突，  冲突时电子流保持待审批并回传 40901/40902）。
"""
import logging

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from ..api import err, ok
from ..errors import (
    CODE_ASSOCIATION,
    CODE_FORBIDDEN,
    CODE_NOT_FOUND,
    CODE_STATUS,
    CODE_UNPROCESSABLE,
)
from ..models import BorrowFlow, Branch, Strategy, StrategyTemplate
from ..services.strategies import (
    StrategyValidationError,
    create_strategy as svc_create,
    valid_hhmm,
)
from . import (
    authed_user,
    body_str,
    fail_resp,
    fetch_by_id,
    fmt_dt,
    json_resp,
    parse_body,
    parse_int,
)

logger = logging.getLogger("build_protection_service")


def _payload(flow: BorrowFlow) -> dict:
    strategy = flow.strategy
    branch = strategy.branch
    target_version = flow.target_branch.version
    return {
        "id": flow.id,
        "strategy_id": strategy.id,
        "strategy_name": strategy.name,
        "source_version_id": branch.version_id,
        "source_version_name": branch.version.name,
        "source_branch_id": branch.id,
        "source_branch_name": branch.name,
        "template_name": strategy.template.name,
        "original_build_time": strategy.build_start_time,
        "borrower_id": flow.borrower_id,
        "borrower_name": flow.borrower.display_name or flow.borrower.username,
        "target_version_id": target_version.id,
        "target_version_name": target_version.name,
        "target_branch_id": flow.target_branch_id,
        "target_branch_name": flow.target_branch.name,
        "new_build_time": flow.new_build_time,
        "reason": flow.reason,
        "status": flow.status,
        "approver_name": (flow.approver.display_name or flow.approver.username)
        if flow.approver
        else None,
        "handle_comment": flow.handle_comment,
        # 时间序列化统一走 fmt_dt（Asia/Shanghai 墙钟，R3-B3）：
        # 此前手工 strftime 输出 UTC 墙钟，前端早 8 小时展示（B-P1-3）。
        "handled_at": fmt_dt(flow.handled_at),
        "cancelled_at": fmt_dt(flow.cancelled_at),
        "created_at": fmt_dt(flow.created_at),
    }


def _can_approve(user, flow: BorrowFlow) -> bool:
    if user.role == "admin":
        return True
    return user.role == "pm" and flow.strategy.branch.version.pm_user_id == user.id


def borrow_flow_list_view(request):
    """单视图双方法：GET 列表 / POST 发起借用申请；其余方法 42201（R3-B16）。"""
    if request.method == "POST":
        return borrow_flow_create_view(request)
    if request.method != "GET":
        # 此前 DELETE/PUT 等会被当作列表请求执行（读端点无方法守卫，B-P3-5）
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
    user, resp = authed_user(request)
    if resp:
        return resp
    status = request.GET.get("status")
    if status and status not in ("pending", "approved", "rejected", "cancelled"):
        return fail_resp(
            CODE_UNPROCESSABLE, "status 应为 pending/approved/rejected/cancelled"
        )
    qs = BorrowFlow.objects.select_related(
        "strategy__branch__version",
        "strategy__template",
        "borrower",
        "approver",
        "target_branch__version",
    )
    if user.role != "admin":
        # 仅返回与本人相关的电子流：自己发起的 +（PM 时）由本人审批的，
        # 避免他人版本的申请理由与审批意见对任意登录用户全量可见（信息暴露）。
        visible = Q(borrower=user)
        if user.role == "pm":
            visible |= Q(strategy__branch__version__pm_user=user)
        qs = qs.filter(visible)
    if status:
        qs = qs.filter(status=status)
    return json_resp(ok([_payload(f) for f in qs]))


def borrow_flow_create_view(request):
    user, resp = authed_user(request)
    if resp:
        return resp
    body = parse_body(request)
    strategy = Strategy.objects.filter(
        id=parse_int(body.get("strategy_id"))
    ).first()
    if not strategy:
        return fail_resp(CODE_NOT_FOUND, "被借用策略不存在")
    target_branch = Branch.objects.filter(
        id=parse_int(body.get("target_branch_id"))
    ).first()
    if not target_branch:
        return fail_resp(CODE_UNPROCESSABLE, "目标分支不存在")
    if target_branch.version_id == strategy.branch.version_id:
        return fail_resp(CODE_UNPROCESSABLE, "目标版本不能是被借用策略所属版本")
    # 类型守卫（R3-B2）：非字符串归一为 ""，走既有格式校验 42201，杜绝 .strip() 500
    new_build_time = body_str(body, "new_build_time")
    if not valid_hhmm(new_build_time):
        return fail_resp(CODE_UNPROCESSABLE, "新构建时间格式应为 HH:MM")
    if BorrowFlow.objects.filter(
        strategy=strategy, borrower=user, status="pending"
    ).exists():
        return fail_resp(CODE_ASSOCIATION, "该策略已有待审批的借用申请，请勿重复发起")
    try:
        # 并发重复发起兜底：uniq_pending_borrow_flow 部分唯一约束（DB 层）
        with transaction.atomic():
            flow = BorrowFlow.objects.create(
                strategy=strategy,
                borrower=user,
                target_branch=target_branch,
                new_build_time=new_build_time,
                reason=body_str(body, "reason", max_len=500),
            )
    except IntegrityError:
        return fail_resp(CODE_ASSOCIATION, "该策略已有待审批的借用申请，请勿重复发起")
    return json_resp(ok(_payload(flow)))


def _handle_view(request, fid, approve: bool):
    # 方法守卫（R3-B16）：审批是写操作，仅 POST（此前 GET 也会执行审批产生副作用）
    if request.method != "POST":
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
    user, resp = authed_user(request)
    if resp:
        return resp
    fid = parse_int(fid)
    flow = BorrowFlow.objects.filter(id=fid).first()
    if not flow:
        return fail_resp(CODE_NOT_FOUND, "借用电子流不存在")
    if not _can_approve(user, flow):
        return fail_resp(CODE_FORBIDDEN, "仅被借用策略所属版本负责人或管理员可审批")
    body = parse_body(request)
    # 类型守卫（R3-B2）：非字符串归一为 ""，驳回时走"必须填写审批意见" 42201
    comment = body_str(body, "comment", max_len=255)
    if not approve and not comment:
        return fail_resp(CODE_UNPROCESSABLE, "驳回时必须填写审批意见")

    new_status = "approved" if approve else "rejected"
    # 事务 + 乐观锁：条件更新抢占 pending 状态，杜绝并发双审批/双处理；
    # 审批通过建策略失败时整体回滚，电子流保持待审批。
    with transaction.atomic():
        claimed = BorrowFlow.objects.filter(id=fid, status="pending").update(
            status=new_status,
            approver=user,
            handle_comment=comment,
            handled_at=timezone.now(),
        )
        if not claimed:
            return fail_resp(CODE_ASSOCIATION, "该电子流已处理，请勿重复操作")
        if approve:
            template = StrategyTemplate.objects.filter(
                id=flow.strategy.template_id
            ).first()
            if not template:
                transaction.set_rollback(True)
                return fail_resp(CODE_NOT_FOUND, "策略模板不存在")
            name = f"{flow.strategy.name}({flow.target_branch.version.name}借用)"
            try:
                # 推送配置从源策略复制（R3-B15）：此前固定 push_mode="normal" 且
                # 丢弃 push_start_time，sync/固定推送策略被借用后推送配置丢失（B-P3-4）。
                svc_create(
                    flow.target_branch,
                    template,
                    user,
                    name=name,
                    build_start_time=flow.new_build_time,
                    push_start_time=flow.strategy.push_start_time,
                    push_mode=flow.strategy.push_mode,
                )
            except StrategyValidationError as exc:
                # 校验不过（资源互斥/阶段冲突）→ 回滚抢占（保持待审批），回传统一错误码
                transaction.set_rollback(True)
                return json_resp(
                    err(exc.code, f"审批通过失败：{exc.message}", exc.extra),
                    status=CODE_STATUS.get(exc.code, 422),
                )
    flow.refresh_from_db()
    return json_resp(ok(_payload(flow)))


def borrow_flow_approve_view(request, fid):
    return _handle_view(request, fid, approve=True)


def borrow_flow_reject_view(request, fid):
    return _handle_view(request, fid, approve=False)


def borrow_flow_cancel_view(request, fid):
    """借用人撤销待审批申请（P2-R1）。

    权限：仅借用人本人（admin 亦不例外——撤销是「撤回自己的申请」，不是管理动作），
    他人调用 40301。状态：仅 pending 可撤，已审批/已撤销返回 40903。
    撤销不删记录（保留审计）；因 uniq_pending_borrow_flow 只约束 pending，
    撤销后同策略可立即重新发起。
    """
    # 方法守卫（R3-B16）：写端点仅 POST
    if request.method != "POST":
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
    user, resp = authed_user(request)
    if resp:
        return resp
    flow, resp = fetch_by_id(
        BorrowFlow,
        fid,
        not_found="借用电子流不存在",
        extra_queryset=BorrowFlow.objects.select_related(
            "strategy__branch__version",
            "strategy__template",
            "borrower",
            "approver",
            "target_branch__version",
        ),
    )
    if resp:
        return resp
    if flow.borrower_id != user.id:
        return fail_resp(CODE_FORBIDDEN, "仅借用人本人可撤销该申请")
    # 条件 UPDATE 抢占（对齐审批/释放范式）：并发下「审批 vs 撤销」只有一方能改状态
    cancelled = BorrowFlow.objects.filter(
        id=flow.id, borrower=user, status="pending"
    ).update(status="cancelled", cancelled_at=timezone.now())
    if not cancelled:
        return fail_resp(CODE_ASSOCIATION, "该电子流已处理，无法撤销")
    flow.refresh_from_db()
    logger.info("[borrow-flow] cancel id=%s actor=%s", flow.id, user.username)
    return json_resp(ok(_payload(flow)))
