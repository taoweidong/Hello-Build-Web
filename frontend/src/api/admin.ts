// 系统管理 API 模块（前缀 /api/admin，写操作均写管理操作日志）
// 契约基准：设计文档 7.2 admin 接口
import http from "@/api/http";
import type {
  VersionItem,
  UserInfo,
  TemplateItem,
  GlobalConfig
} from "@/api/types";

export const adminApi = {
  // ---- 版本与分支 ----
  getVersions: (): Promise<VersionItem[]> => http.get("/admin/versions"),
  createVersion: (d: { name: string; pm_user_id?: number | null }): Promise<VersionItem> =>
    http.post("/admin/versions", d),
  updateVersion: (id: number, d: { name?: string; pm_user_id?: number | null; status?: string }): Promise<VersionItem> =>
    http.patch(`/admin/versions/${id}`, d),
  addBranch: (vid: number, branchName: string): Promise<void> =>
    http.post(`/admin/versions/${vid}/branches`, null, {
      params: { branch_name: branchName }
    }),

  // ---- 用户管理 ----
  getUsers: (): Promise<UserInfo[]> => http.get("/admin/users"),
  createUser: (d: {
    username: string;
    password: string;
    display_name?: string;
    role: string;
  }): Promise<UserInfo> => http.post("/admin/users", d),
  updateUser: (
    id: number,
    d: {
      display_name?: string;
      role?: string;
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
  ): Promise<TemplateItem> => http.patch(`/admin/templates/${id}`, d),
  deleteTemplate: (id: number): Promise<void> =>
    http.delete(`/admin/templates/${id}`),

  // ---- 关键配置 ----
  getConfig: (): Promise<GlobalConfig> => http.get("/admin/config"),
  updateConfig: (d: GlobalConfig): Promise<GlobalConfig> =>
    http.put("/admin/config", d)
};