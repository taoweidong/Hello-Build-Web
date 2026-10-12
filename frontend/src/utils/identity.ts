// 启动时业务身份快照刷新（R3-F10，2026-10-13 第三轮质量优化）
//
// 背景：build-user-info 是登录时刻的 localStorage 快照，服务端改角色/换绑定版本后，
// 前端到下次重新登录前无感知（canEditPanorama、审批权限、admin 判定全部基于旧快照）。
// 处理：应用启动时若已登录，静默拉一次 /auth/me 刷新快照与 user store；失败静默忽略
//（token 失效返回 40100/40101 时由 http 拦截器统一清理并跳登录，此处无需干预）。
import { getMe } from "@/api/auth";
import { businessUserKey } from "@/store/constants";
import { useUserStoreHook } from "@/store/modules/user";
import { getToken } from "@/utils/auth";

/** 已登录则静默刷新业务身份快照（localStorage + user store），永不 reject */
export async function refreshBusinessUser(): Promise<void> {
  if (!getToken()?.accessToken) return;
  try {
    const user = await getMe({ silent: true });
    localStorage.setItem(businessUserKey, JSON.stringify(user));
    const userStore = useUserStoreHook();
    userStore.SET_USERNAME(user.username);
    userStore.SET_NICKNAME(user.display_name);
    // 角色用于菜单/路由权限过滤，与登录时写入口径一致
    userStore.SET_ROLES([user.role]);
  } catch {
    // 静默失败：网络异常等不打扰用户；登录态失效由拦截器处理
  }
}
