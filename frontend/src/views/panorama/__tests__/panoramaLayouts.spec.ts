// 布局清单与入口落点解析单测：优先级 query > localStorage > 默认，只此一处实现
import { describe, expect, it } from "vitest";
import {
  DEFAULT_LAYOUT,
  isLayoutKey,
  layoutOfPath,
  PANORAMA_LAYOUTS,
  resolveEntryLayout
} from "../shared/panoramaLayouts";

describe("panoramaLayouts", () => {
  it("layoutOfPath 未命中回落默认布局（月历）", () => {
    expect(layoutOfPath("/panorama/board")).toBe("board");
    expect(layoutOfPath("/panorama/nope")).toBe(DEFAULT_LAYOUT);
    expect(DEFAULT_LAYOUT).toBe("month");
  });

  it("isLayoutKey 拒绝不可信输入（query/localStorage 均不可信）", () => {
    expect(isLayoutKey("gantt")).toBe(true);
    expect(isLayoutKey("nope")).toBe(false);
    expect(isLayoutKey(null)).toBe(false);
    expect(isLayoutKey(42)).toBe(false);
    expect(isLayoutKey(["board"])).toBe(false);
  });

  it("resolveEntryLayout 优先级：?layout= > localStorage > 默认", () => {
    expect(resolveEntryLayout({ layout: "board" }, "gantt")).toBe("board");
    expect(resolveEntryLayout({}, "gantt")).toBe("gantt");
    expect(resolveEntryLayout({}, null)).toBe("month");
    // 两处都非法时回落默认，不把脏值透传到路由
    expect(resolveEntryLayout({ layout: "bogus" }, "also-bogus")).toBe("month");
  });

  it("布局清单 5 个独立路径，与 /panorama/* 子路由一一对应", () => {
    expect(PANORAMA_LAYOUTS).toHaveLength(5);
    expect(new Set(PANORAMA_LAYOUTS.map(l => l.path)).size).toBe(5);
    for (const l of PANORAMA_LAYOUTS) {
      expect(l.path).toBe(`/panorama/${l.layout}`);
    }
  });
});
