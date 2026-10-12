// 借用电子流复制文案组装（展示层逻辑；状态文案唯一来源为 views/constants）
// 原位于 api/borrowFlow.ts —— API 层不应持有展示文案（2026-10-12 质量优化第二轮）
import { borrowStatusMeta } from "@/views/constants";
import { formatTime } from "@/utils/business";
import type { BorrowFlowItem } from "@/api/borrowFlow";

/**
 * 电子流时间展示：后端 "%Y-%m-%dT%H:%M:%S" → "YYYY-MM-DD HH:mm:ss"。
 * 统一走 utils/business.formatTime（R3-F11，替代手写 .replace("T", " ")）；
 * 输出与原 replace 逐字节等价——合法时间串两者结果相同，空值/null 经守卫保持空串
 * （formatTime 直接吃空串会输出 "Invalid Date"，故必须先判空）。
 */
export function formatFlowTime(value: string | null | undefined): string {
  return value ? formatTime(value, "YYYY-MM-DD HH:mm:ss") : "";
}

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
