// 借用电子流 → ScheduleEvent[] 的纯映射（可单测）
// 数据源：GET /api/borrow-flows?status=pending（后端已按「与我相关」过滤，前端不重算可见性）
//
// 关键口径（设计文档 §6-Q10）：BorrowFlow 不持久化执行日期，故事件锚在**发起日 created_at**，
// 卡片需显式提示「实际执行日取决于目标分支的新构建时间」——不得臆造日期字段。
import type { BorrowFlowItem } from "@/api/borrowFlow";
import type { UserInfo } from "@/api/types";
import { canApproveBorrowFlow } from "@/utils/business";
import { borrowStatusMeta } from "@/views/constants";
import type { ScheduleEvent } from "../types";

/** 当前登录用户（与 utils/business.getCurrentUser 返回一致） */
export type ScheduleUser = Pick<UserInfo, "role" | "bound_version_id"> & {
  id?: number;
};

export interface MapBorrowOptions {
  flows: BorrowFlowItem[];
  user: ScheduleUser | null;
  now?: Date;
}

/**
 * 借用电子流 → 事件（纯函数，仅渲染待审批，红点计数同源）
 *
 * 注意：借用流没有「过期」概念——未审批完的申请永远待办，故事件 `past` 恒为 false，
 * `MapBorrowOptions.now` 仅为与另两个 source 保持签名对称而保留。
 */
export function mapBorrowEvents(opts: MapBorrowOptions): ScheduleEvent[] {
  return opts.flows.map(flow => {
    const created = flow.created_at ?? "";
    const date = created.slice(0, 10);
    const time = created.slice(11, 16);
    const mine = !!opts.user?.id && flow.borrower_id === opts.user.id;
    const canApprove = canApproveBorrowFlow(opts.user, {
      source_version_id: flow.source_version_id
    });
    return {
      id: `borrow:${flow.id}`,
      source: "borrow" as const,
      kind: "borrow" as const,
      date,
      time,
      endTime: time,
      durationMin: 0,
      title: `${flow.borrower_name} 借用 ${flow.strategy_name}`,
      subtitle: `${flow.source_version_name} → ${flow.target_version_name}/${flow.target_branch_name} · 新构建 ${flow.new_build_time}`,
      branchId: flow.target_branch_id,
      branchName: flow.target_branch_name,
      versionId: flow.target_version_id,
      versionName: flow.target_version_name,
      // 状态徽标色走 el-tag 语义类型，不写死 hex
      color: "var(--el-color-warning)",
      status: flow.status,
      statusText: borrowStatusMeta(flow.status).text,
      past: false,
      mine,
      permissions: {
        canEdit: false,
        canBorrow: false,
        canOccupy: false,
        canRelease: false,
        canReleaseOthers: false,
        canApprove,
        // 撤销：仅借用人本人且仍待审批（与后端 borrow_flow_cancel_view 同口径）
        canCancel: mine && flow.status === "pending",
        canReschedule: false
      },
      raw: { type: "borrow" as const, data: flow }
    } satisfies ScheduleEvent;
  });
}

/** 待我审批数量（红点）：与 canApproveBorrowFlow 同口径 */
export function countPendingApproval(
  flows: BorrowFlowItem[],
  user: MapBorrowOptions["user"]
): number {
  return flows.filter(f =>
    canApproveBorrowFlow(user, { source_version_id: f.source_version_id })
  ).length;
}
