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
vi.mock("@/api/panorama", () => ({ getPanoramaTodos: vi.fn() }));

import { getWeekly } from "@/api/weekly";
import { getSlotCalendar } from "@/api/slotBooking";
import { getPlan } from "@/api/plan";
import { listBorrowFlows } from "@/api/borrowFlow";
import { getPanoramaTodos } from "@/api/panorama";
import { monthsOf, useScheduleData } from "../useScheduleData";
import {
  WEEK_FROM,
  makeBorrowFlow,
  makePlanVersions,
  makeTodos,
  makeWeekCalendar,
  makeWeeklyData
} from "./fixtures";
import type { ScheduleQuery } from "../types";
import type { WeeklyData } from "@/api/types";

const weeklyMock = vi.mocked(getWeekly);
const calendarMock = vi.mocked(getSlotCalendar);
const planMock = vi.mocked(getPlan);
const borrowMock = vi.mocked(listBorrowFlows);
const todosMock = vi.mocked(getPanoramaTodos);

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

/** 挂载 composable 宿主组件；query 提升到外层便于用例改写
 * （原 autoRefreshMs 选项从无生产调用方，已按 YAGNI 删除，R4-F13/F-L3） */
function mountData(queryOverrides: Partial<ScheduleQuery> = {}) {
  let api!: ReturnType<typeof useScheduleData>;
  const query = ref<ScheduleQuery>(makeQuery(queryOverrides));
  const Comp = defineComponent({
    setup() {
      api = useScheduleData(query);
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
  todosMock.mockResolvedValue(makeTodos());
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

  it("silent 轮询不驱动 loading（R7-F3：骨架屏不再随轮询闪烁）", async () => {
    const { api, wrapper } = mountData();
    await flushPromises();
    expect(api.loading.value).toBe(false);
    // 挂起一轮 silent 轮询响应，全程 loading 恒 false
    let resolvePoll!: (v: WeeklyData) => void;
    weeklyMock.mockImplementationOnce(
      () => new Promise(res => (resolvePoll = res))
    );
    const polling = api.refresh(true);
    await flushPromises();
    expect(api.loading.value).toBe(false);
    resolvePoll(makeWeeklyData());
    await polling;
    await flushPromises();
    expect(api.loading.value).toBe(false);
    wrapper.unmount();
  });

  it("策略事件携带版本名（R7-F7：S4 按版本分组不再把同版本拆两组）", async () => {
    const { api, wrapper } = mountData();
    await flushPromises();
    const strategy = api.events.value.find(e => e.source === "strategy")!;
    expect(strategy.versionName).toBe("27A");
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
});

describe("monthsOf 自然月聚合与截断标记（R4-F13/F-L7）", () => {
  it("单月/跨 3 个月：不截断", () => {
    expect(monthsOf("2026-10-12", "2026-10-18")).toEqual({
      months: ["2026-10"],
      truncated: false
    });
    expect(monthsOf("2026-10-31", "2026-12-01")).toEqual({
      months: ["2026-10", "2026-11", "2026-12"],
      truncated: false
    });
  });

  it("超过 3 个自然月：仅取前 3 个月且 truncated=true（第 4 个月起矩阵缺失需提示）", () => {
    expect(monthsOf("2026-10-01", "2027-03-01")).toEqual({
      months: ["2026-10", "2026-11", "2026-12"],
      truncated: true
    });
  });

  it("中枢把截断标记外化到 slotTruncated（画布层据此提示）", async () => {
    const { wrapper, api } = mountData({
      dateFrom: "2026-10-01",
      dateTo: "2027-03-01"
    });
    await flushPromises();
    expect(api.slotTruncated.value).toBe(true);
    // 抢占矩阵只发前 3 个月的请求（请求放大保护口径不变）
    expect(calendarMock).toHaveBeenCalledTimes(3);
    expect(calendarMock.mock.calls.map(c => c[0])).toEqual([
      "2026-10",
      "2026-11",
      "2026-12"
    ]);
    wrapper.unmount();
  });

  it("常规周范围：slotTruncated 为 false", async () => {
    const { wrapper, api } = mountData();
    await flushPromises();
    expect(api.slotTruncated.value).toBe(false);
    wrapper.unmount();
  });
});

describe("useScheduleData 待办聚合（P2-R3）", () => {
  it("随刷新并发拉取 todos，供页面展示跨筛选口径的待办量", async () => {
    todosMock.mockResolvedValue(
      makeTodos({
        pending_approval: 4,
        my_reserved_slots: 2,
        my_pending_borrows: 3
      })
    );
    const { wrapper, api } = mountData();
    await flushPromises();
    expect(todosMock).toHaveBeenCalledWith(undefined);
    expect(api.todos.value).toEqual({
      pending_approval: 4,
      my_reserved_slots: 2,
      my_pending_borrows: 3
    });
    wrapper.unmount();
  });

  it("todos 失败不阻断主流程：events 照常就绪，todos 保持 null（页面回退前端聚合）", async () => {
    todosMock.mockRejectedValue(new Error("todos unavailable"));
    const { wrapper, api } = mountData();
    await flushPromises();
    expect(api.todos.value).toBeNull();
    // 三源数据不受影响（与三源编排用例同一夹具口径）
    expect(api.events.value).toHaveLength(24);
    wrapper.unmount();
  });
});

describe("数据中枢四路并发与乱序守卫（R5-F1/F12）", () => {
  it("weekly 先行，calendars/flows/todos/plan 四路并发（任一未归即整体挂起）", async () => {
    // 挂起借用一路：并发实现下其余三路已全部发出；串行实现会停在借用之前
    let resolveBorrow!: (v: ReturnType<typeof makeBorrowFlow>[]) => void;
    borrowMock.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          resolveBorrow = resolve;
        })
    );
    const { wrapper, api } = mountData();
    await flushPromises();
    expect(weeklyMock).toHaveBeenCalledTimes(1);
    expect(calendarMock).toHaveBeenCalledTimes(1);
    expect(todosMock).toHaveBeenCalledTimes(1);
    expect(planMock).toHaveBeenCalledTimes(1);
    expect(borrowMock).toHaveBeenCalledTimes(1);
    // 四路未汇合：events 尚未写入
    expect(api.events.value).toHaveLength(0);
    resolveBorrow([makeBorrowFlow()]);
    await flushPromises();
    // 汇合后与串行版同一归约口径（24 条，同「三源编排」首用例）
    expect(api.events.value).toHaveLength(24);
    wrapper.unmount();
  });

  it("迟到响应不写回：旧 refresh 被新请求取代后，晚归的并发结果被 seq 守卫拦截", async () => {
    // 第一次 refresh 挂起在 plan 一路（旧实现正是 todos/plan 段之后终写无守卫）
    let resolvePlan!: (v: ReturnType<typeof makePlanVersions>) => void;
    planMock.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          resolvePlan = resolve;
        })
    );
    const { wrapper, api, query } = mountData();
    await flushPromises();
    expect(api.events.value).toHaveLength(0);
    // 查询变更触发第二次 refresh（默认 mock 立即落定，seq=2）
    query.value = { ...query.value, scope: "mine" };
    await flushPromises();
    expect(api.events.value.map(e => e.id).sort()).toEqual([
      "borrow:500",
      "slot:2026-10-13:1"
    ]);
    // 第一次的 plan 晚归：不得用旧数据（scope=all 的 24 条）覆盖第二次结果
    resolvePlan(makePlanVersions());
    await flushPromises();
    expect(api.events.value.map(e => e.id).sort()).toEqual([
      "borrow:500",
      "slot:2026-10-13:1"
    ]);
    wrapper.unmount();
  });

  it("plan 失败静默降级为点事件：events 照常就绪，锚点日不再展开四阶段", async () => {
    planMock.mockRejectedValueOnce(new Error("plan unavailable"));
    const { wrapper, api } = mountData();
    await flushPromises();
    // 策略 7 天 × (build+push) 点事件 = 14，时段 7、借用 1 → 22（无四阶段展开）
    expect(api.events.value).toHaveLength(22);
    const strategy = api.events.value.filter(e => e.source === "strategy");
    expect(strategy.every(e => e.durationMin === 0)).toBe(true);
    expect(api.loading.value).toBe(false);
    expect(api.lastLoadedAt.value).toBeInstanceOf(Date);
    wrapper.unmount();
  });
});
