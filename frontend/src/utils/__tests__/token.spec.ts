// utils/token 单测：JWT 过期时间解析（安全相关纯函数，自 store/modules/user 抽取后锁定）
import { describe, expect, it, vi } from "vitest";
import { tokenExpiresAt } from "@/utils/token";

/** 构造 JWT 形态的伪 token（仅 payload 参与解析，签名段随意） */
function fakeJwt(payload: unknown): string {
  return `header.${btoa(JSON.stringify(payload))}.signature`;
}

/** 构造真实 JWT 编码形态的伪 token：payload 段用 base64url（-/_ 替代 +//，去 padding）
 * 后端 simplejwt 输出的就是 base64url，含 -/_ 或缺 "=" 时 atob 会直接抛错（R5-F11） */
function fakeBase64UrlJwt(payload: unknown): string {
  const b64url = btoa(JSON.stringify(payload))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  return `header.${b64url}.signature`;
}

describe("tokenExpiresAt", () => {
  it("exp 解析成功：返回真实过期时刻", () => {
    const exp = Math.floor(Date.UTC(2026, 9, 13, 12, 0, 0) / 1000);
    expect(tokenExpiresAt(fakeJwt({ exp })).getTime()).toBe(exp * 1000);
  });

  it("base64url payload（含 - 字符）解析出正确 exp（R5-F11）", () => {
    const exp = 1760356800;
    // note 含 "~ûï"：base64url 编码后带 "-" 字符（atob 直接解码会抛错）
    const token = fakeBase64UrlJwt({ exp, note: "~ûï" });
    expect(token.split(".")[1]).toContain("-");
    expect(tokenExpiresAt(token).getTime()).toBe(exp * 1000);
  });

  it("base64url payload（含 _ 字符且无 padding）解析出正确 exp（R5-F11）", () => {
    const exp = 1760356800;
    // note 含 "þÿû"：base64url 编码后带 "_" 字符且长度 mod 4 = 2（缺 "==" padding）
    const token = fakeBase64UrlJwt({ exp, note: "þÿû" });
    const seg = token.split(".")[1];
    expect(seg).toContain("_");
    expect(seg.length % 4).not.toBe(0);
    expect(tokenExpiresAt(token).getTime()).toBe(exp * 1000);
  });

  it("非法 base64url 串仍回退 8 小时（try/catch 语义不变）", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-13T10:00:00"));
    try {
      const fallback = Date.now() + 8 * 3600 * 1000;
      // 归一后仍非法 base64（含 atob 无法解码的字符）
      expect(tokenExpiresAt("a.!!!not-base64!!!.c").getTime()).toBe(fallback);
      // 合法 base64url 但解出来不是 JSON
      expect(tokenExpiresAt("a.-_8-_.c").getTime()).toBe(fallback);
    } finally {
      vi.useRealTimers();
    }
  });

  it("非法 token 结构回退 8 小时", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-13T10:00:00"));
    try {
      const fallback = Date.now() + 8 * 3600 * 1000;
      // 无 payload 段
      expect(tokenExpiresAt("not-a-jwt").getTime()).toBe(fallback);
      // 空串
      expect(tokenExpiresAt("").getTime()).toBe(fallback);
      // payload 非 JSON
      expect(tokenExpiresAt("a.b.c").getTime()).toBe(fallback);
      // exp 非数字
      expect(tokenExpiresAt(fakeJwt({ exp: "2000" })).getTime()).toBe(fallback);
      // 无 exp 字段
      expect(tokenExpiresAt(fakeJwt({ sub: 1 })).getTime()).toBe(fallback);
    } finally {
      vi.useRealTimers();
    }
  });
});
