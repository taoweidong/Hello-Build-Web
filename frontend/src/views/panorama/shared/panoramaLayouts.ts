// 调度全景布局清单：与 asyncRoutes 的 /panorama/* 子路由一一对应
// 单独成文件（不放 <script setup>）：Vue 不允许在 script setup 里做 ES module 导出
import type { RouteLocationRaw } from "vue-router";

export interface PanoramaLayout {
  layout: "dashboard" | "gantt" | "month" | "board" | "timeline";
  path: RouteLocationRaw;
  title: string;
}

export const PANORAMA_LAYOUTS: readonly PanoramaLayout[] = [
  { layout: "dashboard", path: "/panorama/dashboard", title: "态势大屏" },
  { layout: "gantt", path: "/panorama/gantt", title: "时空甘特" },
  { layout: "month", path: "/panorama/month", title: "月历矩阵" },
  { layout: "board", path: "/panorama/board", title: "分组看板" },
  { layout: "timeline", path: "/panorama/timeline", title: "时间轴流水" }
] as const;

/** 默认落点：月历矩阵（抢占主战场，与父路由 redirect 一致） */
export const DEFAULT_LAYOUT = "month";

/** 由路由路径反查布局 key，未命中回落默认布局 */
export function layoutOfPath(path: string): PanoramaLayout["layout"] {
  return PANORAMA_LAYOUTS.find(l => l.path === path)?.layout ?? DEFAULT_LAYOUT;
}
