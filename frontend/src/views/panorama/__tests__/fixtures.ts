// 调度全景单测共用夹具：与真实 API 响应同构，禁止在用例里散落魔法字面量
import type { BorrowFlowItem } from "@/api/borrowFlow";
import type { PanoramaTodos } from "@/api/panorama";
import type { PlanVersion } from "@/api/plan";
import type {
  BookingItem,
  CalendarDayCell,
  SlotCalendarResponse,
  SlotTemplateItem
} from "@/api/slotBooking";
import type {
  PushMode,
  Timeline,
  WeeklyData,
  WeeklyStrategy
} from "@/api/types";
import type { ScheduleEvent, SchedulePermissions } from "../types";

/** 固定「现在」，让 isPastSlot 判定可复现 */
export const NOW = new Date("2026-10-13T10:00:00");

/** 中枢测试固定的查询范围（2026-10-12 周一 ~ 10-18 周日，单自然月） */
export const WEEK_FROM = "2026-10-12";
export const WEEK_TO = "2026-10-18";

/** 周视图骨架响应（GET /api/weekly） */
export function makeWeeklyData(over: Partial<WeeklyData> = {}): WeeklyData {
  return {
    week_start: WEEK_FROM,
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
      { branch_id: 10, branch_name: "main" },
      { branch_id: 11, branch_name: "release" }
    ],
    strategies: [makeStrategy()],
    ...over
  };
}

/**
 * 一周的时段矩阵：默认 10-13 有一条本人 reserved（分支 11），其余日期空闲。
 * `reservedDate: null` → 全空闲（用于模拟批量释放后的下一轮拉取）。
 */
export function makeWeekCalendar(
  opts: { reservedDate?: string | null } = {}
): SlotCalendarResponse {
  const reservedDate =
    opts.reservedDate === undefined ? "2026-10-13" : opts.reservedDate;
  const days: Record<string, CalendarDayCell[]> = {};
  for (const date of [
    "2026-10-12",
    "2026-10-13",
    "2026-10-14",
    "2026-10-15",
    "2026-10-16",
    "2026-10-17",
    "2026-10-18"
  ]) {
    days[date] =
      date === reservedDate
        ? [
            makeCell({
              status: "reserved",
              booking: makeBooking({
                is_mine: true,
                branch_id: 11,
                branch_name: "release"
              })
            })
          ]
        : [makeCell()];
  }
  return makeCalendar(days);
}

/** 甘特看板聚合（GET /api/plan）：锚点日 10-12 的四阶段区间 */
export function makePlanVersions(): PlanVersion[] {
  return [
    {
      version_id: 1,
      version_name: "27A",
      branches: [
        {
          branch_id: 10,
          branch_name: "main",
          strategies: [
            {
              id: 1,
              name: "主链路策略",
              push_mode: "normal",
              build_start_time: "08:00",
              push_start_time: "18:00",
              enabled: true,
              timeline: makeTimeline(WEEK_FROM)
            }
          ]
        }
      ]
    }
  ];
}

export function makeStrategy(
  over: Partial<WeeklyStrategy> = {}
): WeeklyStrategy {
  return {
    strategy_id: 1,
    strategy_name: "主链路策略",
    branch_id: 10,
    branch_name: "main",
    build_start_time: "08:00",
    push_start_time: "18:00",
    push_mode: "normal" as PushMode,
    template_name: "标准模板",
    ...over
  };
}

/** 锚点日四阶段区间（绝对时间，start/end 形如 YYYY-MM-DDTHH:mm:ss） */
export function makeTimeline(
  date = "2026-10-13",
  over: Partial<
    Record<
      "build" | "smoke" | "analysis" | "push",
      { start: string; end: string } | null
    >
  > = {}
): Timeline {
  return {
    build: { start: `${date}T08:00:00`, end: `${date}T08:30:00` },
    smoke: { start: `${date}T08:30:00`, end: `${date}T09:00:00` },
    analysis: { start: `${date}T09:00:00`, end: `${date}T09:30:00` },
    push: { start: `${date}T18:00:00`, end: `${date}T18:20:00` },
    ...over
  };
}

export function makeTemplate(
  over: Partial<SlotTemplateItem> = {}
): SlotTemplateItem {
  return {
    id: 1,
    name: "早间窗口",
    start_time: "09:00",
    end_time: "10:00",
    weekdays: "1,2,3,4,5",
    effective_from: null,
    effective_to: null,
    color: "#409eff",
    sort_order: 0,
    enabled: true,
    ...over
  };
}

export function makeBooking(over: Partial<BookingItem> = {}): BookingItem {
  return {
    id: 100,
    status: "reserved",
    user_name: "张三",
    purpose: "集成验证",
    version_id: 3,
    version_name: "v3.2",
    branch_id: 20,
    branch_name: "release",
    is_mine: false,
    created_at: "2026-10-10T09:00:00",
    ...over
  };
}

export function makeCell(over: Partial<CalendarDayCell> = {}): CalendarDayCell {
  return { template_id: 1, status: "available", booking: null, ...over };
}

export function makeCalendar(
  days: Record<string, CalendarDayCell[]>,
  templates: SlotTemplateItem[] = [makeTemplate()],
  horizon_days = 60
): SlotCalendarResponse {
  return { month: "2026-10", horizon_days, templates, days };
}

export function makeBorrowFlow(
  over: Partial<BorrowFlowItem> = {}
): BorrowFlowItem {
  return {
    id: 500,
    strategy_id: 1,
    strategy_name: "主链路策略",
    source_version_id: 3,
    source_version_name: "v3.2",
    source_branch_id: 10,
    source_branch_name: "main",
    template_name: "标准模板",
    original_build_time: "08:00",
    borrower_id: 7,
    borrower_name: "李四",
    target_version_id: 4,
    target_version_name: "v4.0",
    target_branch_id: 21,
    target_branch_name: "feature-x",
    new_build_time: "2026-10-14T09:30:00",
    reason: "赶版本窗口",
    status: "pending",
    approver_name: null,
    handle_comment: "",
    handled_at: null,
    cancelled_at: null,
    created_at: "2026-10-13T09:15:00",
    ...over
  };
}

/** 待办聚合响应（GET /api/panorama/todos）：默认与 borrowMock 的 1 条 pending 对齐 */
export function makeTodos(over: Partial<PanoramaTodos> = {}): PanoramaTodos {
  return {
    pending_approval: 1,
    my_reserved_slots: 1,
    my_pending_borrows: 1,
    ...over
  };
}

/** 全放开权限包（用例按需覆盖单个位） */ export const FULL_PERMISSIONS: SchedulePermissions =
  {
    canEdit: true,
    canBorrow: true,
    canOccupy: true,
    canRelease: true,
    canReleaseOthers: true,
    canApprove: true,
    canCancel: true,
    canReschedule: true
  };

export function makeEvent(over: Partial<ScheduleEvent> = {}): ScheduleEvent {
  return {
    id: "strategy:1#build",
    source: "strategy",
    kind: "build",
    date: "2026-10-13",
    time: "08:00",
    endTime: "08:30",
    durationMin: 30,
    title: "构建 · 主链路策略",
    subtitle: "main · 标准模板 · 正常流程",
    branchId: 10,
    branchName: "main",
    versionId: 3,
    versionName: "v3.2",
    color: "#3b82f6",
    status: "normal",
    statusText: "构建",
    past: false,
    mine: false,
    permissions: { ...FULL_PERMISSIONS },
    raw: { type: "strategy", data: makeStrategy(), strategyId: 1 },
    ...over
  };
}
