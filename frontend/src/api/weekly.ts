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
    week_start?: string; // "YYYY-MM-DD" 须传该周周一（mondayOf）；后端把传入
    // 日期直接作周首日连排 7 天、不归一化，仅缺省时才取默认周一（R7-F15 注释修正）
    version_id?: number;
  },
  config?: AxiosRequestConfig
): Promise<WeeklyData> {
  return http.get("/weekly", { params, ...config });
}
