// JWT 业务纯函数（2026-10-13 第三轮质量优化自 store/modules/user.ts 抽取，便于单测锁定）

/** 从 JWT payload 解析真实过期时间；解析失败回退 8 小时（后端默认 ACCESS 时效） */
export function tokenExpiresAt(token: string): Date {
  try {
    const payload = JSON.parse(atob(token.split(".")[1] ?? ""));
    if (typeof payload?.exp === "number") {
      return new Date(payload.exp * 1000);
    }
  } catch {
    /* 非法 token 结构走默认时效 */
  }
  return new Date(Date.now() + 8 * 3600 * 1000);
}
