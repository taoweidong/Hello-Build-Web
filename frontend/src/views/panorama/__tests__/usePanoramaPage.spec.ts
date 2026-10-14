// usePanoramaPage 装配总线单测（R4-F9/F-M7）：
// 查询变更器（setVersion/setBranches/setScope/setDateRange/shiftBy/goToday/goThisWeek）
// 收敛前散落在五份布局文件逐字复制，本 spec 锁定唯一实现的语义。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import type { VueWrapper } from "@vue/test-utils";
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
import { usePanoramaPage } from "../usePanoramaPage";
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

/** 冻结「今天」= 2026-10-13（周二），所在周周一 = 2026-10-12 */
const FIXED_NOW = new Date("2026-10-13T10:00:00");

let wrapper: VueWrapper;

function mountPage() {
  let api!: ReturnType<typeof usePanoramaPage>;
  const Comp = defineComponent({
    setup() {
      api = usePanoramaPage();
      return () => h("div");
    }
  });
  wrapper = mount(Comp);
  return api;
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  localStorage.setItem(
    businessUserKey,
    JSON.stringify({ id: 7, username: "u", role: "admin", bound_version_id: 1 })
  );
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

describe("usePanoramaPage 查询变更器（R4-F9）", () => {
  it("默认查询为冻结日所在周（周一~周日）", async () => {
    const api = mountPage();
    await flushPromises();
    expect(api.query.value.dateFrom).toBe("2026-10-12");
    expect(api.query.value.dateTo).toBe("2026-10-18");
  });

  it("setVersion 切版本并重置分支筛选（分支 id 跨版本不同）", async () => {
    const api = mountPage();
    await flushPromises();
    api.setBranches([10, 11]);
    expect(api.query.value.branchIds).toEqual([10, 11]);
    api.setVersion(2);
    expect(api.query.value.versionId).toBe(2);
    expect(api.query.value.branchIds).toEqual([]);
  });

  it("setBranches / setScope 独立改写对应字段，不动日期范围", async () => {
    const api = mountPage();
    await flushPromises();
    api.setBranches([11]);
    api.setScope("mine");
    expect(api.query.value).toMatchObject({
      branchIds: [11],
      scope: "mine",
      dateFrom: "2026-10-12",
      dateTo: "2026-10-18"
    });
  });

  it("shiftBy 整体平移且保持跨度（周布局 ±7 / 日布局 ±1 共用）", async () => {
    const api = mountPage();
    await flushPromises();
    api.shiftBy(-7);
    expect(api.query.value.dateFrom).toBe("2026-10-05");
    expect(api.query.value.dateTo).toBe("2026-10-11");
    api.setDateRange("2026-10-13", "2026-10-13");
    api.shiftBy(1);
    expect(api.query.value.dateFrom).toBe("2026-10-14");
    expect(api.query.value.dateTo).toBe("2026-10-14");
  });

  it("goToday 收敛到冻结当日单日", async () => {
    const api = mountPage();
    await flushPromises();
    api.shiftBy(-7);
    api.goToday();
    expect(api.query.value.dateFrom).toBe("2026-10-13");
    expect(api.query.value.dateTo).toBe("2026-10-13");
  });

  it("goThisWeek 回到本周周一~周日（周一计算走 utils/week.mondayOf）", async () => {
    const api = mountPage();
    await flushPromises();
    api.shiftBy(-14);
    expect(api.query.value.dateFrom).toBe("2026-09-28");
    api.goThisWeek();
    expect(api.query.value.dateFrom).toBe("2026-10-12");
    expect(api.query.value.dateTo).toBe("2026-10-18");
  });

  it("变更器写回 query 后中枢按新口径重拉（weekly week_start 跟随平移）", async () => {
    const api = mountPage();
    await flushPromises();
    const callsBefore = weeklyMock.mock.calls.length;
    api.shiftBy(-7);
    await flushPromises();
    expect(weeklyMock.mock.calls.length).toBeGreaterThan(callsBefore);
    expect(weeklyMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ week_start: "2026-10-05" }),
      undefined
    );
  });

  it("返回结构暴露动作总线（含缓存失效入口，R4-F1）", async () => {
    const api = mountPage();
    await flushPromises();
    expect(typeof api.actions.openEdit).toBe("function");
    expect(typeof api.actions.batchRelease).toBe("function");
    expect(typeof api.actions.invalidateStrategyCache).toBe("function");
  });
});
