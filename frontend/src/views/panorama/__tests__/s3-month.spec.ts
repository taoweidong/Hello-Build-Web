// S3 月历矩阵布局组件级测试 /panorama/month
// 重点：首屏加载当前月全量（非默认本周）；单元格事件卡渲染与点击分发
import { defineComponent, h } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import dayjs from "dayjs";
import { flushPromises } from "@vue/test-utils";
import type { VueWrapper } from "@vue/test-utils";
import type { Router } from "vue-router";
import { ElMessage } from "element-plus";

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
import PanoramaMonth from "../layouts/s3-month/index.vue";
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

/** 取某一天的月历单元格 */
function cellOf(date: string) {
  const cell = wrapper
    .findAll(".grid-cell")
    .find(
      c =>
        c.find(".cell-date").text().replace("今天", "").trim() ===
        String(dayjs(date).date())
    );
  if (!cell) throw new Error(`单元格不存在: ${date}`);
  return cell;
}

describe("S3 月历矩阵", () => {
  it("首屏加载当前月全量：42 格月历 + 工具栏统计", async () => {
    ({ wrapper } = await mountLayout(PanoramaMonth, "/panorama/month"));
    expect(wrapper.findAll(".grid-head")).toHaveLength(7);
    expect(wrapper.findAll(".grid-cell")).toHaveLength(42);
    // 冻结时刻 2026-10：当前月 31 天，策略 build 事件恰为 31 条
    // （锚点日四阶段含 1 条 build，其余每日 1 条）
    expect(wrapper.text()).toContain("策略 31");
    expect(wrapper.text()).toContain("已抢占 1 段");
    expect(wrapper.text()).toContain("我的 1 段");
    // 待审批计数由「待我审批（N）」按钮承载（与统计行去重）
    expect(wrapper.text()).toContain("待我审批（1）");
    // 首屏查询范围即当前月全月，而非默认本周（月历是抢占主战场）
    expect(weeklyMock).toHaveBeenCalledWith(
      expect.objectContaining({ week_start: "2026-09-28" }),
      undefined
    );
  });

  it("单元格渲染事件卡，超过 3 条显示更多入口", async () => {
    ({ wrapper } = await mountLayout(PanoramaMonth, "/panorama/month"));
    const cell = cellOf("2026-10-13");
    // 10-13：build / push 点事件 + 本人抢占 + 待审借用 = 4 条
    const chips = cell.findAll(".schedule-chip");
    expect(chips).toHaveLength(3);
    expect(cell.text()).toContain("早间窗口");
    const more = cell.findAll("button").find(b => b.text() === "+1 更多");
    expect(more).toBeTruthy();
  });

  it("点击更多入口下钻当日时间轴（S5）", async () => {
    ({ wrapper, router } = await mountLayout(PanoramaMonth, "/panorama/month"));
    const cell = cellOf("2026-10-13");
    await cell
      .findAll("button")
      .find(b => b.text() === "+1 更多")!
      .trigger("click");
    // router.push 为异步导航，需等待路由更新后再断言
    await flushPromises();
    // 与 S1 热力格同一下钻口径：带日期进当日时间轴，而非弹个 toast 了事
    expect(router.currentRoute.value.path).toBe("/panorama/timeline");
    expect(router.currentRoute.value.query.date).toBe("2026-10-13");
  });

  it("过期事件点击只读提示（冻结时刻下 10-12 全部已过期）", async () => {
    const infoSpy = vi.spyOn(ElMessage, "info");
    ({ wrapper } = await mountLayout(PanoramaMonth, "/panorama/month"));
    const cell = cellOf("2026-10-12");
    const chip = cell
      .findAll(".schedule-chip")
      .find(c => c.text().includes("构建 · 主链路策略"))!;
    expect(chip.classes()).toContain("chip-past");
    await chip.trigger("click");
    expect(infoSpy).toHaveBeenCalledWith("该日程已过期，仅可查看");
  });

  it("R6-F8：过期抢占卡片点击放行详情（与 S4/S5「详情」恒可用口径对齐）", async () => {
    // 探针组件替换 ScheduleDialogs：注入同一上下文，ui.detailVisible 为真时渲染哨兵
    ({ wrapper } = await mountLayout(PanoramaMonth, "/panorama/month", {
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
    const cell = cellOf("2026-10-12");
    // 10-12 的空闲时段卡（早间窗口）：canOccupy=false → 应进详情而非 info toast
    const chip = cell
      .findAll(".schedule-chip")
      .find(c => c.text().includes("早间窗口"))!;
    await chip.trigger("click");
    await flushPromises();
    expect(wrapper.find(".detail-probe").exists()).toBe(true);
  });

  it("翻到上一月后查询范围跟随月份", async () => {
    ({ wrapper } = await mountLayout(PanoramaMonth, "/panorama/month"));
    await wrapper
      .findAll("button")
      .find(b => b.attributes("aria-label") === "上一月")!
      .trigger("click");
    expect(wrapper.find(".biz-range-title").text()).toBe("2026年9月");
    // 9 月无策略数据之外的拉取口径：week_start 落在 8 月底所在周
    expect(weeklyMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ week_start: "2026-08-31" }),
      undefined
    );
  });
});
