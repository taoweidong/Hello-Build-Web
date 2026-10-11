// 借用电子流 API 模块
// 契约：GET/POST /borrow-flows，POST /borrow-flows/:id/approve | reject
import http from "@/api/http";

/** 借用电子流条目 */
export interface BorrowFlowItem {
  id: number;
  strategy_id: number;
  strategy_name: string;
  source_version_id: number;
  source_version_name: string;
  source_branch_id: number;
  source_branch_name: string;
  template_name: string;
  original_build_time: string;
  borrower_id: number;
  borrower_name: string;
  target_version_id: number;
  target_version_name: string;
  target_branch_id: number;
  target_branch_name: string;
  new_build_time: string;
  reason: string;
  status: "pending" | "approved" | "rejected";
  approver_name: string | null;
  handle_comment: string;
  handled_at: string | null;
  created_at: string;
}

/** 发起借用申请表单 */
export interface BorrowFlowForm {
  strategy_id: number;
  target_branch_id: number;
  new_build_time: string;
  reason?: string;
}

/** 借用电子流列表（可按状态过滤） */
export function listBorrowFlows(
  status?: BorrowFlowItem["status"]
): Promise<BorrowFlowItem[]> {
  return http.get("/borrow-flows", { params: status ? { status } : {} });
}

/** 发起借用申请（任意登录用户） */
export function createBorrowFlow(
  data: BorrowFlowForm
): Promise<BorrowFlowItem> {
  return http.post("/borrow-flows", data);
}

/** 审批通过（仅来源版本负责人/管理员；通过即在目标分支实际创建借用策略） */
export function approveBorrowFlow(id: number): Promise<BorrowFlowItem> {
  return http.post(`/borrow-flows/${id}/approve`);
}

/** 审批驳回（须填写审批意见） */
export function rejectBorrowFlow(
  id: number,
  comment: string
): Promise<BorrowFlowItem> {
  return http.post(`/borrow-flows/${id}/reject`, { comment });
}

/** 借用电子流审批页的直达链接（hash 路由，携带 focus 参数定位并打开该条） */
export function borrowFlowUrl(id: number): string {
  if (typeof window === "undefined") return `#/borrow-flow/index?focus=${id}`;
  const { origin, pathname } = window.location;
  return `${origin}${pathname}#/borrow-flow/index?focus=${id}`;
}

