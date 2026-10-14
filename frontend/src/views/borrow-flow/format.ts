// 借用电子流复制文案组装（展示层逻辑；状态文案唯一来源为 views/constants）
// 原位于 api/borrowFlow.ts —— API 层不应持有展示文案（2026-10-12 质量优化第二轮）
import { borrowStatusMeta } from "@/views/constants";
import { formatDateTime } from "@/utils/business";
import type { BorrowFlowItem } from "@/api/borrowFlow";

/**
 * 电子流时间展示：实现已上移 utils/business.formatDateTime（R4-F7 统一唯一实现，
 * 输出与原实现逐字节等价，等价性由 borrowFlow.spec 锁定）；此处保留别名导出，
 * 借用域页面继续按 formatFlowTime 语义调用。
 */
export const formatFlowTime = formatDateTime;

/** 组装电子流纯文本（审批页一键复制，便于粘贴发给审核人员）；传入 detailUrl 时附带可直达该条的链接 */
export function formatBorrowFlowText(
  flow: BorrowFlowItem,
  detailUrl?: string
): string {
  const lines = [
    `【借用电子流】#${flow.id} ${borrowStatusMeta(flow.status).text}`,
    `策略：${flow.strategy_name}（${flow.source_version_name}/${flow.source_branch_name} · ${flow.template_name}）`,
    `原构建时间：${flow.original_build_time}`,
    `借用人：${flow.borrower_name}`,
    `借用至：${flow.target_version_name}/${flow.target_branch_name}，新构建时间 ${flow.new_build_time}`,
    `借用原因：${flow.reason || "（未填写）"}`,
    `申请时间：${formatFlowTime(flow.created_at)}`
  ];
  if (flow.status !== "pending") {
    lines.push(
      `审批：${flow.approver_name || "-"} ${flow.status === "approved" ? "通过" : "驳回"}${
        flow.handle_comment ? `（${flow.handle_comment}）` : ""
      } ${formatFlowTime(flow.handled_at)}`
    );
  }
  if (detailUrl) lines.push(`审批详情链接：${detailUrl}`);
  return lines.join("\n");
}
