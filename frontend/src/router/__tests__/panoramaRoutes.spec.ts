// /panorama 路由接线单测：redirect 优先级 + 5 子路由结构
// 落点解析规则本身在 panoramaLayouts.spec.ts 锁定，这里只验证「接线正确」
import { beforeEach, describe, expect, it } from "vitest";
import { panoramaLayoutKey } from "@/store/constants";
import { panoramaRoute } from "../panoramaRoutes";

const redirect = panoramaRoute.redirect as (to: {
  query: Record<string, unknown>;
}) => string;

beforeEach(() => {
  localStorage.clear();
});

describe("panorama 路由", () => {
  it("redirect 优先级：?layout= > localStorage 偏好 > 默认布局", () => {
    // 1) query 深链最高
    expect(redirect({ query: { layout: "board" } })).toBe("/panorama/board");
    // 2) 无 query 时读 localStorage 偏好（生产经 storageLocal 写入，值为 JSON 编码串）
    localStorage.setItem(panoramaLayoutKey, JSON.stringify("gantt"));
    expect(redirect({ query: {} })).toBe("/panorama/gantt");
    // 3) 都无 → 默认月历矩阵
    localStorage.removeItem(panoramaLayoutKey);
    expect(redirect({ query: {} })).toBe("/panorama/month");
    // 脏值不穿透：query 与 localStorage 都非法时仍回落默认
    localStorage.setItem(panoramaLayoutKey, JSON.stringify("not-a-layout"));
    expect(redirect({ query: { layout: "also-bad" } })).toBe("/panorama/month");
  });

  it("localStorage 为损坏的非 JSON 值时不崩溃，回落默认布局", () => {
    // 用户手改/损坏的裸字符串会让 @pureadmin/utils.getItem 的 JSON.parse 抛错；
    // resolveEntryLayout 必须兜住，否则 /panorama 入口整体卡死
    localStorage.setItem(panoramaLayoutKey, "gantt");
    expect(() => redirect({ query: {} })).not.toThrow();
    expect(redirect({ query: {} })).toBe("/panorama/month");
  });

  it("5 个布局子路由路径独立，对所有角色开放", () => {
    expect(panoramaRoute.children).toHaveLength(5);
    const paths = panoramaRoute.children.map(c => c.path);
    expect(new Set(paths).size).toBe(5);
    for (const child of panoramaRoute.children) {
      expect(child.path).toMatch(/^\/panorama\/[a-z]+$/);
      // 权限细化到事件级 permissions 包，路由层不做角色门槛
      expect(child.meta.roles).toEqual([
        "admin",
        "pm",
        "builder",
        "tester",
        "integrator"
      ]);
    }
  });
});
