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

// ---- 借用电子流状态（BorrowFlow.status）----
export const borrowStatusMap: Record<string, TagMeta> = {
  pending: { text: "待审批", type: "warning" },
  approved: { text: "已通过", type: "success" },
  rejected: { text: "已驳回", type: "danger" }
};

export function borrowStatusMeta(code: string): TagMeta {
  return borrowStatusMap[code] || { text: code, type: "info" };
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
