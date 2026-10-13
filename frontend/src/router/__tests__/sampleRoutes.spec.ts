// 示例菜单路由接线单测：5 子路由结构 + redirect 落点 + 角色开放
import { describe, expect, it } from "vitest";
import { asyncRoutes } from "../asyncRoutes";
import { sampleRoute } from "../sampleRoutes";

describe("sample 示例菜单路由", () => {
  it("5 个子路由路径独立且命名唯一，对所有角色开放", () => {
    expect(sampleRoute.children).toHaveLength(5);
    const paths = sampleRoute.children.map(c => c.path);
    expect(new Set(paths).size).toBe(5);
    const names = sampleRoute.children.map(c => c.name);
    expect(new Set(names).size).toBe(5);
    for (const child of sampleRoute.children) {
      expect(child.path).toMatch(/^\/sample\/[a-z]+$/);
      expect(child.meta.roles).toEqual([
        "admin",
        "pm",
        "builder",
        "tester",
        "integrator"
      ]);
    }
  });

  it("父路由 redirect 落概览页", () => {
    expect(sampleRoute.redirect).toBe("/sample/overview");
  });

  it("sampleRoute 已并入业务路由表（asyncRoutes）", () => {
    expect(asyncRoutes).toContain(sampleRoute);
  });

  it("每个子路由都声明了组件（示例页非 redirect 路由）", () => {
    for (const child of sampleRoute.children) {
      expect(typeof child.component).toBe("function");
    }
  });
});
