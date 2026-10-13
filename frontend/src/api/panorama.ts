// 调度全景聚合 API 模块（P2-R3）
// 契约：GET /panorama/todos → { code, message, data: PanoramaTodos }
//
// 与前端聚合（selectors.buildKpi）的分工：本接口给出**跨筛选仍然准确**的待办量，
// 页面用它展示「待我审批 / 我的有效抢占」；接口不可用时页面回退前端聚合（优雅降级）。
import http from "@/api/http";
import type { AxiosRequestConfig } from "axios";

/** 待办聚合计数 */
export interface PanoramaTodos {
  /** 待我审批的借用流数：admin 全量 / pm 仅自己绑定版本的策略 / 其余角色 0 */
  pending_approval: number;
  /** 我的有效抢占数（reserved 且未过期），不受页面筛选影响 */
  my_reserved_slots: number;
  /** 我发起且仍待审批的借用数 */
  my_pending_borrows: number;
}

/**
 * 获取待办聚合计数
 * @param config 请求级配置；轮询场景传 `{ silent: true }`
 */
export function getPanoramaTodos(
  config?: AxiosRequestConfig
): Promise<PanoramaTodos> {
  return http.get("/panorama/todos", config);
}
