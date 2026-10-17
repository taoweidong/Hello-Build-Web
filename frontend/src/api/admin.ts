// 系统管理 API 模块（前缀 /api/admin，写操作均写管理操作日志）
// 契约基准：设计文档 7.2 admin 接口
import http from "@/api/http";
import type { StrategyForm } from "@/api/strategy";
import type {
  VersionItem,
  VersionStatus,
  UserInfo,
  TemplateItem,
  GlobalConfig,
  Role,
  StrategyItem
} from "@/api/types";

/**
 * 模板时长变更联动告警条目（R5-B12）：update_template 在 smoke/analysis 时长
 * 变化时附带，标识引用该模板的启用策略与同分支其他启用策略新出现的阶段重叠对。
 * 仅告警不拦截（冲突处置走「先停用归档」逃生通道）。
 */
export interface TemplateDurationWarning {
  /** 重叠发生的分支名 */
  branch: string;
  /** 重叠策略对之一（按名称排序去重后的前者） */
  first: string;
  /** 重叠策略对之二 */
  second: string;
  /** 重叠区间起点 HH:MM */
  overlap_start: string;
  /** 重叠区间终点 HH:MM */
  overlap_end: string;
}

/** update_template 响应：模板本体 + 可选时长变更告警（未改时长时无 warnings 字段） */
export type TemplateUpdateResponse = TemplateItem & {
  warnings?: TemplateDurationWarning[];
};

export const adminApi = {
  // ---- 版本与分支 ----
  getVersions: (): Promise<VersionItem[]> => http.get("/admin/versions"),
  createVersion: (d: {
    name: string;
    pm_user_id?: number | null;
  }): Promise<VersionItem> => http.post("/admin/versions", d),
  updateVersion: (
    id: number,
    d: { name?: string; pm_user_id?: number | null; status?: VersionStatus }
  ): Promise<VersionItem> => http.patch(`/admin/versions/${id}`, d),
  addBranch: (vid: number, branchName: string): Promise<void> =>
    http.post(`/admin/versions/${vid}/branches`, { name: branchName }),

  // ---- 用户管理 ----
  getUsers: (): Promise<UserInfo[]> => http.get("/admin/users"),
  createUser: (d: {
    username: string;
    password: string;
    display_name?: string;
    role: Role;
  }): Promise<UserInfo> => http.post("/admin/users", d),
  updateUser: (
    id: number,
    d: {
      display_name?: string;
      role?: Role;
      is_active?: boolean;
      password?: string;
    }
  ): Promise<UserInfo> => http.patch(`/admin/users/${id}`, d),

  // ---- 策略模板 ----
  getTemplates: (): Promise<TemplateItem[]> => http.get("/admin/templates"),
  createTemplate: (d: {
    name: string;
    smoke_minutes: number;
    analysis_minutes: number;
    description?: string;
  }): Promise<TemplateItem> => http.post("/admin/templates", d),
  updateTemplate: (
    id: number,
    d: {
      name?: string;
      smoke_minutes?: number;
      analysis_minutes?: number;
      description?: string;
    }
  ): Promise<TemplateUpdateResponse> =>
    http.patch(`/admin/templates/${id}`, d),
  deleteTemplate: (id: number): Promise<void> =>
    http.delete(`/admin/templates/${id}`),

  // ---- 关键配置 ----
  getConfig: (): Promise<GlobalConfig> => http.get("/admin/config"),
  updateConfig: (d: GlobalConfig): Promise<GlobalConfig> =>
    http.put("/admin/config", d),

  // ---- 策略管理（管理员全量 CRUD，写入管理操作日志） ----
  getAdminStrategies: (params?: {
    version_id?: number;
    branch_id?: number;
  }): Promise<StrategyItem[]> => http.get("/admin/strategies", { params }),
  createAdminStrategy: (d: StrategyForm): Promise<StrategyItem> =>
    http.post("/admin/strategies", d),
  updateAdminStrategy: (id: number, d: StrategyForm): Promise<StrategyItem> =>
    http.patch(`/admin/strategies/${id}`, d),
  toggleAdminStrategy: (id: number): Promise<StrategyItem> =>
    http.patch(`/admin/strategies/${id}/toggle`),
  deleteAdminStrategy: (id: number): Promise<void> =>
    http.delete(`/admin/strategies/${id}`)
};
