// 业务展示常量：结论/状态徽标映射（唯一来源，页面禁止再各自复制）
import type { PushMode, Role } from "@/api/types";

// ---- 时段抢占窗口 ----
/**
 * 后端未返回 horizon_days 时的默认可抢占窗口（天），与后端 RuntimeConfig 默认值一致。
 * 唯一来源（R4-F13/F-L4）：此前 useScheduleData 与 slot-booking 页各持一份并互相
 * 注释引用「口径一致」，两处一律 import 本常量，禁止再本地复制。
 */
export const DEFAULT_HORIZON_DAYS = 60;

export interface TagMeta {
  text: string;
  type: "success" | "danger" | "warning" | "info" | "primary";
}

// ---- 报告结论/状态（VerificationReport）----
export const reportConclusionMap: Record<string, TagMeta> = {
  pass: { text: "通过", type: "success" },
  fail: { text: "不通过", type: "danger" },
  risk: { text: "有风险", type: "warning" }
};

export function reportConclusionMeta(code: string): TagMeta {
  return reportConclusionMap[code] || { text: code, type: "info" };
}

export const reportStatusMap: Record<string, TagMeta> = {
  draft: { text: "草稿", type: "info" },
  published: { text: "已发布", type: "success" }
};

export function reportStatusMeta(code: string): TagMeta {
  return reportStatusMap[code] || { text: code, type: "info" };
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

/** 只要中文文案的场景（toast / 列表纯文本），避免调用方再写三元 */
export function slotStatusText(code: string): string {
  return bookingStatusMeta(code).text;
}

// ---- 分支权限角色（BranchPermission.role）----
export const branchRoleMap: Record<string, TagMeta> = {
  VIEWER: { text: "查看者", type: "info" },
  OPERATOR: { text: "操作者", type: "primary" },
  ADMIN: { text: "管理员", type: "warning" }
};

export function branchRoleMeta(code: string): TagMeta {
  return branchRoleMap[code] || { text: code, type: "info" };
}

// ---- 分支实例状态（Instance.status）----
export const instanceStatusMap: Record<string, TagMeta> = {
  STARTING: { text: "启动中", type: "primary" },
  RUNNING: { text: "运行中", type: "success" },
  STOPPED: { text: "已停止", type: "info" },
  ERROR: { text: "异常", type: "danger" }
};

export function instanceStatusMeta(code: string): TagMeta {
  return instanceStatusMap[code] || { text: code, type: "info" };
}

// ---- 报告修订动作 → tag 颜色（ReportRevisionLog.action）----
export const revisionTagTypeMap: Record<string, TagMeta["type"]> = {
  create: "info",
  update: "warning",
  publish: "success"
};

export function revisionTagType(action: string): TagMeta["type"] {
  return revisionTagTypeMap[action] || "info";
}

// ---- 用户角色中文标签（User.ROLE_CHOICES）----
export const roleTextMap: Record<Role, string> = {
  admin: "管理员",
  pm: "版本负责人",
  builder: "构建人员",
  tester: "测试人员",
  integrator: "集成人员"
};
