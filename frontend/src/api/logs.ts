// 日志中心 API 模块
// 契约基准：设计文档 7.2 日志接口（/logs/execution、/logs/changes、/admin/logs/operations、/admin/logs/security）
import http from "@/api/http";
import type {
  ExecutionLogItem,
  ChangeLogItem,
  AdminOpLogItem,
  SecurityLogItem
} from "@/api/types";

export const logsApi = {
  /** 执行日志查询（PM 限本版本） */
  execution: (
    p: { date?: string; version_id?: number; branch_id?: number }
  ): Promise<ExecutionLogItem[]> =>
    http.get("/logs/execution", { params: p }),

  /** 策略变更日志（PM 限本版本） */
  changes: (p: { from?: string; to?: string }): Promise<ChangeLogItem[]> =>
    http.get("/logs/changes", { params: p }),

  /** 管理操作日志（仅管理员） */
  operations: (p: { from?: string; to?: string }): Promise<AdminOpLogItem[]> =>
    http.get("/admin/logs/operations", { params: p }),

  /** 登录安全日志（仅管理员） */
  security: (p: { from?: string; to?: string }): Promise<SecurityLogItem[]> =>
    http.get("/admin/logs/security", { params: p })
};