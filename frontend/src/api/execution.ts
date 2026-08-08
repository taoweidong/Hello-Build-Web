// 今日执行 API 模块
// 契约基准：设计文档 7.2 execution 接口
import http from "@/api/http";
import type { RoundItem, ExecutionLogItem } from "@/api/types";

/** 执行看板/全景页：轮次列表（PM 仅本版本由后端过滤） */
export function getExecutions(params: {
  date?: string;
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

/** 录入结论（正常模式通过后触发推送；同步模式写 release_approved） */
export function submitConclusion(
  roundId: number,
  data: { conclusion: string; note?: string }
): Promise<RoundItem> {
  return http.post(`/executions/rounds/${roundId}/conclusion`, data);
}