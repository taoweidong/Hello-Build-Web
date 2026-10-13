// 示例菜单演示数据纯函数单测：筛选 / 分页口径锁定
import { describe, expect, it } from "vitest";
import { DEMO_USERS, filterDemoUsers, paginateDemoUsers } from "../demoData";

describe("filterDemoUsers", () => {
  it("空条件返回全量", () => {
    expect(
      filterDemoUsers(DEMO_USERS, { keyword: "", role: "", status: "" })
    ).toHaveLength(DEMO_USERS.length);
  });

  it("关键字命中姓名（trim 后子串匹配）", () => {
    const rows = filterDemoUsers(DEMO_USERS, {
      keyword: "  张  ",
      role: "",
      status: ""
    });
    expect(rows.map(r => r.name)).toEqual(["张伟"]);
  });

  it("角色 + 状态组合过滤是与语义", () => {
    const rows = filterDemoUsers(DEMO_USERS, {
      keyword: "",
      role: "builder",
      status: "active"
    });
    expect(rows.map(r => r.name)).toEqual(["赵敏", "冯军"]);
  });

  it("条件互斥时返回空集（供页面空态展示）", () => {
    expect(
      filterDemoUsers(DEMO_USERS, {
        keyword: "不存在的名字",
        role: "",
        status: ""
      })
    ).toEqual([]);
  });
});

describe("paginateDemoUsers", () => {
  it("按页切片且 total 为全量", () => {
    const p1 = paginateDemoUsers(DEMO_USERS, 1, 5);
    expect(p1.items).toHaveLength(5);
    expect(p1.total).toBe(DEMO_USERS.length);
    const p3 = paginateDemoUsers(DEMO_USERS, 3, 5);
    expect(p3.items.map(r => r.id)).toEqual([11, 12]);
  });

  it("页码越界回退末页，非法页码/页大小回退安全值", () => {
    expect(paginateDemoUsers(DEMO_USERS, 99, 5).items).toHaveLength(2);
    expect(paginateDemoUsers(DEMO_USERS, 0, 5).items[0].id).toBe(1);
    // 非法 pageSize=0 回退 1（不抛错、不返回全量）
    expect(paginateDemoUsers(DEMO_USERS, 1, 0).items).toHaveLength(1);
  });

  it("空集分页不崩溃", () => {
    const res = paginateDemoUsers([], 1, 5);
    expect(res.items).toEqual([]);
    expect(res.total).toBe(0);
  });
});
