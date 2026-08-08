// 业务共享工具：当前登录用户信息 + 时间解析
import dayjs from "dayjs";
import customParseFormat from "dayjs/plugin/customParseFormat";
import type { UserInfo } from "@/api/types";
import { businessUserKey } from "@/store/modules/user";

dayjs.extend(customParseFormat);

/** 获取当前登录用户信息（从业务存储读取，含绑定版本） */
export function getCurrentUser(): UserInfo | null {
  try {
    const raw = localStorage.getItem(businessUserKey);
    return raw ? (JSON.parse(raw) as UserInfo) : null;
  } catch {
    return null;
  }
}

/**
 * 解析后端绝对时间字符串为 Date。
 * 兼容 "YYYY-MM-DD HH:mm:ss" 与 ISO 格式，dayjs 解析失败时回退 new Date。
 */
export function parseTime(value: string | number | Date): Date {
  const str = String(value);
  const normalized = str.includes("T") ? str : str.replace(" ", "T");
  const d = dayjs(normalized);
  return d.isValid() ? d.toDate() : new Date(normalized);
}

/** 时间戳（毫秒） */
export function timeToMs(value: string | number | Date): number {
  return parseTime(value).getTime();
}

/** 格式化时间展示 */
export function formatTime(
  value: string | number | Date,
  fmt = "MM-DD HH:mm"
): string {
  return dayjs(parseTime(value)).format(fmt);
}

/** 计算某日期当天 00:00 对应的 Date */
export function dayStart(date: string | Date): Date {
  return dayjs(date).startOf("day").toDate();
}

/** 阶段状态徽标类型映射 */
export const stageStatusTypeMap: Record<string, string> = {
  pending: "info",
  running: "primary",
  success: "success",
  failed: "danger",
  skipped: "warning"
};

export { dayjs };