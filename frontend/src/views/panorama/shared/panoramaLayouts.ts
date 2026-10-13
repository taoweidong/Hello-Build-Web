// 调度全景布局清单：与 asyncRoutes 的 /panorama/* 子路由一一对应
// 单独成文件（不放 <script setup>）：Vue 不允许在 script setup 里做 ES module 导出
import type { RouteLocationRaw } from "vue-router";
import { storageLocal } from "@pureadmin/utils";
import { panoramaLayoutKey } from "@/store/constants";

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

/** 合法布局 key 守卫（query/localStorage 都是不可信输入） */
export function isLayoutKey(value: unknown): value is PanoramaLayout["layout"] {
  return PANORAMA_LAYOUTS.some(l => l.layout === value);
}

/**
 * 读取 localStorage 中保存的布局偏好。
 * localStorage 是用户可改的不可信输入：@pureadmin/utils 的 getItem 会 JSON.parse，
 * 若值被手改/损坏为非 JSON，解析会抛错——直接卡死 /panorama 的 redirect。
 * 用 try/catch 兜住，返回合法 key 或 undefined（交给默认布局回落）。
 */
function readSavedLayout(): PanoramaLayout["layout"] | undefined {
  try {
    const raw = storageLocal().getItem(panoramaLayoutKey);
    return isLayoutKey(raw) ? raw : undefined;
  } catch {
    return undefined;
  }
}

/**
 * 入口落点解析，优先级：`?layout=` 深链 > localStorage 偏好 > 默认布局（月历）。
 * 供 `/panorama` 父路由 redirect 与 LayoutSwitcher 深链共用——
 * 优先级逻辑只实现一处，避免两处漂移。
 */
export function resolveEntryLayout(
  query: Record<string, unknown> = {},
  saved: unknown = readSavedLayout()
): PanoramaLayout["layout"] {
  if (isLayoutKey(query.layout)) return query.layout;
  if (isLayoutKey(saved)) return saved;
  return DEFAULT_LAYOUT;
}

/** 由路由路径反查布局 key，未命中回落默认布局 */
export function layoutOfPath(path: string): PanoramaLayout["layout"] {
  return PANORAMA_LAYOUTS.find(l => l.path === path)?.layout ?? DEFAULT_LAYOUT;
}
