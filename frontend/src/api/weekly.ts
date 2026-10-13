// 周视图 API 模块
// 契约基准：设计文档 7.2 GET /api/weekly?week_start=...&version_id=...
// 后端参数名为 week_start（实测 build_protection_service/views/weekly.py）
import http from "@/api/http";
import type { AxiosRequestConfig } from "axios";
import type { WeeklyData } from "@/api/types";

/**
 * 获取周视图数据
 * @param config 请求级配置；轮询场景传 `{ silent: true }` 避免后端故障时反复弹 toast
 */
export function getWeekly(
  params: {
    week_start?: string; // "YYYY-MM-DD"（该周任一天，后端取默认周一）
    version_id?: number;
  },
  config?: AxiosRequestConfig
): Promise<WeeklyData> {
  return http.get("/weekly", { params, ...config });
}
