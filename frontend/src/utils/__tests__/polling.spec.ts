// 轮询退避策略单测：锁定「失败递增、成功重置、封顶 5min」
//（shouldNotify 无生产调用者，2026-10-13 第三轮质量优化随死代码一并删除其 2 例测试）
import { describe, expect, it } from "vitest";
import { pollDelay, POLL_BASE_MS, POLL_MAX_MS } from "@/utils/polling";

describe("pollDelay 退避间隔", () => {
  it("无失败时为基准间隔", () => {
    expect(pollDelay(0)).toBe(POLL_BASE_MS);
  });

  it("连续失败按指数递增", () => {
    expect(pollDelay(1)).toBe(60_000);
    expect(pollDelay(2)).toBe(120_000);
    expect(pollDelay(3)).toBe(240_000);
  });

  it("超过上限后封顶 5 分钟", () => {
    expect(pollDelay(4)).toBe(POLL_MAX_MS);
    expect(pollDelay(10)).toBe(POLL_MAX_MS);
    expect(pollDelay(100)).toBe(POLL_MAX_MS);
  });

  it("不会低于基准间隔", () => {
    expect(pollDelay(-1)).toBe(POLL_BASE_MS);
    expect(pollDelay(-999)).toBe(POLL_BASE_MS);
  });

  it("异常输入回落到基准间隔而非 NaN", () => {
    expect(pollDelay(NaN)).toBe(POLL_BASE_MS);
    expect(pollDelay(Infinity)).toBe(POLL_BASE_MS);
  });

  it("每次失败间隔严格大于前一次（封顶前）", () => {
    for (let i = 1; i < 4; i++) {
      expect(pollDelay(i)).toBeGreaterThan(pollDelay(i - 1));
    }
  });
});
