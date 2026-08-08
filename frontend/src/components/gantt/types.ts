// 甘特组件共享常量与类型（供组件与页面复用）

/** 阶段颜色映射（设计文档/原型视觉语言） */
export const STAGE_COLORS: Record<string, string> = {
  build: "#3b82f6",
  smoke: "#8b5cf6",
  analysis: "#f59e0b",
  push: "#10b981"
};

/** 甘特单个色块 */
export interface GanttPhase {
  key: string;
  stage: string;
  start: string;
  end: string;
  conflict?: boolean;
  status?: string;
  statusLabel?: string;
}

/** 甘特行 */
export interface GanttRow {
  id: string;
  label: string;
  type: "group" | "strategy";
  phases: GanttPhase[];
}