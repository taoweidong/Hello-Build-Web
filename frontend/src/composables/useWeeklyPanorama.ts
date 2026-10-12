/**
 * 版本策略周报/全景数据 composable（weekly-new 与 weekly-report 两页共用）。
 *
 * 从原 weekly-new/index.vue 内联逻辑整体抽取（2026-10-12），行为保持一致：
 * 周导航、月周下拉、版本/分支筛选、时间点归行、过期判定、任务点击分发。
 * 两页只各自负责展示层，不再复制数据逻辑。
 */
import { computed, onMounted, ref, watch } from "vue";
import dayjs from "dayjs";
import { getWeekly } from "@/api/weekly";
import { getStrategies } from "@/api/strategy";
import type { WeeklyData, StrategyItem, WeeklyStrategy } from "@/api/types";
import { canEditPanorama, getCurrentUser, isPastSlot } from "@/utils/business";
import { buildMonthWeeks, isoWeek } from "@/utils/week";
import { useBranchColors } from "@/composables/useBranchColors";

/** 网格中的任务芯片（构建/推送阶段各一枚） */
export interface HourTaskItem {
  key: string;
  /** 所属策略 id（维护人员点击卡片进入编辑） */
  strategyId: number;
  kind: "build" | "push";
  stageLabel: string;
  name: string;
  time: string;
  title: string;
  color: string;
  /** 卡片补充信息：所属分支、冒烟模板 */
  branchName: string;
  templateName: string;
}

/** 单日单时刻单元格（过期判定在归行时逐格标记） */
export interface WeekCell {
  date: string;
  /** 该日该时刻是否已早于当前时间（过期历史任务：置灰删除线，仅可查看详情） */
  past: boolean;
  tasks: HourTaskItem[];
}

/** 任务点击分发结果：页面据此打开对应弹窗 */
export type TaskClickResult =
  | { kind: "detail"; strategy: WeeklyStrategy & { version_name?: string } }
  | { kind: "borrow"; strategy: WeeklyStrategy & { version_name?: string } }
  | { kind: "edit"; detail: StrategyItem };

