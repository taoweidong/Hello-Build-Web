// 时段抢占 → ScheduleEvent[] 的纯映射（可单测）
// 数据源：GET /api/slot-calendar?month=YYYY-MM（单次聚合整月矩阵）
//
// 口径：过期不落库，由 isPastSlot 惰性判定；可抢窗口由服务端 horizon_days 下发，
// 前端不硬编码 60；他人/本人释放口径与 services/slot_booking.release_booking 一致。
import type {
  CalendarDayCell,
  SlotCalendarResponse,
  SlotTemplateItem
} from "@/api/slotBooking";
import { isPastSlot } from "@/utils/business";
import { bookingStatusMeta } from "@/views/constants";
import type { ScheduleEvent, SchedulePermissions } from "../types";

export interface MapSlotOptions {
  calendar: SlotCalendarResponse;
  /** 可抢窗口截止日 "YYYY-MM-DD"（由 horizon_days 推导） */
  horizonEnd: string;
  today: string;
  user: { role?: string } | null;
  now?: Date;
}

/** 单格权限包：抢占/释放本人/释放他人（admin） */
function permissionsOf(
  cell: CalendarDayCell,
  date: string,
  template: SlotTemplateItem,
  opts: MapSlotOptions
): SchedulePermissions {
  const past = isPastSlot(date, template.end_time, opts.now);
  const available = cell.status === "available";
  const reserved = cell.status === "reserved";
  const mine = cell.booking?.is_mine === true;
  const isAdmin = opts.user?.role === "admin";
  return {
    canEdit: false,
    canBorrow: false,
    canOccupy:
      !past && available && date >= opts.today && date <= opts.horizonEnd,
    canRelease: reserved && mine,
    canReleaseOthers: reserved && !mine && isAdmin,
    canApprove: false,
    canCancel: false,
    // 改期口径与后端 reschedule_booking 一致：只要求 reserved + （本人或 admin），
    // 不额外排除已过期行（历史记录改到未来是补救操作，后端同样放行）。
    canReschedule: reserved && (mine || isAdmin)
  };
}

/** 时段抢占 → 事件（纯函数） */
export function mapSlotEvents(opts: MapSlotOptions): ScheduleEvent[] {
  const out: ScheduleEvent[] = [];
  const templateMap = new Map<number, SlotTemplateItem>();
  for (const t of opts.calendar.templates) templateMap.set(t.id, t);

  for (const [date, cells] of Object.entries(opts.calendar.days)) {
    for (const cell of cells) {
      const template = templateMap.get(cell.template_id);
      if (!template) continue; // 模板已被删除/停用的历史记录不渲染
      const reserved = cell.status === "reserved";
      const mine = cell.booking?.is_mine === true;
      out.push({
        id: `slot:${date}:${cell.template_id}`,
        source: "slot",
        kind: "slot",
        date,
        time: template.start_time,
        endTime: template.end_time,
        durationMin: durationOf(template.start_time, template.end_time),
        title: template.name,
        subtitle: reserved
          ? mine
            ? "我的抢占"
            : `${cell.booking?.user_name ?? "他人"} · ${cell.booking?.purpose ?? ""}`
          : "空闲可抢占",
        branchId: cell.booking?.branch_id ?? null,
        branchName: cell.booking?.branch_name ?? "",
        versionId: cell.booking?.version_id ?? null,
        versionName: cell.booking?.version_name ?? "",
        color: template.color,
        status: cell.status,
        statusText: bookingStatusMeta(cell.status).text,
        past: isPastSlot(date, template.end_time, opts.now),
        mine,
        permissions: permissionsOf(cell, date, template, opts),
        raw: { type: "slot", data: { ...cell, date }, template }
      });
    }
  }
  return out;
}

/** 分钟差（HH:mm） */
function durationOf(time: string, endTime: string): number {
  const toMin = (v: string) => {
    const [h, m] = v.split(":").map(Number);
    return (h || 0) * 60 + (m || 0);
  };
  const diff = toMin(endTime) - toMin(time);
  return diff > 0 ? diff : 0;
}
