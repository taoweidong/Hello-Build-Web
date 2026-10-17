// JWT 业务纯函数（2026-10-13 第三轮质量优化自 store/modules/user.ts 抽取，便于单测锁定）

/**
 * base64url → base64 归一（R5-F11）：JWT 分段用 base64url 字母表（-/_ 替代
 * +//）且省略 padding；atob 只认标准 base64，payload 一旦含 -/_ 或缺 "=" 就抛
 * InvalidCharacterError，真实 token 会被误判非法而回退 8h。此处先替换字母表、
 * 再按长度 mod 4 补齐 "="，保证标准/base64url 两种编码都能解码。
 */
function base64UrlToBase64(input: string): string {
  const replaced = input.replace(/-/g, "+").replace(/_/g, "/");
  return replaced + "=".repeat((4 - (replaced.length % 4)) % 4);
}

/** 从 JWT payload 解析真实过期时间；解析失败回退 8 小时（后端默认 ACCESS 时效） */
export function tokenExpiresAt(token: string): Date {
  try {
    const payload = JSON.parse(
      atob(base64UrlToBase64(token.split(".")[1] ?? ""))
    );
    if (typeof payload?.exp === "number") {
      return new Date(payload.exp * 1000);
    }
  } catch {
    /* 非法 token 结构走默认时效 */
  }
  return new Date(Date.now() + 8 * 3600 * 1000);
}
