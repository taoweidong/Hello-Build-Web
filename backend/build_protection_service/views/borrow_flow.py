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
    check_str_len,
    fail_resp,
    fetch_by_id,
    fmt_dt,
    json_resp,
    paginate_qs,
    parse_body,
    parse_int,
)

logger = logging.getLogger("build_protection_service")

# _payload 需访问的全部关联（R4-B14/B4-14）：单条响应路径（create/approve/
# reject/cancel）此前逐关联点查固定 N+1，列表路径已正确配置；抽公共 queryset
# 供两条路径复用（cancel 原 extra_queryset 内联写法收敛于此）。
_FLOW_SELECT_RELATED = (
    "strategy__branch__version",
    "strategy__template",
    "borrower",
    "approver",
    "target_branch__version",
)


def _flow_qs():
    """带 select_related 的 BorrowFlow queryset（列表与单条响应路径共用）。"""
    return BorrowFlow.objects.select_related(*_FLOW_SELECT_RELATED)


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
    # 回避规则（R5-B10 决策定案）：借用人与审批人不得为同一人，admin 亦不
    # 例外（对照 cancel 端点「仅本人」的审计取向）——电子流的核心价值即
    # 审批留痕的独立性，自借自批在审计报表中无法与正常审批区分；
    # 借用人想撤回申请应走 cancel 端点。
    if flow.borrower_id == user.id:
        return False
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
    qs = _flow_qs()
    if user.role != "admin":
        # 仅返回与本人相关的电子流：自己发起的 +（PM 时）由本人审批的，
        # 避免他人版本的申请理由与审批意见对任意登录用户全量可见（信息暴露）。
        visible = Q(borrower=user)
        if user.role == "pm":
            visible |= Q(strategy__branch__version__pm_user=user)
        qs = qs.filter(visible)
    if status:
        qs = qs.filter(status=status)
    # 可选分页（R4-B13/B4-13）：携带 page 参数返回 {items,total,page,page_size}
    # （page_size 默认 20 上限 100），不携带保持全量数组——与 reports 列表
    # 向后兼容口径一致（前端未改造前行为不变）。
    if request.GET.get("page"):
        return json_resp(ok(paginate_qs(qs, request, _payload)))
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
    # reason 是审批人要看的核心业务内容（TextField，非审计备注类字段）：
    # 超长 42201 拒绝而非静默截断（R6-B7，check_str_len 范式；500 为既定业务上限）
    reason = body_str(body, "reason")
    too_long = check_str_len(reason, "借用原因", 500)
    if too_long:
        return too_long
    if BorrowFlow.objects.filter(
        strategy=strategy, borrower=user, status="pending"
    ).exists():
        return fail_resp(CODE_ASSOCIATION, "该策略已有待审批的借用申请，请勿重复发起")
    try:
        # 并发重复发起兜底：uniq_pending_borrow_flow 部分唯一约束（DB 层）。
        # IntegrityError 按消息双格式匹配（R7-B5，对齐 strategies/slot_booking
        # 版 R4-B8/R5-B2）：SQLite 命名部分唯一索引消息含约束名 uniq_pending_
        # borrow_flow，字段组合（borrower_id+strategy_id）作兜底；非本约束的
        # IntegrityError（如校验后 create 前被并发删除的关联）原样抛出，
        # 不再误导为「重复申请」。
        with transaction.atomic():
            flow = BorrowFlow.objects.create(
                strategy=strategy,
                borrower=user,
                target_branch=target_branch,
                new_build_time=new_build_time,
                reason=reason,
            )
    except IntegrityError as exc:
        if "uniq_pending_borrow_flow" in str(exc) or (
            "borrower_id" in str(exc) and "strategy_id" in str(exc)
        ):
            return fail_resp(CODE_ASSOCIATION, "该策略已有待审批的借用申请，请勿重复发起")
        raise
    # 单条响应经 select_related 重取（R4-B14）：create 返回的实例无关联缓存，
    # 直接 _payload 会逐关联点查 6+ 次
    flow = _flow_qs().get(pk=flow.pk)
    return json_resp(ok(_payload(flow)))


def _handle_view(request, fid, approve: bool):
    # 方法守卫（R3-B16）：审批是写操作，仅 POST（此前 GET 也会执行审批产生副作用）
    if request.method != "POST":
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
    user, resp = authed_user(request)
    if resp:
        return resp
    fid = parse_int(fid)
    # select_related 取单条（R4-B14）：_can_approve 与审批分支需访问
    # strategy.branch.version / strategy.template 等关联
    flow = _flow_qs().filter(id=fid).first()
    if not flow:
        return fail_resp(CODE_NOT_FOUND, "借用电子流不存在")
    if flow.borrower_id == user.id:
        # 回避规则专用文案（R5-B10）：与「无审批权限」区分，指引走撤销
        return fail_resp(CODE_FORBIDDEN, "不可审批自己发起的借用申请，如需撤回请使用撤销")
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
            # 拼接名防御截断到 Strategy.name 上限 200（R4-B10/B4-10）：源策略名
            # (≤200) + 版本名 + "(借用)" 后缀可超限，SQLite 放行、迁 Postgres 即 500
            name = f"{flow.strategy.name}({flow.target_branch.version.name}借用)"[:200]
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
    # 单条响应经 select_related 重取（R4-B14）：替代 refresh_from_db——条件
    # UPDATE 已改写 approver_id/状态，重取一次即同时刷新标量与关联缓存，
    # 杜绝 _payload 逐关联点查与「approver 缓存陈旧」两类问题
    flow = _flow_qs().get(pk=flow.id)
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
    # select_related 清单收敛到 _flow_qs（R4-B14，原 cancel 独有的内联写法）
    flow, resp = fetch_by_id(
        BorrowFlow,
        fid,
        not_found="借用电子流不存在",
        extra_queryset=_flow_qs(),
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
    # 条件 UPDATE 改写了 status/cancelled_at，经 _flow_qs 重取一次即同时刷新
    # 标量与关联缓存（R4-B14 范式；R7-B5 前用 refresh_from_db 会清空关联缓存，
    # _payload 逐关联点查 5+ 次）
    flow = _flow_qs().get(pk=flow.id)
    logger.info("[borrow-flow] cancel id=%s actor=%s", flow.id, user.username)
    return json_resp(ok(_payload(flow)))
