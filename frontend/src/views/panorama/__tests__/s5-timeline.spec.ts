// S5 时间轴流水布局组件级测试 /panorama/timeline
// 重点：?date= 深链把查询收敛为单日（S1 热力格下钻带入），锚点日因此切换为当日——
// 策略展开为四阶段区间、与本人抢占时段重合的分析阶段打「重合」徽标
// （detectCrossSourceConflicts 与 S1 告警同源）；四档筛选互斥口径。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import type { VueWrapper } from "@vue/test-utils";

vi.mock("@/api/weekly", () => ({ getWeekly: vi.fn() }));
vi.mock("@/api/slotBooking", () => ({ getSlotCalendar: vi.fn() }));
vi.mock("@/api/plan", () => ({ getPlan: vi.fn() }));
vi.mock("@/api/borrowFlow", () => ({ listBorrowFlows: vi.fn() }));

import { getWeekly } from "@/api/weekly";
import { getSlotCalendar } from "@/api/slotBooking";
import { getPlan } from "@/api/plan";
import { listBorrowFlows } from "@/api/borrowFlow";
import PanoramaTimeline from "../layouts/s5-timeline/index.vue";
import { mountLayout, setTestUser } from "./helpers";
import {
  makeBorrowFlow,
  makePlanVersions,
  makeWeekCalendar,
  makeWeeklyData
} from "./fixtures";

const weeklyMock = vi.mocked(getWeekly);
const calendarMock = vi.mocked(getSlotCalendar);
const planMock = vi.mocked(getPlan);
const borrowMock = vi.mocked(listBorrowFlows);

/** 与夹具 NOW 一致的冻结时刻（保留真实 setImmediate 供 flushPromises 冲刷） */
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
});

afterEach(() => {
  wrapper?.unmount();
  vi.useRealTimers();
});

/** 当日时间轴条目（已按 selectors.sortEvents 排序） */
function rows() {
  return wrapper.findAll(".track-item");
}

/** 按标题取条目（标题同日唯一） */
function rowOf(title: string) {
  const row = rows().find(r => r.find(".body-title").text() === title);
  if (!row) throw new Error(`时间轴条目不存在: ${title}`);
  return row;
}

/**
 * 切换筛选档位。
 * el-radio-button 的原生 input 挂 vModelRadio：对 input setValue(true)
 * 会置 checked 并派发 change，经指令写回 radio-group 的 modelValue。
 */
async function selectFilter(text: string) {
  const btn = wrapper.findAll(".el-radio-button").find(b => b.text() === text);
  if (!btn) throw new Error(`筛选档位不存在: ${text}`);
  await btn.find("input").setValue(true);
  await flushPromises();
}

