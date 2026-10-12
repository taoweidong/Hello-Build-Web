// 调度全景域：provide / inject 上下文（数据中枢 + 动作总线）
// 5 个布局页面各自 provide 一次，shared/* 组件直接 inject，避免逐层透传 props。
import { inject, provide, type InjectionKey } from "vue";
import type { ScheduleActions } from "./useScheduleActions";
import type { ScheduleData } from "./types";

export interface PanoramaContext {
  data: ScheduleData;
  actions: ScheduleActions;
}

const PanoramaKey: InjectionKey<PanoramaContext> = Symbol("panorama-context");

export function providePanorama(ctx: PanoramaContext): void {
  provide(PanoramaKey, ctx);
}

export function usePanorama(): PanoramaContext {
  const ctx = inject(PanoramaKey);
  if (!ctx) {
    throw new Error("usePanorama 必须在 providePanorama 包裹的布局页内调用");
  }
  return ctx;
}
