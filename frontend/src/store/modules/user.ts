import { defineStore } from "pinia";
import {
  type userType,
  store,
  router,
  resetRouter,
  routerArrays,
  storageLocal
} from "../utils";
import { type RefreshTokenResult, refreshTokenApi } from "@/api/user";
// 后端认证接口（构建策略配置系统契约）
import { loginApi, logoutApi } from "@/api/auth";
import type { UserInfo } from "@/api/types";
import { useMultiTagsStoreHook } from "./multiTags";
import { type DataInfo, setToken, removeToken, userKey } from "@/utils/auth";
// JWT 过期时间解析（纯函数已抽到 utils/token 便于单测，此处 re-export 保持既有引用路径可用）
import { tokenExpiresAt } from "@/utils/token";

/** 登录用户信息存储 key（含绑定版本等业务元数据） */
// 业务存储键常量收敛到 store/constants（此处 re-export 保持既有导入兼容）
import { businessUserKey as _businessUserKey } from "../constants";

export const useUserStore = defineStore("pure-user", {
  state: (): userType => ({
    // 头像
    avatar: storageLocal().getItem<DataInfo<number>>(userKey)?.avatar ?? "",
    // 用户名
    username: storageLocal().getItem<DataInfo<number>>(userKey)?.username ?? "",
    // 昵称
    nickname: storageLocal().getItem<DataInfo<number>>(userKey)?.nickname ?? "",
    // 页面级别权限
    roles: storageLocal().getItem<DataInfo<number>>(userKey)?.roles ?? [],
    // 按钮级别权限
    permissions:
      storageLocal().getItem<DataInfo<number>>(userKey)?.permissions ?? [],
    // 是否勾选了登录页的免登录
    isRemembered: false,
    // 登录页的免登录存储几天，默认7天
    loginDay: 7
  }),
  actions: {
    /** 存储头像 */
    SET_AVATAR(avatar: string) {
      this.avatar = avatar;
    },
    /** 存储用户名 */
    SET_USERNAME(username: string) {
      this.username = username;
    },
    /** 存储昵称 */
    SET_NICKNAME(nickname: string) {
      this.nickname = nickname;
    },
    /** 存储角色 */
    SET_ROLES(roles: Array<string>) {
      this.roles = roles;
    },
    /** 存储按钮级别权限 */
    SET_PERMS(permissions: Array<string>) {
      this.permissions = permissions;
    },
    /** 存储是否勾选了登录页的免登录 */
    SET_ISREMEMBERED(bool: boolean) {
      this.isRemembered = bool;
    },
    /** 设置登录页的免登录存储几天 */
    SET_LOGINDAY(value: number) {
      this.loginDay = Number(value);
    },
    /** 登入 */
    async loginByUsername(data: { username: string; password: string }) {
      return new Promise<{ success: boolean; user: UserInfo }>(
        (resolve, reject) => {
          // 对接后端 /api/auth/login 契约：{ token, user }
          loginApi(data)
            .then(res => {
              const { token, user } = res;
              // 写入基座 Token 与用户信息（角色用于菜单/路由权限过滤）
              setToken({
                accessToken: token,
                refreshToken: "",
                // 有效期取 JWT 真实 exp（不再伪造 30 天，避免过期后基座误判仍有效）
                expires: tokenExpiresAt(token),
                username: user.username,
                nickname: user.display_name,
                roles: [user.role],
                permissions: ["*:*:*"]
              });
              // 额外存储业务用户信息（PM 绑定版本等）
              localStorage.setItem(_businessUserKey, JSON.stringify(user));
              resolve({ success: true, user });
            })
            .catch(error => {
              reject(error);
            });
        }
      );
    },
    /** 登出：先请求后端将当前 token 拉黑（写安全日志），失败不阻塞本地清理 */
    logOut() {
      // fire-and-forget：后端不可达/ token 已失效时本地登出照常完成
      logoutApi().catch(() => undefined);
      this.username = "";
      this.roles = [];
      this.permissions = [];
      removeToken();
      // 清除业务用户信息
      localStorage.removeItem(_businessUserKey);
      useMultiTagsStoreHook().handleTags("equal", [...routerArrays]);
      resetRouter();
      router.push("/login");
    },
    /** 刷新`token` */
    async handRefreshToken(data) {
      return new Promise<RefreshTokenResult>((resolve, reject) => {
        refreshTokenApi(data)
          .then(data => {
            if (data) {
              setToken(data.data);
              resolve(data);
            }
          })
          .catch(error => {
            reject(error);
          });
      });
    }
  }
});

export function useUserStoreHook() {
  return useUserStore(store);
}