describe("S5 时间轴流水", () => {
  it("?date= 深链锚定单日：四阶段 + 抢占 + 借用共 6 条，首条 08:00", async () => {
    ({ wrapper } = await mountLayout(
      PanoramaTimeline,
      "/panorama/timeline?date=2026-10-13"
    ));
    expect(wrapper.find(".day-title").text()).toContain("2026年10月13日");
    // 深链把查询收敛为单日：/plan 以该日为锚点取四阶段区间（而非默认周首日）
    expect(planMock).toHaveBeenCalledTimes(1);
    expect(planMock).toHaveBeenCalledWith({ date: "2026-10-13" }, undefined);
    expect(rows()).toHaveLength(6);
    // 同日同时刻按时长降序：09:00 抢占（60min）排在 09:00 分析（30min）前
    expect(rows().map(r => r.find(".time-main").text())).toEqual([
      "08:00",
      "08:30",
      "09:00",
      "09:00",
      "09:15",
      "18:00"
    ]);
    const first = rows()[0];
    expect(first.find(".body-title").text()).toBe("构建 · 主链路策略");
    // 区间事件显示结束时刻（点事件 endTime === time 不渲染 time-sub）
    expect(first.find(".time-sub").text()).toBe("08:30");
    // 冻结时刻 10:00：08:00 / 08:30 / 09:00 三条已开始 → 置灰
    expect(wrapper.findAll(".track-body.body-past")).toHaveLength(3);
    expect(wrapper.text()).toContain("共 6 条");
  });

  it("跨源冲突：分析阶段与本人抢占重合，打「重合」徽标且可单独筛选", async () => {
    ({ wrapper } = await mountLayout(
      PanoramaTimeline,
      "/panorama/timeline?date=2026-10-13"
    ));
    // 10-13 成为锚点日：分析 09:00-09:30 落在本人抢占 09:00-10:00 内
    // （默认周首日锚定下 10-13 只有点事件，不冲突——冲突只在深链单日时出现）
    const analysis = rowOf("分析 · 主链路策略");
    expect(analysis.find(".el-tag--danger").text()).toBe("重合");
    await selectFilter("只看冲突");
    expect(rows()).toHaveLength(1);
    expect(rows()[0].find(".body-title").text()).toBe("分析 · 主链路策略");
  });

  it("筛选口径互斥：只看我的 2 条，只看借用 1 条且带审批/复制入口", async () => {
    ({ wrapper } = await mountLayout(
      PanoramaTimeline,
      "/panorama/timeline?date=2026-10-13"
    ));
    await selectFilter("只看我的");
    expect(rows()).toHaveLength(2);
    expect(rows().map(r => r.find(".body-title").text())).toEqual([
      "早间窗口",
      "李四 借用 主链路策略"
    ]);
    // 本人抢占有释放入口（reserved && mine），借用行无时段操作
    expect(
      rowOf("早间窗口")
        .findAll("button")
        .map(b => b.text())
    ).toEqual(["释放", "详情"]);

    await selectFilter("只看借用");
    expect(rows()).toHaveLength(1);
    const borrow = rows()[0];
    expect(borrow.find(".body-title").text()).toBe("李四 借用 主链路策略");
    // 借用事件：待审批徽标 + 通过/驳回（canApprove）+ 复制（source === borrow）
    expect(borrow.text()).toContain("待审批");
    expect(borrow.findAll("button").map(b => b.text())).toEqual([
      "通过",
      "驳回",
      "复制"
    ]);
  });

  it("翻日后重锚单日并重拉：锚点日四阶段 + 空闲时段抢占入口", async () => {
    ({ wrapper } = await mountLayout(
      PanoramaTimeline,
      "/panorama/timeline?date=2026-10-13"
    ));
    await wrapper
      .findAll("button")
      .find(b => b.attributes("aria-label") === "后一天")!
      .trigger("click");
    await flushPromises();
    expect(wrapper.find(".day-title").text()).toContain("2026年10月14日");
    // 重新以 10-14 为锚点拉取：10-14 成为锚点日 → 策略展开为四阶段区间
    expect(planMock).toHaveBeenLastCalledWith(
      { date: "2026-10-14" },
      undefined
    );
    // 10-14：四阶段（08:00/08:30/09:00/18:00）+ 空闲时段 09:00，共 5 条
    expect(rows()).toHaveLength(5);
    expect(rows().map(r => r.find(".body-title").text())).toEqual([
      "构建 · 主链路策略",
      "冒烟 · 主链路策略",
      "早间窗口",
      "分析 · 主链路策略",
      "推送 · 主链路策略"
    ]);
    // 锚点日策略带区间：构建有结束时刻 08:30
    expect(rowOf("构建 · 主链路策略").find(".time-sub").text()).toBe("08:30");
    // 空闲时段在 horizon 内且未过期 → 抢占入口 + 详情
    const slot = rowOf("早间窗口");
    expect(slot.text()).toContain("空闲可抢占");
    expect(slot.findAll("button").map(b => b.text())).toEqual(["抢占", "详情"]);
    // 借用事件锚定发起日 10-13，翻到 10-14 后离场
    expect(wrapper.text()).not.toContain("李四 借用 主链路策略");
  });

  it("「今天」按钮回到冻结当日（10-13）", async () => {
    ({ wrapper } = await mountLayout(
      PanoramaTimeline,
      "/panorama/timeline?date=2026-10-14"
    ));
    expect(wrapper.find(".day-title").text()).toContain("2026年10月14日");
    await wrapper
      .findAll("button")
      .find(b => b.text() === "今天")!
      .trigger("click");
    await flushPromises();
    expect(wrapper.find(".day-title").text()).toContain("2026年10月13日");
    // 回到今日：锚点日四阶段 + 冲突徽标一并回来
    expect(rows()).toHaveLength(6);
    expect(rowOf("分析 · 主链路策略").find(".el-tag--danger").exists()).toBe(
      true
    );
  });
});
