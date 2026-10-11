// 业务展示常量：结论/状态徽标映射（唯一来源，页面禁止再各自复制）
import type { Role } from "@/api/types";

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

// ---- 用户角色中文标签（User.ROLE_CHOICES）----
export const roleTextMap: Record<Role, string> = {
  admin: "管理员",
  pm: "版本负责人",
  builder: "构建人员",
  tester: "测试人员",
  integrator: "集成人员"
};
