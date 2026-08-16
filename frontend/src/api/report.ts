// 验证报告 API 模块
import http from "@/api/http";
import type { ReportItem } from "@/api/types";

/** 报告表单 */
export interface ReportForm {
  title: string;
  version_id?: number | null;
  strategy_id?: number | null;
  conclusion: string;
  environment?: string;
  summary: string;
  risks?: string;
  remark?: string;
}

/** 报告列表查询 */
export interface ReportQuery {
  status?: string;
  version_id?: number;
  strategy_id?: number;
  keyword?: string;
}

export function getReports(params?: ReportQuery): Promise<ReportItem[]> {
  return http.get("/reports", { params });
}
export function getReport(id: number): Promise<ReportItem> {
  return http.get(`/reports/${id}`);
}
export function createReport(data: ReportForm): Promise<ReportItem> {
  return http.post("/reports", data);
}
export function updateReport(id: number, data: ReportForm): Promise<ReportItem> {
  return http.put(`/reports/${id}`, data);
}
export function publishReport(id: number, screenshot: string): Promise<ReportItem> {
  return http.post(`/reports/${id}/publish`, { screenshot });
}
export function deprecateReport(id: number, reason: string): Promise<ReportItem> {
  return http.post(`/reports/${id}/deprecate`, { reason });
}