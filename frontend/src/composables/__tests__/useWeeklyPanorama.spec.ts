import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { mount, flushPromises } from "@vue/test-utils";
import type { WeeklyData } from "@/api/types";
import { businessUserKey } from "@/store/constants";

vi.mock("@/api/weekly", () => ({ getWeekly: vi.fn() }));
vi.mock("@/api/strategy", () => ({ getStrategies: vi.fn() }));

import { getWeekly } from "@/api/weekly";
import { getStrategies } from "@/api/strategy";
import { useWeeklyPanorama } from "@/composables/useWeeklyPanorama";

const weeklyMock = vi.mocked(getWeekly);
const strategiesMock = vi.mocked(getStrategies);

/** 构造周视图数据（days 由组件内按 week_start 推导前先给足 7 天） */
function makeWeekly(overrides: Partial<WeeklyData> = {}): WeeklyData {
  return {
    week_start: "2026-10-12",
    days: [
      { date: "2026-10-12", weekday: "周一" },
      { date: "2026-10-13", weekday: "周二" },
      { date: "2026-10-14", weekday: "周三" },
      { date: "2026-10-15", weekday: "周四" },
      { date: "2026-10-16", weekday: "周五" },
      { date: "2026-10-17", weekday: "周六" },
      { date: "2026-10-18", weekday: "周日" }
    ],
    version: { version_id: 1, version_name: "27A" },
    versions: [
      { version_id: 1, version_name: "27A" },
      { version_id: 2, version_name: "27B" }
    ],
    branches: [
      { branch_id: 11, branch_name: "27A-master" },
      { branch_id: 12, branch_name: "27A-TR6" }
    ],
    strategies: [
      {
        strategy_id: 101,
        strategy_name: "早间回归",
        branch_id: 11,
        branch_name: "27A-master",
        build_start_time: "06:30",
        push_start_time: "09:00",
        push_mode: "sync",
        template_name: "冒烟A"
      },
      {
        strategy_id: 102,
        strategy_name: "晚间发布",
        branch_id: 12,
        branch_name: "27A-TR6",
        build_start_time: "22:00",
        push_start_time: null,
        push_mode: "normal",
        template_name: "冒烟B"
      }
    ],
    ...overrides
  };
}

/** 挂载 composable 宿主组件，返回响应式状态 */
function mountPanorama() {
  let api!: ReturnType<typeof useWeeklyPanorama>;
  const Comp = defineComponent({
    setup() {
      api = useWeeklyPanorama();
      return () => h("div");
    }
  });
  const wrapper = mount(Comp);
  // setup 同步执行，mount 返回时 api 已就绪
  return { wrapper, api };
}

function setUser(role: string, boundVersionId?: number) {
  localStorage.setItem(
    businessUserKey,
    JSON.stringify({
      id: 1,
      username: "u",
      role,
      bound_version_id: boundVersionId
    })
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  weeklyMock.mockResolvedValue(makeWeekly());
});

describe("useWeeklyPanorama 数据加载", () => {
  it("首屏加载并自动回填首个版本后二次拉取", async () => {
    const { api } = mountPanorama();
    await flushPromises();
    // 首次加载 → 回填 versionId → watcher 触发二次拉取（同一刷新周期内完成）
    expect(weeklyMock).toHaveBeenCalledTimes(2);
    expect(api.versionId.value).toBe(1);
    expect(weeklyMock).toHaveBeenLastCalledWith({
      week_start: api.weekStart.value,
      version_id: 1
    });
    expect(api.loading.value).toBe(false);
    expect(api.lastLoadedAt.value).toBeInstanceOf(Date);
  });

  it("翻周与回本周", async () => {
    const { api } = mountPanorama();
    await flushPromises();
    await flushPromises();
    api.shiftWeek(1);
    await flushPromises();
    expect(api.weekStart.value).toBe("2026-10-19");
    expect(api.isCurrentWeek.value).toBe(false);
    api.goThisWeek();
    await flushPromises();
    expect(api.isCurrentWeek.value).toBe(true);
  });

  it("分支筛选联动统计与可见分支", async () => {
    const { api } = mountPanorama();
    await flushPromises();
    await flushPromises();
    api.branchFilter.value = [12];
    await Promise.resolve();
    expect(api.stats.value.tasks).toBe(1);
    expect(api.stats.value.branches).toBe(1);
    expect(api.visibleBranches.value.map(b => b.branch_id)).toEqual([12]);
  });
});

