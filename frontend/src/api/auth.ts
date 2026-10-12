// 认证 API 模块
// 契约基准：设计文档 7.2 认证接口
import type { AxiosRequestConfig } from "axios";
import http from "@/api/http";
import type { LoginResult, UserInfo } from "@/api/types";

/** 登录：返回 JWT + 用户信息（写安全日志） */
export function loginApi(data: {
  username: string;
  password: string;
}): Promise<LoginResult> {
  return http.post("/auth/login", data);
}

/** 登出：当前 token 写入后端黑名单即时失效 + 写安全日志。
 * silent：登出失败无需打扰用户（本地清理照常进行）。 */
export function logoutApi(): Promise<void> {
  return http.post("/auth/logout", null, { silent: true });
}

/** 当前用户信息（含权限元数据）；启动静默刷新等场景可传 { silent: true } 失败不弹 toast */
export function getMe(config?: AxiosRequestConfig): Promise<UserInfo> {
  return http.get("/auth/me", config);
}
