// 认证 API 模块
// 契约基准：设计文档 7.2 认证接口
import http from "@/api/http";
import type { LoginResult, UserInfo } from "@/api/types";

/** 登录：返回 JWT + 用户信息（写安全日志） */
export function loginApi(data: {
  username: string;
  password: string;
}): Promise<LoginResult> {
  return http.post("/auth/login", data);
}

/** 登出：写安全日志 */
export function logoutApi(): Promise<void> {
  return http.post("/auth/logout");
}

/** 当前用户信息（含权限元数据） */
export function getMe(): Promise<UserInfo> {
  return http.get("/auth/me");
}