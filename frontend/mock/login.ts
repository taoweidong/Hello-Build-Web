// 根据角色动态生成路由
// ⚠️ 仅开发环境使用（build/plugins.ts 中 enableProd 恒为 false）。
// 本文件返回的 accessToken/refreshToken 均为格式占位假 JWT，非真实签名令牌；
// 若 enableProd 被误开，此文件会进入生产构建并可直接伪造管理员身份。
import { defineFakeRoute } from "vite-plugin-fake-server/client";

export default defineFakeRoute([
  {
    url: "/login",
    method: "post",
    response: ({ body }) => {
      if (body.username === "admin") {
        return {
          success: true,
          data: {
            avatar: "https://avatars.githubusercontent.com/u/44761321",
            username: "admin",
            nickname: "小铭",
            // 一个用户可能有多个角色
            roles: ["admin"],
            // 按钮级别权限
            permissions: ["*:*:*"],
            accessToken: "eyJhbGciOiJIUzUxMiJ9.admin",
            refreshToken: "eyJhbGciOiJIUzUxMiJ9.adminRefresh",
            expires: "2030/10/30 00:00:00"
          }
        };
      } else {
        return {
          success: true,
          data: {
            avatar: "https://avatars.githubusercontent.com/u/52823142",
            username: "common",
            nickname: "小林",
            roles: ["common"],
            permissions: ["permission:btn:add", "permission:btn:edit"],
            accessToken: "eyJhbGciOiJIUzUxMiJ9.common",
            refreshToken: "eyJhbGciOiJIUzUxMiJ9.commonRefresh",
            expires: "2030/10/30 00:00:00"
          }
        };
      }
    }
  }
]);
