// 甘特阶段颜色共享常量（策略配置页时间线预览使用）
// 注：原 GanttPhase/GanttRow 类型与 GanttGanttastic 组件服务于已下线的
// 计划页/版本全景页，随死代码一并移除（2026-10-12 质量优化第二轮）。

/** 阶段颜色映射（设计文档/原型视觉语言） */
export const STAGE_COLORS: Record<string, string> = {
  build: "#3b82f6",
  smoke: "#8b5cf6",
  analysis: "#f59e0b",
  push: "#10b981"
};
