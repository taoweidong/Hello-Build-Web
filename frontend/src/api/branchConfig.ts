// 分支配置 API 模块
// 契约：统一响应 { code, message, data }；写接口权限门槛由后端校验
import type { AxiosRequestConfig } from "axios";
import http from "@/api/http";
import type { Role } from "@/api/types";

/** 分支角色（与后端 BranchPermission.ROLE_CHOICES 一致） */
export type BranchRole = "VIEWER" | "OPERATOR" | "ADMIN";

/** 实例状态（与后端 Instance.STATUS_CHOICES 一致） */
export type InstanceStatus = "STARTING" | "RUNNING" | "STOPPED" | "ERROR";

export interface BranchItem {
  id: number;
  version_id: number;
  version_name: string;
  name: string;
  repository_url: string;
  description: string;
}

export interface ProjectItem {
  id: number;
  name: string;
  repository_url: string;
  description: string;
}

export interface StartupConfigItem {
  command: string;
  args: string[];
  env_vars: Record<string, string>;
  working_directory: string;
  timeout_seconds: number;
  auto_restart: boolean;
  raw_json: string;
  updated_at?: string;
}

export interface InstanceItem {
  id: number;
  status: InstanceStatus;
  pid: number | null;
  started_at: string | null;
  stopped_at: string | null;
  last_heartbeat_at: string | null;
  exit_code: number | null;
  log_tail: string;
}

export interface BranchProjectItem {
  id: number;
  enabled: boolean;
  project: ProjectItem;
  startup_config: StartupConfigItem | null;
  latest_instance: InstanceItem | null;
}

export interface PermissionItem {
  id: number;
  user_id: number;
  username: string;
  role: BranchRole;
}

export interface UserOption {
  id: number;
  username: string;
  display_name: string;
  role: Role;
}

/** 聚合配置响应：GET /branches/{id}/config */
export interface BranchConfigResponse {
  branch: BranchItem;
  branch_projects: BranchProjectItem[];
  permissions: PermissionItem[];
  my_role: BranchRole;
  available_users: UserOption[];
  available_projects: { id: number; name: string }[];
}

/** 实例轮询行：GET /branches/{id}/instances */
export interface InstanceRow {
  branch_project_id: number;
  project_id: number;
  project_name: string;
  instance: InstanceItem | null;
}

// ---- 分支 ----
export function getBranches(): Promise<BranchItem[]> {
  return http.get("/branches");
}
export function createBranch(data: {
  version_id: number;
  name: string;
  repository_url?: string;
  description?: string;
}): Promise<BranchItem> {
  return http.post("/branches", data);
}
export function deleteBranch(id: number): Promise<void> {
  return http.delete(`/branches/${id}`);
}
export function getBranchConfig(id: number): Promise<BranchConfigResponse> {
  return http.get(`/branches/${id}/config`);
}

// ---- 工程关联与启动参数 ----
export function addBranchProject(
  branchId: number,
  data: { project_id: number; enabled?: boolean }
): Promise<BranchProjectItem> {
  return http.post(`/branches/${branchId}/projects`, data);
}
export function removeBranchProject(bpId: number): Promise<void> {
  return http.delete(`/branch-projects/${bpId}`);
}
export function updateStartupConfig(
  bpId: number,
  data: Partial<Omit<StartupConfigItem, "raw_json" | "updated_at">>
): Promise<StartupConfigItem> {
  return http.put(`/branch-projects/${bpId}/config`, data);
}

// ---- 授权 ----
export function addBranchPermission(
  branchId: number,
  data: { user_id: number; role: BranchRole }
): Promise<PermissionItem> {
  return http.post(`/branches/${branchId}/permissions`, data);
}
export function removeBranchPermission(permId: number): Promise<void> {
  return http.delete(`/branch-permissions/${permId}`);
}
export function getUsersAll(): Promise<UserOption[]> {
  return http.get("/users/all");
}

// ---- 工程库 ----
export function getProjects(): Promise<ProjectItem[]> {
  return http.get("/projects");
}
export function createProject(data: {
  name: string;
  repository_url?: string;
  description?: string;
}): Promise<ProjectItem> {
  return http.post("/projects", data);
}

// ---- 实例 ----
export function getBranchInstances(
  branchId: number,
  config?: AxiosRequestConfig
): Promise<InstanceRow[]> {
  return http.get(`/branches/${branchId}/instances`, config);
}
export function startBranchProject(bpId: number): Promise<InstanceItem> {
  return http.post(`/branch-projects/${bpId}/start`);
}
export function stopBranchProject(bpId: number): Promise<InstanceItem | null> {
  return http.post(`/branch-projects/${bpId}/stop`);
}