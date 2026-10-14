// 调度全景数据中枢：三源编排 → 同构 ScheduleEvent[]
// 依据：docs/superpowers/specs/2026-10-12-scheduling-panorama-design.md §5.1.2~5.1.3
//
// 定位：布局无关。5 个布局页面只消费本 composable 的输出，不直接 import 业务 API。
// 原 useWeeklyPanorama 保留不动（/weekly-new 回归基线 + 回滚兜底）。
//
// 纪律：
// - 自增序号守卫：快速切换范围/版本时丢弃过期响应；
// - 版本兜底：weekly 未传 version_id 时返回空策略，自动回填首个版本后二次拉取；
// - 轮询退避 / document.hidden 暂停 / silent 请求 / 卸载守卫：
//   设计文档原计划「由展示层各自接入」，实测那会让 5 个布局各复制一份
//   定时器 + visibilitychange + onBeforeUnmount 逻辑（branch-config 页正是
//   因漏了卸载守卫出过僵尸轮询 R3-F1）。故收敛到中枢一处实现，布局页不再
//   各自接线（原 `autoRefreshMs` opt-out 选项从无生产调用方，按 YAGNI 删除，R4-F13）。
import {
  computed,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
  type Ref
} from "vue";
import dayjs from "dayjs";
import { getWeekly } from "@/api/weekly";
import { getSlotCalendar, type SlotCalendarResponse } from "@/api/slotBooking";
import { getPlan, type PlanVersion } from "@/api/plan";
import { listBorrowFlows } from "@/api/borrowFlow";
import { getPanoramaTodos, type PanoramaTodos } from "@/api/panorama";
import type { Timeline, WeeklyData } from "@/api/types";
import { getCurrentUser } from "@/utils/business";
// 周一计算与中文星期数组唯一来源（R4-F6/F9：删除本地 weekMondayOf 与 WEEKDAY_CN_MON 副本）
import { buildDateRange, mondayOf, WEEKDAY_CN_MON } from "@/utils/week";
// 默认可抢窗口唯一来源（R4-F13/F-L4：删除本地副本，与 slot-booking 页同源）
import { DEFAULT_HORIZON_DAYS } from "@/views/constants";
import { POLL_BASE_MS, pollDelay } from "@/utils/polling";
import { useBranchColors } from "@/composables/useBranchColors";
import { mapStrategyEvents } from "./sources/strategySource";
import { mapSlotEvents } from "./sources/slotSource";
import { mapBorrowEvents } from "./sources/borrowSource";
import { buildAgenda, buildKpi, groupByDay, sortEvents } from "./selectors";
import type {
  ScheduleData,
  ScheduleDay,
  ScheduleEvent,
  ScheduleQuery
} from "./types";

/**
 * 范围内涉及的自然月（去重，最多 3 个，避免范围过大导致请求放大）。
 * truncated 标记范围超过 3 个自然月（R4-F13/F-L7）：第 4 个月起抢占矩阵静默
 * 缺失曾让用户误读为「无抢占」，画布层据 slotTruncated 显式提示。
 */
export function monthsOf(
  from: string,
  to: string
): { months: string[]; truncated: boolean } {
  const out: string[] = [];
  let cur = dayjs(from).startOf("month");
  const end = dayjs(to).startOf("month");
  while (cur.isBefore(end) || cur.isSame(end)) {
    out.push(cur.format("YYYY-MM"));
    cur = cur.add(1, "month");
  }
  return { months: out.slice(0, 3), truncated: out.length > 3 };
}

/** 构造布局无关的日期轴 */
export function buildScheduleDays(
  dateFrom: string,
  dateTo: string,
  today = dayjs().format("YYYY-MM-DD")
): ScheduleDay[] {
  return buildDateRange(dateFrom, dateTo).map(date => ({
    date,
    weekday: WEEKDAY_CN_MON[(dayjs(date).day() + 6) % 7],
    isToday: date === today,
    isPast: date < today
  }));
}

