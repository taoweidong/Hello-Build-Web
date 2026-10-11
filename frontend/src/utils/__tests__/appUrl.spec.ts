// utils/appUrl 单测：hash 深链接拼接（origin + pathname + #/xxx）
import { describe, expect, it } from "vitest";
import { appHashUrl } from "@/utils/appUrl";

describe("appHashUrl", () => {
  it("拼接 origin + pathname + hash 路径", () => {
    const { origin, pathname } = window.location;
    expect(appHashUrl("/report/detail/5")).toBe(
      `${origin}${pathname}#/report/detail/5`
    );
  });

  it("自动补前导斜杠", () => {
    expect(appHashUrl("borrow-flow/index?focus=3")).toContain(
      "#/borrow-flow/index?focus=3"
    );
  });
});
