// utils/appUrl 单测：hash 深链接拼接（origin + pathname + #/xxx）
import { describe, expect, it } from "vitest";
import { appHashUrl } from "@/utils/appUrl";

describe("appHashUrl", () => {
  it("拼接 origin + pathname + hash 路径", () => {
    const { origin, pathname } = window.location;
    expect(appHashUrl("/panorama/gantt")).toBe(
      `${origin}${pathname}#/panorama/gantt`
    );
  });

  it("自动补前导斜杠", () => {
    expect(appHashUrl("panorama/month?date=2026-10-24")).toContain(
      "#/panorama/month?date=2026-10-24"
    );
  });
});
