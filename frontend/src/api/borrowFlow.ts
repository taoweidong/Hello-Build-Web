// 借用电子流 API 模块
// 契约：GET/POST /borrow-flows，POST /borrow-flows/:id/approve | reject | cancel
// 2026-10-20 页面精简：借用审批独立页下线，本模块仅服务全景域行内动作
// （发起借用弹窗 / 审批抽屉 / 复制文案），borrowFlowUrl 直达链接随之删除。
import http from "@/api/http";
import type { AxiosRequestConfig } from "axios";

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
  status: "pending" | "approved" | "rejected" | "cancelled";
  approver_name: string | null;
  handle_comment: string;
  handled_at: string | null;
  /** 借用人自行撤销的时刻（P2-R1；仅 status=cancelled 时有值） */
  cancelled_at: string | null;
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
/**
 * 借用电子流列表
 * @param config 请求级配置；轮询场景传 `{ silent: true }`
 */
export function listBorrowFlows(
  status?: BorrowFlowItem["status"],
  config?: AxiosRequestConfig
): Promise<BorrowFlowItem[]> {
  return http.get("/borrow-flows", {
    params: status ? { status } : {},
    ...config
  });
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

/** 撤销申请（P2-R1）：仅借用人本人 + 仅待审批可撤；撤销保留记录，同策略可立即重发 */
export function cancelBorrowFlow(id: number): Promise<BorrowFlowItem> {
  return http.post(`/borrow-flows/${id}/cancel`);
}
