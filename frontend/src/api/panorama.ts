// 策略全景 API 模块（复用 strategies + executions 接口，不新增接口）
// 契约基准：设计文档 7.2
import http from "@/api/http";
import type { StrategyItem, RoundItem, ExecutionLogItem } from "@/api/types";

/** 策略列表（含时间线计算结果） */
export function getStrategies(params: {
  version_id?: number;
  branch_id?: number;
}): Promise<StrategyItem[]> {
  return http.get("/strategies", { params });
}

/** 执行历史（按策略/时间范围） */
export function getExecutions(params: {
  strategy_id?: number;
  from?: string;
  to?: string;
}): Promise<RoundItem[]> {
  return http.get("/executions", { params });
}

/** 轮次详情（各阶段实际起止 + 执行日志） */
export function getRoundDetail(
  roundId: number
): Promise<{
  round: RoundItem;
  logs: ExecutionLogItem[];
}> {
  return http.get(`/executions/rounds/${roundId}`);
}