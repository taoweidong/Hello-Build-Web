// 策略配置 API 模块
// 契约基准：设计文档 7.2 strategies 接口
import http from "@/api/http";
import type { StrategyItem, Timeline, ConflictInfo } from "@/api/types";

/** 策略表单 */
export interface StrategyForm {
  branch_id: number;
  template_id: number;
  name: string;
  build_start_time: string;
  push_mode: string;
  enabled: boolean;
}

/** 预览结果：时间线 + 冲突检测 */
export interface PreviewResult {
  timeline: Timeline;
  conflict?: ConflictInfo | null;
}

/** 策略列表（含时间线计算结果） */
export function getStrategies(params?: {
  version_id?: number;
  branch_id?: number;
}): Promise<StrategyItem[]> {
  return http.get("/strategies", { params });
}

/** 保存前预览：时间线排布 + 冲突检测（不落库） */
export function previewStrategy(data: StrategyForm): Promise<PreviewResult> {
  return http.post("/strategies/preview", data);
}

/** 新建策略 */
export function createStrategy(data: StrategyForm): Promise<StrategyItem> {
  return http.post("/strategies", data);
}

/** 修改策略 */
export function updateStrategy(
  id: number,
  data: StrategyForm
): Promise<StrategyItem> {
  return http.patch(`/strategies/${id}`, data);
}

/** 启用/停用 */
export function toggleStrategy(
  id: number,
  enabled: boolean
): Promise<StrategyItem> {
  return http.patch(`/strategies/${id}/toggle`, null, { params: { enabled } });
}