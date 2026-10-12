import http from "@/api/http";
import type {
  ReportConclusion,
  ReportItem,
  ReportRevisionItem,
  ReportStatus
} from "@/api/types";

/** 报告表单：版本/策略为文本快照（无外键，发布后可改，结论发布后锁定） */
export interface ReportForm {
  title: string;
  version_name?: string | null;
  strategy_name?: string | null;
  conclusion: ReportConclusion;
  environment?: string;
  summary: string;
  risks?: string;
  remark?: string;
}

/** 报告列表查询（django-filter：status 精确 + 版本/策略包含 + 关键词） */
export interface ReportQuery {
  status?: ReportStatus;
  version_name?: string;
  strategy_name?: string;
  keyword?: string;
  /** 页码：携带后返回分页包装 { items, total, page, page_size }；不携带保持全量数组（后端向后兼容） */
  page?: number;
  /** 每页条数（后端上限 100） */
  page_size?: number;
}

/** 报告列表分页包装（携带 page 参数时的响应结构） */
export interface ReportPageData {
  items: ReportItem[];
  total: number;
  page: number;
  page_size: number;
}

/** 报告列表：支持按状态/版本/策略/关键词过滤；带 page 时返回分页包装 */
export function getReports(
  params: ReportQuery & { page: number }
): Promise<ReportPageData>;
export function getReports(params?: ReportQuery): Promise<ReportItem[]>;
export function getReports(
  params?: ReportQuery
): Promise<ReportItem[] | ReportPageData> {
  return http.get("/reports", { params });
}
export function getReport(id: number): Promise<ReportItem> {
  return http.get(`/reports/${id}`);
}
export function createReport(data: ReportForm): Promise<ReportItem> {
  return http.post("/reports", data);
}
export function updateReport(
  id: number,
  data: ReportForm
): Promise<ReportItem> {
  return http.put(`/reports/${id}`, data);
}
export function publishReport(
  id: number,
  screenshot: string
): Promise<ReportItem> {
  return http.post(`/reports/${id}/publish`, { screenshot });
}
/** 报告修改记录：按时间倒序（由近及远），含创建/修改/发布全留痕 */
export function getReportRevisions(id: number): Promise<ReportRevisionItem[]> {
  return http.get(`/reports/${id}/revisions`);
}
