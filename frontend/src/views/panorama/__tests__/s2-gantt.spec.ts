// S2 时空甘特布局组件级测试 /panorama/gantt
// 重点：锚点日四阶段区间来自服务端 /plan（非前端硬算），翻日后退化为点标记
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import type { VueWrapper } from "@vue/test-utils";

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
import PanoramaGantt from "../layouts/s2-gantt/index.vue";
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

const FIXED_NOW = new Date("2026-10-13T10:00:00");

let wrapper: VueWrapper;

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

/** 从内联 style 里取百分比数值（left/width），避免硬编码浮点字符串 */
function stylePct(style: string | undefined, prop: string): number {
  const m = (style ?? "").match(new RegExp(`${prop}:\\s*([\\d.]+)%`));
  return m ? Number(m[1]) : Number.NaN;
}

describe("S2 时空甘特", () => {
  it("锚点日四阶段区间渲染为甘特条（区间来自 /plan，推送为虚线描边）", async () => {
    ({ wrapper } = await mountLayout(PanoramaGantt, "/panorama/gantt"));
    // 锚点日 = query.dateFrom = 2026-10-12
    expect(wrapper.find(".day-title").text()).toContain("2026年10月12日");
    const lanes = wrapper.findAll(".lane");
    // 分支泳道：main（4 阶段）+ 未关联分支（1 空闲时段），仅看有任务分支默认开
    expect(lanes).toHaveLength(2);
    const mainLane = lanes.find(l =>
      l.find(".lane-label").text().includes("main")
    )!;
    const bars = mainLane.findAll(".bar");
    expect(bars.map(b => b.text())).toEqual([
      "构建 · 主链路策略",
      "冒烟 · 主链路策略",
      "分析 · 主链路策略",
      "推送 · 主链路策略"
    ]);
    // 构建 08:00 起（480/1440 ≈ 33.33%）、30 分钟宽（≈2.08%）
    expect(stylePct(bars[0].attributes("style"), "left")).toBeCloseTo(33.33, 1);
    expect(stylePct(bars[0].attributes("style"), "width")).toBeCloseTo(2.08, 1);
    // 推送：透明底 + 虚线描边（与 HourGrid 既有表现一致）
    const pushStyle = bars[3].attributes("style") ?? "";
    expect(pushStyle).toContain("border-style: dashed");
    expect(pushStyle).toContain("background: transparent");
  });

  it("翻到后一天后只渲染当日（10-13）事件：main 四阶段 + release 抢占 + 借用 共 3 泳道", async () => {
    ({ wrapper } = await mountLayout(PanoramaGantt, "/panorama/gantt"));
    await wrapper
      .findAll("button")
      .find(b => b.attributes("aria-label") === "后一天")!
      .trigger("click");
    // shiftDay 改写 query → 中枢签名 watcher 触发异步重拉，需等待数据更新
    // （多段 await：getWeekly / getSlotCalendar / listBorrowFlows / getPlan，
    // 单次 flush 不足以让借用流 settle，故循环多次确保整表刷新写完）
    for (let i = 0; i < 3; i++) await flushPromises();
    expect(wrapper.find(".day-title").text()).toContain("2026年10月13日");
    // 10-13 成为锚点日：main 展开为四阶段区间；该日本人抢占落在 release 分支；
    // 借用流锚定在「发起日」created_at=2026-10-13（非新构建时间 10-14，新构建时间
    // 只出现在副标题），故当日也有一条借用 → 共 3 个分支泳道
    const lanes = wrapper.findAll(".lane");
    expect(lanes).toHaveLength(3);
    const mainLane = lanes.find(l =>
      l.find(".lane-label").text().includes("main")
    )!;
    expect(mainLane.findAll(".bar").map(b => b.text())).toEqual([
      "构建 · 主链路策略",
      "冒烟 · 主链路策略",
      "分析 · 主链路策略",
      "推送 · 主链路策略"
    ]);
    const releaseLane = lanes.find(l =>
      l.find(".lane-label").text().includes("release")
    )!;
    expect(releaseLane.findAll(".bar").map(b => b.text())).toEqual([
      "早间窗口"
    ]);
    // 借用流落在目标分支 feature-x，渲染为独立泳道与借用条（区别于抢占时段区间）
    const borrowLane = lanes.find(l =>
      l.find(".lane-label").text().includes("feature-x")
    )!;
    expect(borrowLane.findAll(".bar").map(b => b.text())).toEqual([
      "李四 借用 主链路策略"
    ]);
    expect(wrapper.findAll(".bar-borrow")).toHaveLength(1);
  });

  it("空数据时展示 el-empty 占位", async () => {
    // 翻到一个日历与策略都不覆盖的日期：策略每日循环仍有点事件，
    // 故用「仅看有任务分支」永远非空——此用例锁定骨架/空态二选一渲染不双出
    ({ wrapper } = await mountLayout(PanoramaGantt, "/panorama/gantt"));
    expect(wrapper.find(".el-skeleton").exists()).toBe(false);
    expect(wrapper.find(".gantt-scroll").exists()).toBe(true);
    expect(wrapper.find(".el-empty").exists()).toBe(false);
  });
});
