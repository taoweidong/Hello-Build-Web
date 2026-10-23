// 业务展示常量：结论/状态徽标映射（唯一来源，页面禁止再各自复制）
// 2026-10-20 页面精简：报告结论/状态、分支权限角色、实例状态、报告修订动作、
// 角色中文标签等映射随对应页面下线删除，仅保留全景域 + 策略配置页在用的映射。
import type { PushMode } from "@/api/types";

// ---- 时段抢占窗口 ----
/**
 * 后端未返回 horizon_days 时的默认可抢占窗口（天），与后端 RuntimeConfig 默认值一致。
 * 唯一来源（R4-F13/F-L4）：此前多页面各持一份，现一律 import 本常量，禁止再本地复制。
 */
export const DEFAULT_HORIZON_DAYS = 60;

export interface TagMeta {
  text: string;
  type: "success" | "danger" | "warning" | "info" | "primary";
}

// ---- 借用电子流状态（BorrowFlow.status）----
export const borrowStatusMap: Record<string, TagMeta> = {
  pending: { text: "待审批", type: "warning" },
  approved: { text: "已通过", type: "success" },
  rejected: { text: "已驳回", type: "danger" },
  cancelled: { text: "已撤销", type: "info" }
};

export function borrowStatusMeta(code: string): TagMeta {
  return borrowStatusMap[code] || { text: code, type: "info" };
}

// ---- 策略推送模式（Strategy.push_mode）----
export interface PushModeMeta {
  /** 短文案：详情/借用弹窗「推送模式」字段展示用 */
  label: string;
  /** 长文案：策略表单单选项展示用 */
  fullLabel: string;
}

export const pushModeMap: Record<PushMode, PushModeMeta> = {
  normal: { label: "正常流程", fullLabel: "正常流程推送" },
  sync: { label: "同步推送", fullLabel: "同步推送冒烟" }
};

/** 未知/缺失值原样兜底（空值返回空文案，不猜测语义） */
export function pushModeMeta(
  code: PushMode | string | null | undefined
): PushModeMeta {
  if (!code) return { label: "", fullLabel: "" };
  return pushModeMap[code as PushMode] ?? { label: code, fullLabel: code };
}

// ---- 时段状态（SlotBooking.status 与 CalendarDayCell.status 共用同一映射）----
// 过期不落库，无 expired 分支；available 仅存在于日历单元格（未抢占）
export const bookingStatusMap: Record<string, TagMeta> = {
  available: { text: "空闲", type: "info" },
  reserved: { text: "已抢占", type: "success" },
  released: { text: "已释放", type: "info" }
};

export function bookingStatusMeta(code: string): TagMeta {
  return bookingStatusMap[code] || { text: code, type: "info" };
}
