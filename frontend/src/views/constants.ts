// 业务展示常量：结论/状态徽标映射（唯一来源，页面禁止再各自复制）
import type { Role } from "@/api/types";

export interface TagMeta {
  text: string;
  type: "success" | "danger" | "warning" | "info" | "primary";
}

// ---- 执行轮次结论（RoundItem.conclusion）----
export const roundConclusionMap: Record<string, TagMeta> = {
  pass: { text: "通过", type: "success" },
  fail: { text: "不通过", type: "danger" },
  pending: { text: "待录", type: "info" }
};

export function roundConclusionMeta(code: string): TagMeta {
  return roundConclusionMap[code] || { text: code || "待录", type: "info" };
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

// ---- 推送状态（RoundItem.push_status）----
export const pushStatusMap: Record<string, TagMeta> = {
  pending: { text: "待推送", type: "info" },
  running: { text: "推送中", type: "primary" },
  success: { text: "成功", type: "success" },
  failed: { text: "失败", type: "danger" },
  skipped: { text: "跳过", type: "warning" }
};

export function pushStatusMeta(code: string): TagMeta {
  return pushStatusMap[code] || { text: code || "-", type: "info" };
}

// ---- 用户角色中文标签（User.ROLE_CHOICES）----
export const roleTextMap: Record<Role, string> = {
  admin: "管理员",
  pm: "版本负责人",
  builder: "构建人员",
  tester: "测试人员",
  integrator: "集成人员"
};
