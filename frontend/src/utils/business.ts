// 业务共享工具：当前登录用户信息 + 时间解析
import dayjs from "dayjs";
import customParseFormat from "dayjs/plugin/customParseFormat";
import type { Role, UserInfo } from "@/api/types";
import { businessUserKey } from "@/store/constants";

dayjs.extend(customParseFormat);

/**
 * 版本策略全景页的编辑权限：内部维护人员（admin 全部版本、pm 仅绑定版本）
 * 可修改调度时间与信息；其余角色（builder/tester/integrator 等外部查看人员）只读。
 * 与后端策略写路径的角色门槛（views/strategies.py _check_pm_bound）保持一致。
 */
export function canEditPanorama(
  role: Role | undefined,
  boundVersionId: number | undefined,
  versionId: number | undefined
): boolean {
  if (!role || !versionId) return false;
  if (role === "admin") return true;
  if (role === "pm") return boundVersionId === versionId;
  return false;
}

/**
 * 判断某日某时刻（每日循环策略的一次排布）是否已早于当前时间——即已过期的历史任务。
 * dateStr "YYYY-MM-DD" + timeStr "HH:mm" 组合成本地时刻与 now 比较；无法解析时按未过期处理。
 */
export function isPastSlot(
  dateStr: string,
  timeStr: string,
  now: Date = new Date()
): boolean {
  const ts = parseTime(`${dateStr} ${timeStr}:00`).getTime();
  return Number.isNaN(ts) ? false : ts < now.getTime();
}

/**
 * 借用电子流审批权限：admin 全部；pm 仅来源版本为自己的电子流。
 * 与后端 views/borrow_flow._can_approve 同口径；从 borrow-flow 页抽出便于单测。
 */
export function canApproveBorrowFlow(
  user: Pick<UserInfo, "role" | "bound_version_id"> | null,
  flow: { source_version_id: number }
): boolean {
  if (user?.role === "admin") return true;
  return (
    user?.role === "pm" && user?.bound_version_id === flow.source_version_id
  );
}

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

/**
 * 后端秒级时间戳（"%Y-%m-%dT%H:%M:%S"）统一展示为 "YYYY-MM-DD HH:mm:ss"。
 * 唯一实现（R4-F7）：原 views/borrow-flow/format.formatFlowTime 上移至此，
 * 抢占记录/我的抢占/时段详情等 created_at 裸展示处一律改用本函数；
 * 空值先判空回退空串（formatTime 直接吃空串会输出 "Invalid Date"）。
 */
export function formatDateTime(value: string | null | undefined): string {
  return value ? formatTime(value, "YYYY-MM-DD HH:mm:ss") : "";
}

export { dayjs };
