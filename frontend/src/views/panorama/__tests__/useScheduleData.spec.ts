// 调度全景数据中枢单测：三源编排口径 + 轮询退避 / 隐藏暂停 / 卸载守卫
// 依据：docs/superpowers/specs/2026-10-12-scheduling-panorama-design.md §5.1.2~5.1.3
// 背景：轮询原计划由 5 个展示层各自接入，收敛到中枢后此处是唯一回归点
// （branch-config 页曾因漏卸载守卫出现僵尸轮询 R3-F1，见 useScheduleData 头部注释）。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, ref } from "vue";
import { mount, flushPromises } from "@vue/test-utils";
import { businessUserKey } from "@/store/constants";

vi.mock("@/api/weekly", () => ({ getWeekly: vi.fn() }));
vi.mock("@/api/slotBooking", () => ({ getSlotCalendar: vi.fn() }));
vi.mock("@/api/plan", () => ({ getPlan: vi.fn() }));
vi.mock("@/api/borrowFlow", () => ({ listBorrowFlows: vi.fn() }));

import { getWeekly } from "@/api/weekly";
import { getSlotCalendar } from "@/api/slotBooking";
import { getPlan } from "@/api/plan";
import { listBorrowFlows } from "@/api/borrowFlow";
import { useScheduleData, type ScheduleDataOptions } from "../useScheduleData";
import {
  WEEK_FROM,
  makeBorrowFlow,
  makePlanVersions,
  makeWeekCalendar,
  makeWeeklyData
} from "./fixtures";
import type { ScheduleQuery } from "../types";
import type { WeeklyData } from "@/api/types";

const weeklyMock = vi.mocked(getWeekly);
const calendarMock = vi.mocked(getSlotCalendar);
const planMock = vi.mocked(getPlan);
const borrowMock = vi.mocked(listBorrowFlows);

/** 固定查询范围（单自然月， monthsOf 只发一次 slot-calendar） */
function makeQuery(over: Partial<ScheduleQuery> = {}): ScheduleQuery {
  return {
    dateFrom: WEEK_FROM,
    dateTo: "2026-10-18",
    versionId: 1,
    branchIds: [],
    scope: "all",
    ...over
  };
}

/** 挂载 composable 宿主组件；query 提升到外层便于用例改写 */
function mountData(
  options?: ScheduleDataOptions,
  queryOverrides: Partial<ScheduleQuery> = {}
) {
  let api!: ReturnType<typeof useScheduleData>;
  const query = ref<ScheduleQuery>(makeQuery(queryOverrides));
  const Comp = defineComponent({
    setup() {
      api = useScheduleData(query, options);
      return () => h("div");
    }
  });
  const wrapper = mount(Comp);
  return { wrapper, api, query };
}

/** 切换 document.hidden（jsdom 原型 getter 之上覆写实例属性） */
function setHidden(value: boolean) {
  Object.defineProperty(document, "hidden", { value, configurable: true });
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  // 用户 id=7 与夹具 borrowFlow.borrower_id 对齐，mine 判定可复现
  localStorage.setItem(
    businessUserKey,
    JSON.stringify({ id: 7, username: "u", role: "admin", bound_version_id: 1 })
  );
  weeklyMock.mockResolvedValue(makeWeeklyData());
  calendarMock.mockResolvedValue(makeWeekCalendar());
  planMock.mockResolvedValue(makePlanVersions());
  borrowMock.mockResolvedValue([makeBorrowFlow()]);
  // 只假造定时器：VTU 的 flushPromises 依赖真实 setImmediate 冲刷微任务
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});

afterEach(() => {
  setHidden(false);
  vi.useRealTimers();
});

