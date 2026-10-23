"""调度全景聚合视图（P2-R3）：把「跨筛选仍然准确」的待办计数一次性返回。

为什么需要它：前端聚合（`selectors.buildKpi`）只统计**当前视图已加载的事件**，
因此「待我审批」会随版本/分支/范围筛选跳动；而待办数在语义上是全局量，
必须由服务端给出。页面在接口不可用时回退前端聚合（优雅降级）。

口径（与既有权限规则同源，勿在此另立一套）：
- `pending_approval`：待「我」审批的借用流数。admin 全量；pm 为其绑定版本所属策略
  的申请；其余角色 0。判定与 `views/borrow_flow._can_approve` 一致，并按 R5-B10
  回避规则排除借用人是本人的单（R6-B8：自借单只能由本人撤回，计入待办只会产生
  不可操作的假待办）。
- `my_reserved_slots`：我的仍有效抢占（status=reserved 且 date >= 今天），不受页面筛选影响。
- `my_pending_borrows`：我发起且仍待审批的申请数。

设计取舍（对应设计文档 §6-Q6）：**冲突数不在此返回**——跨源重合依赖「当前视图已加载的
事件范围」（S1 告警 / S5 徽标都基于已渲染事件），服务端全量口径必然与页面显示不一致，
仍由前端 `selectors.detectCrossSourceConflicts` 聚合。
"""
from django.utils import timezone

from ..api import ok
from ..errors import CODE_UNPROCESSABLE
from ..models import BorrowFlow, SlotBooking
from . import authed_user, fail_resp, json_resp


def todos_view(request):
    """GET /api/panorama/todos（读端点仅 GET，R3-B16）。"""
    if request.method != "GET":
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
    user, resp = authed_user(request)
    if resp:
        return resp

    pending = BorrowFlow.objects.filter(status="pending").exclude(borrower=user)
    if user.role == "admin":
        # 排除自借单（R6-B8）：回避规则（R5-B10）下本人发起的申请自己永远
        # 无法审批，计入待办只会产生不可操作的假待办
        pending_approval = pending.count()
    elif user.role == "pm":
        pending_approval = pending.filter(
            strategy__branch__version__pm_user=user
        ).count()
    else:
        # 非 admin/pm 无审批权，待办恒为 0（与前端 canApproveBorrowFlow 同口径）
        pending_approval = 0

    today = timezone.localdate()
    return json_resp(
        ok(
            {
                "pending_approval": pending_approval,
                "my_reserved_slots": SlotBooking.objects.filter(
                    user=user, status="reserved", date__gte=today
                ).count(),
                "my_pending_borrows": BorrowFlow.objects.filter(
                    borrower=user, status="pending"
                ).count(),
            }
        )
    )
