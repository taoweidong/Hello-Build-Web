// utils/token 单测：JWT 过期时间解析（安全相关纯函数，自 store/modules/user 抽取后锁定）
import { describe, expect, it, vi } from "vitest";
import { tokenExpiresAt } from "@/utils/token";

/** 构造 JWT 形态的伪 token（仅 payload 参与解析，签名段随意） */
function fakeJwt(payload: unknown): string {
  return `header.${btoa(JSON.stringify(payload))}.signature`;
}

describe("tokenExpiresAt", () => {
  it("exp 解析成功：返回真实过期时刻", () => {
    const exp = Math.floor(Date.UTC(2026, 9, 13, 12, 0, 0) / 1000);
    expect(tokenExpiresAt(fakeJwt({ exp })).getTime()).toBe(exp * 1000);
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