export function useWeeklyPanorama() {
  const today = dayjs().format("YYYY-MM-DD");
  const thisWeekMonday = dayjs(today)
    .subtract((dayjs(today).day() + 6) % 7, "day")
    .format("YYYY-MM-DD");

  // ---- 周选择 ----
  const weekStart = ref(thisWeekMonday);
  const isCurrentWeek = computed(() => weekStart.value === thisWeekMonday);
  const weekEnd = computed(() =>
    weekDays.value.length
      ? weekDays.value[6].date
      : dayjs(weekStart.value).add(6, "day").format("YYYY-MM-DD")
  );
  const weekRangeText = computed(() => {
    const s = dayjs(weekStart.value);
    return `${s.format("YYYY年M月D日")} - ${dayjs(weekEnd.value).format(
      "M月D日"
    )}`;
  });

  // isoWeek/buildMonthWeeks 抽取到 utils/week（纯函数，单测锁定）
  const weekNumber = computed(() =>
    weekStart.value ? isoWeek(weekStart.value) : 0
  );

  function shiftWeek(delta: number) {
    weekStart.value = dayjs(weekStart.value)
      .add(delta * 7, "day")
      .format("YYYY-MM-DD");
  }

  function goThisWeek() {
    weekStart.value = thisWeekMonday;
  }

  /** 本月周列表（与原周视图同规则：本月第一个周一为第 1 周） */
  const monthWeeks = computed(() => buildMonthWeeks());

  const selectedWeek = ref(thisWeekMonday);
  watch(selectedWeek, value => {
    if (value && value !== weekStart.value) weekStart.value = value;
  });

  // ---- 数据源（版本/分支/策略，与原周视图一致）----
  const weekly = ref<WeeklyData | null>(null);
  const loading = ref(false);
  /** 最近一次成功加载时间（展示层可用于「更新于 HH:mm」） */
  const lastLoadedAt = ref<Date | null>(null);
  const versionId = ref<number | undefined>(undefined);

  const versionOptions = computed(() => weekly.value?.versions ?? []);
  const branches = computed(() => weekly.value?.branches ?? []);
  const strategies = computed(() => weekly.value?.strategies ?? []);
  const currentVersionName = computed(
    () =>
      versionOptions.value.find(v => v.version_id === versionId.value)
        ?.version_name ?? ""
  );

  // ---- 分支筛选：多选过滤网格与图例，空=全部 ----
  const branchFilter = ref<number[]>([]);
  const filteredStrategies = computed(() =>
    branchFilter.value.length
      ? strategies.value.filter(s => branchFilter.value.includes(s.branch_id))
      : strategies.value
  );
  /** 图例/统计随筛选联动：仅展示当前筛选到的分支 */
  const visibleBranches = computed(() =>
    branchFilter.value.length
      ? branches.value.filter(b => branchFilter.value.includes(b.branch_id))
      : branches.value
  );

  // 分支配色：固定色板、按 branch_id 稳定取色（与 weekly 共用）
  const { branchColor } = useBranchColors(branches);

  /** 列头 7 天：后端 weekly.py 直接返回中文星期（周一~周日），透传即可；?? 兜底防空值 */
  const weekDays = computed(() =>
    (weekly.value?.days ?? []).map(d => ({
      date: d.date,
      weekday: d.weekday ?? ""
    }))
  );

  /** 首次加载未选版本时，后端返回空分支/策略；自动回填第一个版本后由 watcher 二次拉取 */
  // 自增序号守卫：快速翻周/切版本时丢弃过期响应，避免慢响应覆盖新周数据
  let weeklySeq = 0;
  async function loadWeekly() {
    const seq = ++weeklySeq;
    loading.value = true;
    try {
      const data = await getWeekly({
        week_start: weekStart.value,
        version_id: versionId.value
      });
      if (seq !== weeklySeq) return; // 过期响应丢弃
      weekly.value = data;
      lastLoadedAt.value = new Date();
      if (!versionId.value && data.versions.length) {
        versionId.value = data.versions[0].version_id;
      }
    } catch {
      // 拦截器已提示
    } finally {
      if (seq === weeklySeq) loading.value = false;
    }
  }

  /** 任务卡片（按精确时间点归类：构建/推送起始时间相等才落行；受分支筛选过滤） */
  function tasksAtTime(t: string): HourTaskItem[] {
    const tasks: HourTaskItem[] = [];
    for (const s of filteredStrategies.value) {
      if (s.build_start_time === t) {
        tasks.push({
          key: `b-${s.strategy_id}`,
          strategyId: s.strategy_id,
          kind: "build",
          stageLabel: "构建",
          name: s.strategy_name,
          time: s.build_start_time,
          title: `构建 · ${s.strategy_name} · ${s.branch_name} · ${s.template_name} · ${s.build_start_time}`,
          color: branchColor(s.branch_id),
          branchName: s.branch_name,
          templateName: s.template_name
        });
      }
      if (s.push_start_time && s.push_start_time === t) {
        tasks.push({
          key: `p-${s.strategy_id}`,
          strategyId: s.strategy_id,
          kind: "push",
          stageLabel: "推送",
          name: s.strategy_name,
          time: s.push_start_time,
          title: `推送 · ${s.strategy_name} · ${s.branch_name} · ${s.template_name} · ${s.push_start_time}`,
          color: branchColor(s.branch_id),
          branchName: s.branch_name,
          templateName: s.template_name
        });
      }
    }
    return tasks;
  }

  /**
   * 时间点行：0:00~23:59 内仅渲染有任务的时间点，按时间升序（非线性铺满，无任务时段省略）。
   * 策略当前为每日循环，7 天共享同一组任务；结构按天独立，兼容将来每天时间点存在差异的情况。
   * 每格按「日期+时刻」判定是否已过期（早于当前时间）——过期为已完成的历史任务，置灰删除线、仅可查看详情。
   */
  const timeRows = computed(() => {
    const times = new Set<string>();
    for (const s of filteredStrategies.value) {
      times.add(s.build_start_time);
      if (s.push_start_time) times.add(s.push_start_time);
    }
    const now = new Date();
    return [...times].sort().map(t => {
      // 策略每日循环：同一时间点的任务数组 7 天内容一致，只构建一次共享引用
      //（旧实现每格各调一次 tasksAtTime，O(时间点×7×策略数) 重复构建，R3-F7；
      // 渲染输出不变——展示层只读该数组，逐格的 past 仍按日期独立判定）
      const tasks = tasksAtTime(t);
      return {
        time: t,
        cells: weekDays.value.map(d => ({
          date: d.date,
          past: isPastSlot(d.date, t, now),
          tasks
        }))
      };
    });
  });

  const stats = computed(() => ({
    tasks: filteredStrategies.value.length,
    branches: visibleBranches.value.length
  }));

  // ---- 编辑能力：外部人员只读，内部维护人员（admin / 绑定版本的 pm）可修改任意时间与信息 ----
  const currentUser = getCurrentUser();
  const canEdit = computed(() =>
    canEditPanorama(
      currentUser?.role,
      currentUser?.bound_version_id,
      versionId.value
    )
  );

  // 策略详情缓存（芯片点击时按需拉取 /strategies；weekly 契约不含 template_id/enabled）
  const strategyDetailList = ref<StrategyItem[] | null>(null);

  /** 保存后详情缓存失效（时间/启用状态可能变化） */
  function invalidateStrategyCache() {
    strategyDetailList.value = null;
  }

  /**
   * 任务点击分发（与页面解耦，返回页面应打开的弹窗类型）：
   * - 已过期 → 只读详情（任何角色一致）
   * - 无修改权限 → 详情 + 借用申请
   * - 维护人员 → 编辑（按需拉取 /strategies 补全 template_id/enabled）
   */
  async function resolveTaskClick(
    task: HourTaskItem,
    past: boolean
  ): Promise<TaskClickResult | null> {
    if (!versionId.value) return null;
    if (past) {
      const s =
        strategies.value.find(x => x.strategy_id === task.strategyId) ?? null;
      if (!s) return null;
      return {
        kind: "detail",
        strategy: { ...s, version_name: currentVersionName.value }
      };
    }
    if (!canEdit.value) {
      const s =
        strategies.value.find(x => x.strategy_id === task.strategyId) ?? null;
      if (!s) return null;
      return {
        kind: "borrow",
        strategy: { ...s, version_name: currentVersionName.value }
      };
    }
    if (!strategyDetailList.value) {
      try {
        strategyDetailList.value = await getStrategies({
          version_id: versionId.value
        });
      } catch {
        return null; // 拦截器已提示
      }
    }
    const detail =
      strategyDetailList.value.find(x => x.id === task.strategyId) ?? null;
    return detail ? { kind: "edit", detail } : null;
  }

  watch(weekStart, () => {
    selectedWeek.value = weekStart.value;
    loadWeekly();
  });
  watch(versionId, value => {
    // 版本变化（含首屏自动回填）都重新拉取，保证拿到该版本的分支与策略；分支 id 跨版本不同，重置筛选
    invalidateStrategyCache();
    branchFilter.value = [];
    if (value) loadWeekly();
  });

  onMounted(() => {
    loadWeekly();
  });

  return {
    // 周导航
    today,
    thisWeekMonday,
    weekStart,
    isCurrentWeek,
    weekEnd,
    weekRangeText,
    weekNumber,
    monthWeeks,
    selectedWeek,
    shiftWeek,
    goThisWeek,
    // 数据
    weekly,
    loading,
    lastLoadedAt,
    versionId,
    versionOptions,
    branches,
    strategies,
    currentVersionName,
    // 筛选
    branchFilter,
    filteredStrategies,
    visibleBranches,
    branchColor,
    // 网格
    weekDays,
    timeRows,
    stats,
    // 权限与交互
    currentUser,
    canEdit,
    loadWeekly,
    resolveTaskClick,
    invalidateStrategyCache
  };
}
