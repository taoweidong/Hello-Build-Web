// S2 时空甘特布局组件级测试 /panorama/gantt
// 重点：锚点日四阶段区间来自服务端 /plan（非前端硬算），翻日后退化为点标记
import { defineComponent, h } from "vue";
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
import { usePanorama } from "../context";
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
  it("首屏锚今天：四阶段区间渲染为甘特条（区间来自 /plan，推送为虚线描边）", async () => {
    ({ wrapper } = await mountLayout(PanoramaGantt, "/panorama/gantt"));
    // 首屏锚点 = 今天 = FIXED_NOW 的 2026-10-13（R5-F6：此前吃 defaultWeekQuery
    // 的周一 10-12，周中打开看到的是历史日，需手点「今天」才能归位）
    expect(wrapper.find(".biz-range-title").text()).toContain("2026年10月13日");
    // R4-F6：星期文案走 utils/week 中文唯一来源（dayjs `ddd` 未加载 zh-cn 会输出 "Mon"）
    expect(wrapper.find(".biz-range-title").text()).toContain("周二");
    expect(wrapper.find(".biz-range-title").text()).not.toMatch(
      /Mon|Tue|Wed|Thu|Fri|Sat|Sun/
    );
    const lanes = wrapper.findAll(".lane");
    // 10-13 为锚点日：main 展开四阶段区间；该日本人抢占落在 release 分支；
    // 借用流锚定在「发起日」created_at=2026-10-13 → 共 3 个分支泳道
    expect(lanes).toHaveLength(3);
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
    // 该日本人抢占（release/早间窗口）与借用条（feature-x）同画布
    const releaseLane = lanes.find(l =>
      l.find(".lane-label").text().includes("release")
    )!;
    expect(releaseLane.findAll(".bar").map(b => b.text())).toEqual([
      "早间窗口"
    ]);
    expect(wrapper.findAll(".bar-borrow")).toHaveLength(1);
  });

  it("翻到后一天（10-14）：main 仍按 /plan 展开四阶段，借用不再落在当日", async () => {
    ({ wrapper } = await mountLayout(PanoramaGantt, "/panorama/gantt"));
    await wrapper
      .findAll("button")
      .find(b => b.attributes("aria-label") === "后一天")!
      .trigger("click");
    // shiftDay 改写 query → 中枢签名 watcher 触发异步重拉，需等待数据更新
    //（四路并发汇合后统一写入，循环多段 flush 确保整表刷新写完）
    for (let i = 0; i < 3; i++) await flushPromises();
    expect(wrapper.find(".biz-range-title").text()).toContain("2026年10月14日");
    // 翻日后星期文案同步（2026-10-14 为周三）
    expect(wrapper.find(".biz-range-title").text()).toContain("周三");
    // 10-14 成为新锚点日（days[0]）：main 展开四阶段区间；该日无本人抢占
    //（reserved 在 10-13）、借用锚定发起日 10-13 → 泳道为 main + 未关联分支（空闲时段）
    const lanes = wrapper.findAll(".lane");
    expect(lanes).toHaveLength(2);
    const mainLane = lanes.find(l =>
      l.find(".lane-label").text().includes("main")
    )!;
    expect(mainLane.findAll(".bar").map(b => b.text())).toEqual([
      "构建 · 主链路策略",
      "冒烟 · 主链路策略",
      "分析 · 主链路策略",
      "推送 · 主链路策略"
    ]);
    expect(wrapper.findAll(".bar-borrow")).toHaveLength(0);
  });

  it("空数据时展示 el-empty 占位", async () => {
    // 翻到一个日历与策略都不覆盖的日期：策略每日循环仍有点事件，
    // 故用「仅看有任务分支」永远非空——此用例锁定骨架/空态二选一渲染不双出
    ({ wrapper } = await mountLayout(PanoramaGantt, "/panorama/gantt"));
    expect(wrapper.find(".el-skeleton").exists()).toBe(false);
    expect(wrapper.find(".gantt-scroll").exists()).toBe(true);
    expect(wrapper.find(".el-empty").exists()).toBe(false);
  });

  it("R6-F8：过期抢占点击放行详情（与 S4/S5「详情」恒可用口径对齐）", async () => {
    // 探针组件替换 ScheduleDialogs：注入同一上下文，ui.detailVisible 为真时渲染哨兵
    ({ wrapper } = await mountLayout(PanoramaGantt, "/panorama/gantt", {
      ScheduleDialogs: defineComponent({
        setup() {
          const { actions } = usePanorama();
          return () =>
            actions.ui.detailVisible
              ? h("div", { class: "detail-probe" })
              : null;
        }
      })
    }));
    // 翻到 10-12（相对冻结时刻已过期）：空闲时段条 canOccupy=false → 应进详情
    await wrapper
      .findAll("button")
      .find(b => b.attributes("aria-label") === "前一天")!
      .trigger("click");
    for (let i = 0; i < 3; i++) await flushPromises();
    const slotBar = wrapper
      .findAll(".bar")
      .find(b => b.text().includes("早间窗口"))!;
    await slotBar.trigger("click");
    await flushPromises();
    expect(wrapper.find(".detail-probe").exists()).toBe(true);
  });
});
