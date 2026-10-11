"""借用电子流 views：列表/发起/审批（通过/驳回）。

- 发起：任意登录用户；目标版本不能是被借用策略所属版本，不允许重复的待审批申请。
- 审批：仅被借用策略所属版本的 PM（或 admin）。
- 通过 = 在目标分支按新时间实际创建借用策略（复用 services.strategies.create_strategy
  统一校验：资源互斥/阶段冲突，冲突时电子流保持待审批并回传 40901/40902）。
"""
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
from . import authed_user, fail_resp, json_resp, parse_body, parse_int


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
        "handled_at": flow.handled_at.strftime("%Y-%m-%dT%H:%M:%S")
        if flow.handled_at
        else None,
        "created_at": flow.created_at.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _can_approve(user, flow: BorrowFlow) -> bool:
    if user.role == "admin":
        return True
    return user.role == "pm" and flow.strategy.branch.version.pm_user_id == user.id


def borrow_flow_list_view(request):
    """单视图双方法：GET 列表 / POST 发起借用申请。"""
    if request.method == "POST":
        return borrow_flow_create_view(request)
    user, resp = authed_user(request)
    if resp:
        return resp
    status = request.GET.get("status")
    qs = BorrowFlow.objects.select_related(
        "strategy__branch__version",
        "strategy__template",
        "borrower",
        "approver",
        "target_branch__version",
    )
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
    new_build_time = (body.get("new_build_time") or "").strip()
    if not valid_hhmm(new_build_time):
        return fail_resp(CODE_UNPROCESSABLE, "新构建时间格式应为 HH:MM")
    if BorrowFlow.objects.filter(
        strategy=strategy, borrower=user, status="pending"
    ).exists():
        return fail_resp(CODE_ASSOCIATION, "该策略已有待审批的借用申请，请勿重复发起")
    flow = BorrowFlow.objects.create(
        strategy=strategy,
        borrower=user,
        target_branch=target_branch,
        new_build_time=new_build_time,
        reason=(body.get("reason") or "").strip()[:500],
    )
    return json_resp(ok(_payload(flow)))


def _handle_view(request, fid, approve: bool):
    user, resp = authed_user(request)
    if resp:
        return resp
    flow = BorrowFlow.objects.filter(id=parse_int(fid)).first()
    if not flow:
        return fail_resp(CODE_NOT_FOUND, "借用电子流不存在")
    if flow.status != "pending":
        return fail_resp(CODE_ASSOCIATION, "该电子流已处理，请勿重复操作")
    if not _can_approve(user, flow):
        return fail_resp(CODE_FORBIDDEN, "仅被借用策略所属版本负责人或管理员可审批")
    body = parse_body(request)
    comment = (body.get("comment") or "").strip()[:255]
    if not approve and not comment:
        return fail_resp(CODE_UNPROCESSABLE, "驳回时必须填写审批意见")

    if approve:
        # 通过 = 在目标分支按新时间实际创建借用策略（复用共用写路径，统一互斥/阶段冲突校验）
        template = StrategyTemplate.objects.filter(
            id=flow.strategy.template_id
        ).first()
        if not template:
            return fail_resp(CODE_NOT_FOUND, "策略模板不存在")
        name = f"{flow.strategy.name}({flow.target_branch.version.name}借用)"
        try:
            svc_create(
                flow.target_branch,
                template,
                user,
                name=name,
                build_start_time=flow.new_build_time,
                push_mode="normal",
            )
        except StrategyValidationError as exc:
            # 校验不过（资源互斥/阶段冲突）→ 电子流保持待审批，回传统一错误码
            return json_resp(
                err(exc.code, f"审批通过失败：{exc.message}", exc.extra),
                status=CODE_STATUS.get(exc.code, 422),
            )
    flow.status = "approved" if approve else "rejected"
    flow.approver = user
    flow.handle_comment = comment
    flow.handled_at = timezone.now()
    flow.save(update_fields=["status", "approver", "handle_comment", "handled_at"])
    return json_resp(ok(_payload(flow)))


def borrow_flow_approve_view(request, fid):
    return _handle_view(request, fid, approve=True)


def borrow_flow_reject_view(request, fid):
    return _handle_view(request, fid, approve=False)