describe("useScheduleData 三源编排", () => {
  it("策略/时段/借用归约为同构事件，锚点日阶段区间来自 /plan", async () => {
    const { wrapper, api } = mountData();
    await flushPromises();
    // 四个数据源各拉一次；首屏刷新不带 silent（后端故障要弹 toast）
    expect(weeklyMock).toHaveBeenCalledTimes(1);
    expect(weeklyMock).toHaveBeenCalledWith(
      { week_start: WEEK_FROM, version_id: 1 },
      undefined
    );
    expect(calendarMock).toHaveBeenCalledWith("2026-10", undefined);
    expect(planMock).toHaveBeenCalledWith({ date: WEEK_FROM }, undefined);
    expect(borrowMock).toHaveBeenCalledWith("pending", undefined);

    // 策略：锚点日四阶段（4）+ 其余 6 日各 build/push 点事件（12）= 16
    // 时段：7 天各 1 格 = 7；借用：1
    expect(api.events.value).toHaveLength(24);
    const anchor = api.events.value.filter(
      e => e.source === "strategy" && e.date === WEEK_FROM
    );
    expect(anchor.map(e => e.kind)).toEqual([
      "build",
      "smoke",
      "analysis",
      "push"
    ]);
    // 时长取自服务端 timeline（30/30/30/20），禁止前端按 RuntimeConfig 硬算
    expect(anchor.map(e => e.durationMin)).toEqual([30, 30, 30, 20]);
    // 非锚点日退化为点事件
    const other = api.events.value.filter(
      e => e.source === "strategy" && e.date !== WEEK_FROM && e.kind === "build"
    );
    expect(other).toHaveLength(6);
    expect(other.every(e => e.durationMin === 0)).toBe(true);

    // 借用锚定发起日；mine 命中（borrower_id=7 = 当前用户 id）
    const borrow = api.events.value.find(e => e.source === "borrow")!;
    expect(borrow).toMatchObject({
      id: "borrow:500",
      date: "2026-10-13",
      mine: true,
      past: false
    });
    expect(api.kpi.value).toMatchObject({
      pendingBorrow: 1,
      weekSlotTotal: 7,
      weekSlotOccupied: 1,
      mySlots: 1
    });
    expect(api.loading.value).toBe(false);
    expect(api.lastLoadedAt.value).toBeInstanceOf(Date);
    wrapper.unmount();
  });

  it("scope=mine 只保留与当前用户相关的事件", async () => {
    const { wrapper, api, query } = mountData();
    await flushPromises();
    expect(api.events.value.some(e => e.source === "strategy")).toBe(true);
    query.value = { ...query.value, scope: "mine" };
    await flushPromises();
    expect(api.events.value.every(e => e.mine)).toBe(true);
    expect(api.events.value.map(e => e.id).sort()).toEqual([
      "borrow:500",
      "slot:2026-10-13:1"
    ]);
    wrapper.unmount();
  });

  it("分支筛选保留无分支事件（借用等锚定在目标分支上）", async () => {
    const { wrapper, api, query } = mountData();
    await flushPromises();
    query.value = { ...query.value, branchIds: [11] };
    await flushPromises();
    const branchIds = new Set(
      api.events.value
        .map(e => e.branchId)
        .filter((v): v is number => v !== null)
    );
    expect([...branchIds]).toEqual([11]);
    // 借用事件 branchId 为目标分支 21，不在筛选内 → 被过滤
    expect(api.events.value.some(e => e.source === "borrow")).toBe(false);
    wrapper.unmount();
  });

  it("查询变更（范围/分支）立即重拉，仍不带 silent", async () => {
    const { wrapper, query } = mountData();
    await flushPromises();
    query.value = {
      ...query.value,
      dateFrom: "2026-10-05",
      dateTo: "2026-10-11"
    };
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(2);
    // 2026-10-05 自身是周一（上一周），week_start 即日期本身
    expect(weeklyMock).toHaveBeenLastCalledWith(
      { week_start: "2026-10-05", version_id: 1 },
      undefined
    );
    query.value = { ...query.value, branchIds: [11] };
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(3);
    wrapper.unmount();
  });
});

describe("useScheduleData 自动轮询", () => {
  it("首屏成功后 30s 排下一轮，轮询请求带 silent", async () => {
    const { wrapper } = mountData();
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(29_999);
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(1);
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(2);
    // 后台轮询不弹全局 toast（拦截器按 silent 放行）
    expect(weeklyMock.mock.calls[1][1]).toEqual({ silent: true });
    expect(borrowMock.mock.calls[1][1]).toEqual({ silent: true });
    wrapper.unmount();
  });

  it("失败按 30s→60s→120s 退避，恢复成功后重置为 30s", async () => {
    const { wrapper } = mountData();
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(1);
    weeklyMock.mockRejectedValue(new Error("boom"));
    vi.advanceTimersByTime(30_000);
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(60_000);
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(3);
    // 120s 差 1ms 都不触发
    vi.advanceTimersByTime(119_999);
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(3);
    vi.advanceTimersByTime(1);
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(4);
    // 恢复成功 → 退避清零，下一轮回到 30s
    weeklyMock.mockResolvedValue(makeWeeklyData());
    vi.advanceTimersByTime(240_000);
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(5);
    vi.advanceTimersByTime(30_000);
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(6);
    wrapper.unmount();
  });

  it("document.hidden 时不排定时器；恢复可见立即补拉一次", async () => {
    const { wrapper } = mountData();
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(1);
    setHidden(true);
    document.dispatchEvent(new Event("visibilitychange"));
    vi.advanceTimersByTime(600_000);
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(1);
    // 恢复可见：立即补一次，并重新按 30s 排轮
    setHidden(false);
    document.dispatchEvent(new Event("visibilitychange"));
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(30_000);
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(3);
    wrapper.unmount();
  });

  it("卸载守卫：卸载后不再排定时器，在途响应晚归也不复活轮询", async () => {
    // 首屏请求挂起，模拟慢网络下用户已离开页面
    let resolveFirst!: (v: WeeklyData) => void;
    weeklyMock.mockImplementationOnce(
      () =>
        new Promise<WeeklyData>(resolve => {
          resolveFirst = resolve;
        })
    );
    const { wrapper } = mountData();
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(1);
    wrapper.unmount();
    // 卸载后响应才晚归：refresh 的 finally/then 排定时器路径必须被 disposed 挡住
    resolveFirst(makeWeeklyData());
    await flushPromises();
    vi.advanceTimersByTime(600_000);
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(1);
  });

  it("autoRefreshMs: false 关闭自动轮询（仅保留查询变更与写动作刷新）", async () => {
    const { wrapper } = mountData({ autoRefreshMs: false });
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(600_000);
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });
});
