// 借用电子流复制文案组装（展示层逻辑；状态文案唯一来源为 views/constants）
// 原位于 api/borrowFlow.ts —— API 层不应持有展示文案（2026-10-12 质量优化第二轮）
import { borrowStatusMeta } from "@/views/constants";
import { formatDateTime } from "@/utils/business";
import type { BorrowFlowItem } from "@/api/borrowFlow";

// 电子流时间展示直连 utils/business.formatDateTime（R4-F7 唯一实现）；
// 原 formatFlowTime 别名导出已删除（R7-F11：借用域独立页下线后全仓无页面消费）
const formatFlowTime = formatDateTime;

/** 组装电子流纯文本（S5 时间轴「复制」入口，便于粘贴发给审核人员）；传入 detailUrl 时附带可直达该条的链接 */
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
  // 非待审批态按三态分支（R5-F2）：approved/rejected 拼审批人与意见，
  // cancelled 为借用人自行撤销、不存在审批动作，不拼审批人/意见
  if (flow.status === "approved" || flow.status === "rejected") {
    lines.push(
      `审批：${flow.approver_name || "-"} ${flow.status === "approved" ? "通过" : "驳回"}${
        flow.handle_comment ? `（${flow.handle_comment}）` : ""
      } ${formatFlowTime(flow.handled_at)}`
    );
  } else if (flow.status === "cancelled") {
    lines.push(`撤销：借用人撤销于 ${formatFlowTime(flow.cancelled_at)}`);
  }
  if (detailUrl) lines.push(`审批详情链接：${detailUrl}`);
  return lines.join("\n");
}
