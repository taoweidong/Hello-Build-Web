// S1 态势大屏布局组件级测试 /panorama/dashboard
// 冻结「现在」到 2026-10-13 10:00，令 past / todayBuild / 月历等口径可复现
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import type { VueWrapper } from "@vue/test-utils";
import type { Router } from "vue-router";

vi.mock("@/api/weekly", () => ({ getWeekly: vi.fn() }));
vi.mock("@/api/slotBooking", () => ({ getSlotCalendar: vi.fn() }));
vi.mock("@/api/plan", () => ({ getPlan: vi.fn() }));
vi.mock("@/api/borrowFlow", () => ({ listBorrowFlows: vi.fn() }));
vi.mock("@/api/panorama", () => ({ getPanoramaTodos: vi.fn() }));

import { getWeekly } from "@/api/weekly";
import { getSlotCalendar } from "@/api/slotBooking";
import { getPlan } from "@/api/plan";
import { listBorrowFlows } from "@/api/borrowFlow";
import { getPanoramaTodos } from "@/api/panorama";
import PanoramaDashboard from "../layouts/s1-dashboard/index.vue";
import LayoutSwitcher from "../shared/LayoutSwitcher.vue";
import { mountLayout, setTestUser } from "./helpers";
import {
  makeBorrowFlow,
  makePlanVersions,
  makeTodos,
  makeWeekCalendar,
  makeWeeklyData
} from "./fixtures";

const weeklyMock = vi.mocked(getWeekly);
const calendarMock = vi.mocked(getSlotCalendar);
const planMock = vi.mocked(getPlan);
const borrowMock = vi.mocked(listBorrowFlows);
const todosMock = vi.mocked(getPanoramaTodos);

/** 与夹具 NOW 一致的冻结时刻（保留真实 setImmediate 供 flushPromises 冲刷） */
const FIXED_NOW = new Date("2026-10-13T10:00:00");

let wrapper: VueWrapper;
let router: Router;

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  setTestUser();
  vi.useFakeTimers({
    now: FIXED_NOW,
    toFake: ["setTimeout", "clearTimeout", "Date"]
  });
  weeklyMock.mockResolvedValue(makeWeeklyData());
  calendarMock.mockResolvedValue(makeWeekCalendar());
  planMock.mockResolvedValue(makePlanVersions());
  borrowMock.mockResolvedValue([makeBorrowFlow()]);
  todosMock.mockResolvedValue(makeTodos());
});

afterEach(() => {
  wrapper?.unmount();
  vi.useRealTimers();
});

/** 取某张统计卡的数值文本 */
function statValue(label: string): string {
  const item = wrapper
    .findAll(".stat-item")
    .find(i => i.find(".stat-label").text() === label);
  if (!item) throw new Error(`统计卡不存在: ${label}`);
  return item.find(".stat-value").text();
}

describe("S1 态势大屏", () => {
  it("挂载即拉取三源，KPI 卡按夹具口径渲染", async () => {
    ({ wrapper } = await mountLayout(PanoramaDashboard, "/panorama/dashboard"));
    // 首屏拉取：初始无版本号 → 中枢回填首个版本（weekly 返回 versions[0]）触发二次拉取
    expect(weeklyMock).toHaveBeenCalledTimes(2);
    // 冻结时刻 10-13：今日构建 1；本周抢占 1/7；待我审批 1；跨源冲突 0
    expect(statValue("今日构建")).toBe("1");
    expect(statValue("本周抢占")).toBe("1/7");
    expect(statValue("待我审批")).toBe("1");
    expect(statValue("跨源冲突")).toBe("0");
    // 待审批 > 0 触发告警样式
    const alert = wrapper
      .findAll(".stat-item")
      .find(i => i.find(".stat-label").text() === "待我审批")!;
    expect(alert.find(".stat-value").classes()).toContain("stat-alert");
    // 占用率 = 1/7 ≈ 14%
    expect(wrapper.text()).toContain("占用率 14%");
  });

  it("热力网格 7 天表头，待办队列渲染待审批借用", async () => {
    ({ wrapper } = await mountLayout(PanoramaDashboard, "/panorama/dashboard"));
    expect(wrapper.findAll(".heat-head").map(h => h.text())).toEqual([
      "周一",
      "周二",
      "周三",
      "周四",
      "周五",
      "周六",
      "周日"
    ]);
    const todos = wrapper.findAll(".todo-list li");
    expect(todos).toHaveLength(1);
    expect(todos[0].find(".todo-title").text()).toBe("李四 借用 主链路策略");
    // 异常告警：无跨源冲突时展示占位文案
    expect(wrapper.text()).toContain("暂无跨源冲突");
  });

  it("刷新按钮触发重新拉取（手动刷新非 silent）", async () => {
    ({ wrapper } = await mountLayout(PanoramaDashboard, "/panorama/dashboard"));
    const refreshBtn = wrapper.findAll("button").find(b => b.text() === "刷新");
    await refreshBtn!.trigger("click");
    // 首屏 2 次（版本回填）+ 手动刷新 1 次
    expect(weeklyMock).toHaveBeenCalledTimes(3);
    expect(weeklyMock.mock.calls.at(-1)![1]).toBeUndefined();
  });

  it("投屏模式：隐藏筛选栏并给根容器加样式钩子（仅信息密度差异）", async () => {
    ({ wrapper } = await mountLayout(PanoramaDashboard, "/panorama/dashboard"));
    expect(wrapper.find(".biz-filter-bar").exists()).toBe(true);

    await wrapper.find(".el-switch input").setValue(true);
    await flushPromises();
    expect(wrapper.find(".biz-filter-bar").exists()).toBe(false);
    expect(wrapper.find(".biz-page").classes()).toContain("present-mode");
    // 投屏只降密度，不隐藏信息
    expect(statValue("今日构建")).toBe("1");
  });

  it("待办计数取服务端聚合（跨筛选口径）", async () => {
    todosMock.mockResolvedValue(
      makeTodos({ pending_approval: 5, my_reserved_slots: 3 })
    );
    ({ wrapper } = await mountLayout(PanoramaDashboard, "/panorama/dashboard"));
    await flushPromises();
    expect(todosMock).toHaveBeenCalled();
    expect(statValue("待我审批")).toBe("5");
    expect(statValue("我的有效抢占")).toBe("3");
  });

  it("待办计数降级：接口不可用时回落前端聚合", async () => {
    todosMock.mockRejectedValue(new Error("todos unavailable"));
    ({ wrapper } = await mountLayout(PanoramaDashboard, "/panorama/dashboard"));
    await flushPromises();
    // 前端聚合同口径：1 条 pending 借用 / 1 条本人抢占
    expect(statValue("待我审批")).toBe("1");
    expect(statValue("我的有效抢占")).toBe("1");
  });

  it("热力格下钻跳转 S5 时间轴并带上日期", async () => {
    ({ wrapper, router } = await mountLayout(
      PanoramaDashboard,
      "/panorama/dashboard"
    ));
    await wrapper.findAll(".heat-cell")[0].trigger("click");
    // router.push 为异步导航，需等待路由更新后再断言
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/panorama/timeline");
    expect(router.currentRoute.value.query.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("布局切换器渲染且当前为态势大屏", async () => {
    ({ wrapper } = await mountLayout(PanoramaDashboard, "/panorama/dashboard"));
    const switcher = wrapper.findComponent(LayoutSwitcher);
    expect(switcher.exists()).toBe(true);
    expect(switcher.find(".el-select__selection").text()).toBe("态势大屏");
  });
});
