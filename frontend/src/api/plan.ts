// 版本计划 API 模块
// 契约基准：设计文档 7.2 GET /api/plan?date=
// 甘特看板聚合：版本 → 分支 → 策略 → 各阶段时间区间 + 冲突标记
import http from "@/api/http";
import type { AxiosRequestConfig } from "axios";
import type { PushMode, Timeline } from "@/api/types";

/** 甘特看板策略行 */
export interface PlanStrategy {
  id: number;
  name: string;
  push_mode: PushMode;
  build_start_time: string;
  push_start_time?: string | null;
  enabled: boolean;
  timeline: Timeline;
  /** 是否冲突（红色斜纹高亮） */
  conflict?: boolean;
}

/** 甘特看板分支 */
export interface PlanBranch {
  branch_id: number;
  branch_name: string;
  strategies: PlanStrategy[];
}

/** 甘特看板版本分组 */
export interface PlanVersion {
  version_id: number;
  version_name: string;
  pm_name?: string;
  branches: PlanBranch[];
}

/**
 * 获取甘特看板聚合数据
 * @param config 请求级配置；轮询场景传 `{ silent: true }`
 */
// 后端 /plan 只消费 date（views/plan.py）：version_id/branch_id 曾在此声明
// 但后端从不读取，传入即被静默忽略（R7-F15 删除幽灵参数，版本/分支筛选由
// 消费方拿到全量后自行过滤）
export function getPlan(
  params: { date: string },
  config?: AxiosRequestConfig
): Promise<PlanVersion[]> {
  return http.get("/plan", { params, ...config });
}
