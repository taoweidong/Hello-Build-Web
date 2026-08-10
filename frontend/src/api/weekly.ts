// 周视图 API 模块
// 契约基准：设计文档 7.2 GET /api/weekly?week_start=...&version_id=...
// 后端参数名为 week_start（实测 build_protection_service/views/weekly.py）
import http from "@/api/http";
import type { WeeklyData } from "@/api/types";

/** 获取周视图数据 */
export function getWeekly(params: {
  week_start?: string; // "YYYY-MM-DD"（该周任一天，后端取默认周一）
  version_id?: number;
}): Promise<WeeklyData> {
  return http.get("/weekly", { params });
}