describe("useWeeklyPanorama 时间点归行", () => {
  it("按时间点聚行且 7 天共享任务", async () => {
    const { api } = mountPanorama();
    await flushPromises();
    await flushPromises();
    const times = api.timeRows.value.map(r => r.time);
    expect(times).toEqual(["06:30", "09:00", "22:00"]);
    for (const row of api.timeRows.value) {
      expect(row.cells).toHaveLength(7);
    }
    // 06:30 行每个单元格各一枚构建芯片
    const first = api.timeRows.value[0];
    expect(first.cells[0].tasks).toHaveLength(1);
    expect(first.cells[0].tasks[0]).toMatchObject({
      kind: "build",
      stageLabel: "构建",
      name: "早间回归",
      branchName: "27A-master"
    });
    // 09:00 行为推送芯片（虚线描边语义由展示层决定）
    const pushRow = api.timeRows.value[1];
    expect(pushRow.cells[0].tasks[0]).toMatchObject({
      kind: "push",
      stageLabel: "推送"
    });
  });

  it("过期标记：过去日期的单元格 past=true", async () => {
    // 以很旧的周起点加载，全部单元格均应过期
    weeklyMock.mockResolvedValue(
      makeWeekly({
        week_start: "2020-01-06",
        days: [
          { date: "2020-01-06", weekday: "周一" },
          { date: "2020-01-07", weekday: "周二" },
          { date: "2020-01-08", weekday: "周三" },
          { date: "2020-01-09", weekday: "周四" },
          { date: "2020-01-10", weekday: "周五" },
          { date: "2020-01-11", weekday: "周六" },
          { date: "2020-01-12", weekday: "周日" }
        ]
      })
    );
    const { api } = mountPanorama();
    await flushPromises();
    await flushPromises();
    api.weekStart.value = "2020-01-06";
    await flushPromises();
    await flushPromises();
    expect(api.timeRows.value.every(r => r.cells.every(c => c.past))).toBe(
      true
    );
  });
});

describe("useWeeklyPanorama 任务点击分发", () => {
  const buildTask = {
    key: "b-101",
    strategyId: 101,
    kind: "build" as const,
    stageLabel: "构建",
    name: "早间回归",
    time: "06:30",
    title: "t",
    color: "#f59e0b",
    branchName: "27A-master",
    templateName: "冒烟A"
  };

  it("admin → 编辑（按需拉取 /strategies 补全）", async () => {
    setUser("admin");
    strategiesMock.mockResolvedValue([
      {
        id: 101,
        name: "早间回归",
        template_id: 7,
        branch_id: 11,
        build_start_time: "06:30",
        push_mode: "sync",
        push_start_time: "09:00",
        enabled: true
      }
    ] as never);
    const { api } = mountPanorama();
    await flushPromises();
    await flushPromises();
    const result = await api.resolveTaskClick(buildTask, false);
    expect(result).toMatchObject({ kind: "edit" });
    expect(strategiesMock).toHaveBeenCalledWith({ version_id: 1 });
    if (result?.kind === "edit") expect(result.detail.id).toBe(101);
  });

  it("无权限角色 → 借用申请", async () => {
    setUser("builder");
    const { api } = mountPanorama();
    await flushPromises();
    await flushPromises();
    const result = await api.resolveTaskClick(buildTask, false);
    expect(result?.kind).toBe("borrow");
    if (result?.kind === "borrow") {
      expect(result.strategy.strategy_id).toBe(101);
      expect(result.strategy.version_name).toBe("27A");
    }
    expect(strategiesMock).not.toHaveBeenCalled();
  });

  it("过期任务 → 只读详情（任何角色一致）", async () => {
    setUser("admin");
    const { api } = mountPanorama();
    await flushPromises();
    await flushPromises();
    const result = await api.resolveTaskClick(buildTask, true);
    expect(result?.kind).toBe("detail");
  });

  it("pm 未绑定该版本时只读，绑定后可编辑", async () => {
    setUser("pm", 2);
    const { api } = mountPanorama();
    await flushPromises();
    await flushPromises();
    // 查看版本 1（pm 绑定 2）→ 借用
    expect((await api.resolveTaskClick(buildTask, false))?.kind).toBe("borrow");
    // 切到绑定版本 2 → 编辑
    strategiesMock.mockResolvedValue([
      {
        id: 101,
        name: "早间回归",
        template_id: 7,
        branch_id: 11,
        build_start_time: "06:30",
        push_mode: "sync",
        push_start_time: "09:00",
        enabled: true
      }
    ] as never);
    api.versionId.value = 2;
    await flushPromises();
    await flushPromises();
    expect((await api.resolveTaskClick(buildTask, false))?.kind).toBe("edit");
  });
});
