// 布局无关的纯投影：所有布局共用，禁止页面自行聚合
// 依据：docs/superpowers/specs/2026-10-12-scheduling-panorama-design.md §5.1（selectors 纯投影）
import type { ScheduleDay, ScheduleEvent, ScheduleKpi } from "./types";
import { durationOf } from "./sources/strategySource";

/** 按「日期 + 起止」升序排序（同日按 start，start 相同按 duration 降序） */
export function sortEvents(events: ScheduleEvent[]): ScheduleEvent[] {
  return [...events].sort((a, b) => {
    if (a.date !== b.date) return a.date < b.date ? -1 : 1;
    if (a.time !== b.time) return a.time < b.time ? -1 : 1;
    return b.durationMin - a.durationMin;
  });
}

/** 按日期分组（仅返回有事件的日期，布局自行决定是否补空日） */
export function groupByDay(
  events: ScheduleEvent[]
): Record<string, ScheduleEvent[]> {
  const out: Record<string, ScheduleEvent[]> = {};
  for (const e of sortEvents(events)) {
    (out[e.date] ||= []).push(e);
  }
  return out;
}

/** 区间是否重叠（分钟口径；起止相等的点事件按 1 分钟处理） */
function overlaps(
  aStart: string,
  aEnd: string,
  bStart: string,
  bEnd: string
): boolean {
  const aS = toMin(aStart);
  const aE = toMin(aEnd) > aS ? toMin(aEnd) : aS + 1;
  const bS = toMin(bStart);
  const bE = toMin(bEnd) > bS ? toMin(bEnd) : bS + 1;
  return aS < bE && bS < aE;
}

function toMin(v: string): number {
  const [h, m] = v.split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

/**
 * 跨源冲突：同一天内，策略时间点落在「已被抢占」的时段区间里（仅提示，不改后端互斥逻辑）。
 * 这是 P1-R3「策略与抢占同画布叠加」的纯函数基础，S1 告警与 S5 冲突徽标共用。
 */
export function detectCrossSourceConflicts(
  events: ScheduleEvent[]
): ScheduleEvent[] {
  const byDay = groupByDay(events);
  const conflicts: ScheduleEvent[] = [];
  for (const dayEvents of Object.values(byDay)) {
    const slots = dayEvents.filter(
      e => e.source === "slot" && e.status === "reserved"
    );
    if (!slots.length) continue;
    for (const e of dayEvents) {
      if (e.source !== "strategy") continue;
      const hit = slots.some(s =>
        overlaps(e.time, e.endTime, s.time, s.endTime)
      );
      if (hit) conflicts.push(e);
    }
  }
  return conflicts;
}

/** 聚合指标（S1 消费） */
export function buildKpi(events: ScheduleEvent[], today: string): ScheduleKpi {
  const slots = events.filter(e => e.source === "slot");
  const occupied = slots.filter(e => e.status === "reserved");
  const todayStrategy = events.filter(
    e => e.source === "strategy" && e.date === today
  );
  return {
    todayBuild: todayStrategy.filter(e => e.kind === "build").length,
    weekSlotOccupied: occupied.length,
    weekSlotTotal: slots.length,
    pendingBorrow: events.filter(e => e.source === "borrow").length,
    mySlots: occupied.filter(e => e.mine).length,
    conflictCount: detectCrossSourceConflicts(events).length,
    occupancyRate: slots.length
      ? Math.round((occupied.length / slots.length) * 100)
      : 0
  };
}

/** 同日事件的重叠分列（S2 甘特泳道 / S5 时间轴共用） */
export function lanePack(dayEvents: ScheduleEvent[]): {
  lanes: Map<string, number>;
  laneCount: number;
} {
  const lanes = new Map<string, number>();
  const laneEnds: number[] = [];
  for (const e of sortEvents(dayEvents)) {
    const start = toMin(e.time);
    const end = toMin(e.endTime) > start ? toMin(e.endTime) : start + 1;
    let placed = -1;
    for (let i = 0; i < laneEnds.length; i++) {
      if (laneEnds[i] <= start) {
        placed = i;
        break;
      }
    }
    if (placed === -1) {
      laneEnds.push(end);
      placed = laneEnds.length - 1;
    } else {
      laneEnds[placed] = end;
    }
    lanes.set(e.id, placed);
  }
  return { lanes, laneCount: Math.max(laneEnds.length, 1) };
}

/** 按分支分组（S4 分组看板 / S2 泳道消费） */
export function groupByBranch(events: ScheduleEvent[]): Array<{
  branchId: number | null;
  branchName: string;
  events: ScheduleEvent[];
}> {
  const map = new Map<string, ScheduleEvent[]>();
  for (const e of sortEvents(events)) {
    const key = `${e.branchId ?? "none"}`;
    (map.get(key) || map.set(key, []).get(key)!).push(e);
  }
  return [...map.entries()].map(([, list]) => ({
    branchId: list[0].branchId,
    branchName: list[0].branchName || "未关联分支",
    events: list
  }));
}

/** 时刻 × 星期 负载热力（S1 消费）：返回每个时刻每天的计数 */
export function buildHeatmap(
  events: ScheduleEvent[],
  days: ScheduleDay[],
  timePoints: string[]
): Array<{ time: string; counts: number[] }> {
  const dateIndex = new Map(days.map((d, i) => [d.date, i]));
  const rows = timePoints.map(time => ({ time, counts: days.map(() => 0) }));
  const rowIndex = new Map(timePoints.map((t, i) => [t, i]));
  for (const e of events) {
    const di = dateIndex.get(e.date);
    const ri = rowIndex.get(e.time);
    if (di === undefined || ri === undefined) continue;
    rows[ri].counts[di] += 1;
  }
  return rows;
}

/** 收集范围内出现过的全部时刻（升序去重） */
export function collectTimePoints(events: ScheduleEvent[]): string[] {
  return [...new Set(events.map(e => e.time))].sort();
}

export { durationOf };
