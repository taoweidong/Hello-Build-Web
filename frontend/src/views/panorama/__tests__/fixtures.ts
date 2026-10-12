// 调度全景单测共用夹具：与真实 API 响应同构，禁止在用例里散落魔法字面量
import type { BorrowFlowItem } from "@/api/borrowFlow";
import type {
  BookingItem,
  CalendarDayCell,
  SlotCalendarResponse,
  SlotTemplateItem
} from "@/api/slotBooking";
import type { PushMode, Timeline, WeeklyStrategy } from "@/api/types";
import type { ScheduleEvent, SchedulePermissions } from "../types";

/** 固定「现在」，让 isPastSlot 判定可复现 */
export const NOW = new Date("2026-10-13T10:00:00");

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
    created_at: "2026-10-13T09:15:00",
    ...over
  };
}

/** 全放开权限包（用例按需覆盖单个位） */
export const FULL_PERMISSIONS: SchedulePermissions = {
  canEdit: true,
  canBorrow: true,
  canOccupy: true,
  canRelease: true,
  canReleaseOthers: true,
  canApprove: true
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
