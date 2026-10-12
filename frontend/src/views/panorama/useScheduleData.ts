// 调度全景数据中枢：三源编排 → 同构 ScheduleEvent[]
// 依据：docs/superpowers/specs/2026-10-12-scheduling-panorama-design.md §5.1.2~5.1.3
//
// 定位：布局无关。5 个布局页面只消费本 composable 的输出，不直接 import 业务 API。
// 原 useWeeklyPanorama 保留不动（/weekly-new 回归基线 + 回滚兜底）。
//
// 纪律：
// - 自增序号守卫：快速切换范围/版本时丢弃过期响应；
// - 版本兜底：weekly 未传 version_id 时返回空策略，自动回填首个版本后二次拉取；
// - 轮询退避、document.hidden 暂停、silent 请求由展示层经 utils/polling 接入，
//   本中枢只暴露 refresh()，不自行定时。
import { computed, onMounted, ref, watch, type Ref } from "vue";
import dayjs from "dayjs";
import { getWeekly } from "@/api/weekly";
import { getSlotCalendar, type SlotCalendarResponse } from "@/api/slotBooking";
import { getPlan, type PlanVersion } from "@/api/plan";
import { listBorrowFlows } from "@/api/borrowFlow";
import type { Timeline, WeeklyData } from "@/api/types";
import { getCurrentUser } from "@/utils/business";
import { buildDateRange } from "@/utils/week";
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

/** 后端未返回 horizon_days 时的默认窗口（与 slot-booking 页口径一致） */
const DEFAULT_HORIZON_DAYS = 60;

/** 一周起点（周一） */
function weekMondayOf(dateStr: string): string {
  return dayjs(dateStr)
    .subtract((dayjs(dateStr).day() + 6) % 7, "day")
    .format("YYYY-MM-DD");
}

/** 范围内涉及的自然月（去重，最多 3 个，避免范围过大导致请求放大） */
function monthsOf(from: string, to: string): string[] {
  const out: string[] = [];
  let cur = dayjs(from).startOf("month");
  const end = dayjs(to).startOf("month");
  while (cur.isBefore(end) || cur.isSame(end)) {
    out.push(cur.format("YYYY-MM"));
    cur = cur.add(1, "month");
    if (out.length >= 3) break;
  }
  return out;
}

const WEEKDAY_CN_MON = [
  "周一",
  "周二",
  "周三",
  "周四",
  "周五",
  "周六",
  "周日"
] as const;

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

  async function refresh() {
    const current = ++seq;
    loading.value = true;
    const q = query.value;
    const today = dayjs().format("YYYY-MM-DD");
    const rangeDays = buildDateRange(q.dateFrom, q.dateTo);
    try {
      // 1) 策略骨架（weekly 未选版本时返回空策略，回填后由下方 watcher 二次拉取）
      const weeklyData = await getWeekly({
        week_start: weekMondayOf(q.dateFrom),
        version_id: q.versionId
      });
      if (current !== seq) return;
      weekly.value = weeklyData;
      if (!q.versionId && weeklyData.versions.length) {
        query.value = {
          ...q,
          versionId: weeklyData.versions[0].version_id
        };
        return; // 版本变化触发 watcher 二次拉取
      }

      // 2) 时段抢占矩阵（按自然月聚合）
      const monthList = monthsOf(q.dateFrom, q.dateTo);
      const calendarList = await Promise.all(
        monthList.map(m => getSlotCalendar(m))
      );
      if (current !== seq) return;
      const calendarMap: Record<string, SlotCalendarResponse> = {};
      for (const c of calendarList) {
        calendarMap[c.month] = c;
        if (c.horizon_days) horizonDays.value = c.horizon_days;
      }
      calendars.value = calendarMap;

      // 3) 待审批借用（后端已按「与我相关」过滤）
      const flows = await listBorrowFlows("pending");
      if (current !== seq) return;

      // 4) 锚点日阶段区间（仅供策略事件补精确时长；失败静默降级为点事件）
      let planMap = new Map<number, Timeline>();
      try {
        const planList: PlanVersion[] = await getPlan({ date: q.dateFrom });
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
    } catch {
      // 失败已由 http 拦截器统一提示
    } finally {
      if (current === seq) loading.value = false;
    }
  }

  watch(
    () => [query.value.dateFrom, query.value.dateTo, query.value.versionId],
    () => refresh()
  );
  watch(
    () => query.value.branchIds,
    () => {
      // 分支/范围筛选只影响已加载数据的投影，重新拉取以保持口径一致（抢占/借用可见性以服务端为准）
      refresh();
    },
    { deep: true }
  );
  watch(
    () => query.value.scope,
    () => refresh()
  );

  onMounted(refresh);

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
    refresh
  };
}

/** 默认查询：本周一起始（布局可覆盖 dateFrom/dateTo） */
export function defaultWeekQuery(
  overrides: Partial<ScheduleQuery> = {}
): ScheduleQuery {
  const monday = weekMondayOf(dayjs().format("YYYY-MM-DD"));
  return {
    dateFrom: monday,
    dateTo: dayjs(monday).add(6, "day").format("YYYY-MM-DD"),
    ...overrides
  };
}
