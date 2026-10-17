// utils/seqGuard 单测（R5-F4）：过期响应守卫的纯逻辑锁定
// 页面接线（branch-config/slot-booking/RecordsPanel/borrow-flow/logs）依赖此语义：
// 仅最新令牌可写响应式状态，迟到响应一律丢弃
import { describe, expect, it } from "vitest";
import { createSeqGuard } from "@/utils/seqGuard";

describe("createSeqGuard 过期响应守卫", () => {
  it("next 递增：每次发起返回自增令牌", () => {
    const guard = createSeqGuard();
    expect(guard.next()).toBe(1);
    expect(guard.next()).toBe(2);
    expect(guard.next()).toBe(3);
  });

  it("旧令牌 isCurrent=false：被更晚请求取代后迟到响应应丢弃", () => {
    const guard = createSeqGuard();
    const first = guard.next();
    const second = guard.next();
    expect(guard.isCurrent(first)).toBe(false);
    expect(guard.isCurrent(second)).toBe(true);
  });

  it("最新令牌 isCurrent=true：未被取代时可写状态", () => {
    const guard = createSeqGuard();
    const token = guard.next();
    expect(guard.isCurrent(token)).toBe(true);
    // 再发起一次后，前一个令牌立即失效
    guard.next();
    expect(guard.isCurrent(token)).toBe(false);
  });

  it("多实例互不影响：各加载域独立计数（勿跨域共享的语义锁定）", () => {
    const a = createSeqGuard();
    const b = createSeqGuard();
    const tokenA1 = a.next();
    const tokenA2 = a.next();
    const tokenB1 = b.next();
    // a 域内旧令牌已失效，但 b 域的最新令牌不受影响
    expect(a.isCurrent(tokenA1)).toBe(false);
    expect(a.isCurrent(tokenA2)).toBe(true);
    expect(b.isCurrent(tokenB1)).toBe(true);
    // 两实例序号独立：b 再发起不影响 a 的判定
    b.next();
    expect(a.isCurrent(tokenA2)).toBe(true);
    expect(b.isCurrent(tokenB1)).toBe(false);
  });

  it("新实例首个令牌从 1 起：未经 next 的令牌（如 99）非最新", () => {
    const guard = createSeqGuard();
    expect(guard.isCurrent(99)).toBe(false);
    expect(guard.next()).toBe(1);
  });
});