export function useScheduleData(query: Ref<ScheduleQuery>): ScheduleData {
  const loading = ref(false);
  const lastLoadedAt = ref<Date | null>(null);
  const events = ref<ScheduleEvent[]>([]);
  const weekly = ref<WeeklyData | null>(null);
  const calendars = ref<Record<string, SlotCalendarResponse>>({});
  const horizonDays = ref(DEFAULT_HORIZON_DAYS);
  /** 服务端待办聚合；接口不可用时保持 null，页面回退前端聚合 */
  const todos = ref<PanoramaTodos | null>(null);
  /** 查询范围超过 3 个自然月：抢占矩阵仅覆盖前 3 个月，画布层需显式提示（R4-F13） */
  const slotTruncated = ref(false);
  const user = getCurrentUser();

  const branches = computed(() => weekly.value?.branches ?? []);
  const { branchColor } = useBranchColors(branches);

  const days = computed(() =>
    buildScheduleDays(query.value.dateFrom, query.value.dateTo)
  );

  const versionOptions = computed(() => weekly.value?.versions ?? []);
  const branchOptions = computed(() =>
    (weekly.value?.branches ?? []).map(b => ({
      branch_id: b.branch_id,
      branch_name: b.branch_name
    }))
  );
  const templates = computed(() => {
    const map = new Map<number, SlotCalendarResponse["templates"][number]>();
    for (const c of Object.values(calendars.value)) {
      for (const t of c.templates) map.set(t.id, t);
    }
    return [...map.values()];
  });

  let seq = 0;

  /**
   * 拉取一次三源数据。
   * @param silent 轮询等后台请求传 true：后端故障时不弹全局 toast，失败仅用于退避计时
   * @returns 是否成功（序号守卫丢弃的迟到响应算成功——数据已被更新请求取代）
   */
  async function refresh(silent = false): Promise<boolean> {
    const current = ++seq;
    loading.value = true;
    const q = query.value;
    const today = dayjs().format("YYYY-MM-DD");
    const rangeDays = buildDateRange(q.dateFrom, q.dateTo);
    // 后台轮询不打扰用户；手动刷新 / 查询变更保持非 silent，让拦截器提示
    const cfg = silent ? { silent: true } : undefined;
    try {
      // 1) 策略骨架（weekly 未选版本时返回空策略，回填后由下方 watcher 二次拉取）
      const weeklyData = await getWeekly(
        {
          week_start: mondayOf(q.dateFrom),
          version_id: q.versionId
        },
        cfg
      );
      if (current !== seq) return true;
      weekly.value = weeklyData;
      if (!q.versionId && weeklyData.versions.length) {
        query.value = {
          ...q,
          versionId: weeklyData.versions[0].version_id
        };
        return true; // 版本变化触发 watcher 二次拉取
      }

      // 2) 时段抢占矩阵（按自然月聚合；超 3 个月截断并外化提示标记）
      const { months: monthList, truncated } = monthsOf(q.dateFrom, q.dateTo);
      const calendarList = await Promise.all(
        monthList.map(m => getSlotCalendar(m, cfg))
      );
      if (current !== seq) return true;
      slotTruncated.value = truncated;
      const calendarMap: Record<string, SlotCalendarResponse> = {};
      for (const c of calendarList) {
        calendarMap[c.month] = c;
        if (c.horizon_days) horizonDays.value = c.horizon_days;
      }
      calendars.value = calendarMap;

      // 3) 待审批借用（后端已按「与我相关」过滤）
      const flows = await listBorrowFlows("pending", cfg);
      if (current !== seq) return true;

      // 4) 待办聚合（跨筛选口径；失败静默降级——保留上次值，页面自行回退前端聚合）
      try {
        const todoData = await getPanoramaTodos(cfg);
        if (current === seq) todos.value = todoData;
      } catch {
        /* 降级：todos 维持旧值 */
      }

      // 5) 锚点日阶段区间（仅供策略事件补精确时长；失败静默降级为点事件）
      let planMap = new Map<number, Timeline>();
      try {
        const planList: PlanVersion[] = await getPlan(
          { date: q.dateFrom },
          cfg
        );
        if (current === seq) {
          for (const v of planList) {
            for (const b of v.branches) {
              for (const s of b.strategies) planMap.set(s.id, s.timeline);
            }
          }
        }
      } catch {
        planMap = new Map();
      }

      const horizonEnd = dayjs(today)
        .add(horizonDays.value, "day")
        .format("YYYY-MM-DD");

      const strategyEvents = mapStrategyEvents({
        strategies: weeklyData.strategies,
        days: rangeDays,
        planMap,
        branchColor,
        user,
        versionId: q.versionId
      });

      const slotEvents = Object.values(calendarMap).flatMap(c =>
        mapSlotEvents({ calendar: c, horizonEnd, today, user })
      );

      const borrowEvents = mapBorrowEvents({ flows, user });

      let all = sortEvents([...strategyEvents, ...slotEvents, ...borrowEvents]);
      // 分支筛选（空 = 全部）；无分支的事件（如借用锚定在目标分支上）按 branchId 过滤
      if (q.branchIds?.length) {
        all = all.filter(
          e => e.branchId === null || q.branchIds!.includes(e.branchId)
        );
      }
      // 仅看我的
      if (q.scope === "mine") all = all.filter(e => e.mine);

      events.value = all;
      lastLoadedAt.value = new Date();
      return true;
    } catch {
      // 失败已由 http 拦截器统一提示（silent 请求除外）
      return false;
    } finally {
      if (current === seq) loading.value = false;
    }
  }

  // ---------- 自动轮询（退避 + 隐藏暂停 + 卸载守卫，5 布局共用一处）----------
  let pollFailures = 0;
  // 注意：显式用 window.setTimeout（浏览器语义返回 number），
  // 不用全局 setTimeout——本仓库 @types/node 在，全局签名返回 NodeJS.Timeout
  let pollTimer: number | null = null;
  // 卸载守卫：在途请求 settle 后 finally 仍会排定时器，无此标记会自我续命
  // （离开页面后持续轮询直到关标签页的僵尸循环，参照 branch-config R3-F1）
  let disposed = false;

  function stopPoll() {
    if (pollTimer !== null) {
      window.clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  function schedulePoll() {
    if (disposed) return;
    stopPoll();
    // 后台标签页不打点，恢复可见时由 visibilitychange 立即补一次
    if (document.hidden) return;
    pollTimer = window.setTimeout(
      pollOnce,
      pollDelay(pollFailures, POLL_BASE_MS)
    );
  }

  async function pollOnce() {
    if (disposed) return;
    try {
      const ok = await refresh(true);
      pollFailures = ok ? 0 : pollFailures + 1;
    } catch {
      pollFailures += 1;
    } finally {
      schedulePoll();
    }
  }

  function onVisibilityChange() {
    if (document.hidden) {
      stopPoll();
    } else {
      pollFailures = 0;
      pollOnce();
    }
  }

  /**
   * 查询签名：口径没变就不重拉。
   * 布局常整体替换 query.value（{ ...query, branchIds }），若对 branchIds 用
   * deep watcher，Vue 3 下 effect 一重跑就触发（不比较值是否真变），
   * 一次筛选变更会发两遍请求。收敛为字符串签名后按内容比较，一次变更一次请求。
   */
  function querySignature(q: ScheduleQuery): string {
    return [
      q.dateFrom,
      q.dateTo,
      q.versionId ?? "",
      (q.branchIds ?? []).join(","),
      q.scope ?? ""
    ].join("|");
  }

  watch(
    () => querySignature(query.value),
    () => {
      // 查询口径变化：立即重拉并重置退避（用户刚操作过，下一轮按正常间隔来）。
      // 分支/范围筛选虽只影响投影，仍重新拉取——抢占/借用可见性以服务端返回为准。
      pollFailures = 0;
      refresh();
      schedulePoll();
    }
  );

  onMounted(() => {
    document.addEventListener("visibilitychange", onVisibilityChange);
    refresh().then(ok => {
      pollFailures = ok ? 0 : 1;
      schedulePoll();
    });
  });

  onBeforeUnmount(() => {
    // 先置卸载标记再清定时器：此后任何在途请求 settle 都不会复活轮询链
    disposed = true;
    document.removeEventListener("visibilitychange", onVisibilityChange);
    stopPoll();
  });

  return {
    loading,
    lastLoadedAt,
    days,
    events,
    byDay: computed(() => groupByDay(events.value)),
    agenda: computed(() => buildAgenda(events.value)),
    kpi: computed(() => buildKpi(events.value, dayjs().format("YYYY-MM-DD"))),
    versionOptions,
    branchOptions,
    templates,
    horizonDays,
    todos,
    slotTruncated,
    refresh
  };
}

/** 默认查询：本周一起始（布局可覆盖 dateFrom/dateTo） */
export function defaultWeekQuery(
  overrides: Partial<ScheduleQuery> = {}
): ScheduleQuery {
  const monday = mondayOf(dayjs().format("YYYY-MM-DD"));
  return {
    dateFrom: monday,
    dateTo: dayjs(monday).add(6, "day").format("YYYY-MM-DD"),
    ...overrides
  };
}
