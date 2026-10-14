// 策略时间线 → ScheduleEvent[] 的纯映射（可单测）
// 数据源：GET /api/weekly（每日循环策略骨架）+ GET /api/plan（锚点日的精确阶段区间）
//
// 关键口径：
// - weekly 只给构建/推送起始时刻，不含阶段区间；锚点日的阶段区间由 /plan 的 timeline 补齐，
//   其余日期退化为「点事件」（durationMin = 0），**禁止前端按 build_minutes 硬算时长**
//   （会与 RuntimeConfig 漂移）。
// - 过期判定走 isPastSlot（惰性，无 expired 枚举）。
import type { Role, Timeline, WeeklyStrategy } from "@/api/types";
// 权限判定唯一来源（R4-F8/F-M6：不再手写 admin || (pm && bound===versionId) 同构逻辑）
import { canEditPanorama, isPastSlot } from "@/utils/business";
import { pushModeMeta } from "@/views/constants";
import { STAGE_COLORS } from "@/components/gantt/types";
import type { ScheduleEvent, SchedulePermissions } from "../types";

/** 阶段顺序与展示名（与 STAGE_COLORS 对齐） */
const PHASES: Array<{
  key: keyof Timeline;
  kind: ScheduleEvent["kind"];
  label: string;
}> = [
  { key: "build", kind: "build", label: "构建" },
  { key: "smoke", kind: "smoke", label: "冒烟" },
  { key: "analysis", kind: "analysis", label: "分析" },
  { key: "push", kind: "push", label: "推送" }
];

export interface MapStrategyOptions {
  strategies: WeeklyStrategy[];
  /** 需要生成事件的日期列表 "YYYY-MM-DD"（通常来自中枢的日期范围） */
  days: string[];
  /** 锚点日的阶段区间：strategyId → Timeline（来自 GET /api/plan?date=锚点日） */
  planMap: Map<number, Timeline>;
  /** 分支配色（useBranchColors.branchColor） */
  branchColor: (branchId: number) => string;
  /** 当前登录用户（权限包计算） */
  user: { role?: string; bound_version_id?: number } | null;
  /** 策略所属版本 id（版本筛选已由 weekly 入参完成，此处用于权限判定） */
  versionId: number | undefined;
  now?: Date;
}

/** 权限包：策略来源只涉及「修改 / 借用」，不可抢占/释放/审批 */
function permissionsOf(
  strategy: WeeklyStrategy,
  past: boolean,
  user: MapStrategyOptions["user"],
  versionId: number | undefined
): SchedulePermissions {
  // canEditPanorama 与后端策略写路径角色门槛对齐（有独立单测）；过期只读在前置
  const canEdit =
    !past &&
    canEditPanorama(
      user?.role as Role | undefined,
      user?.bound_version_id,
      versionId
    );
  return {
    canEdit,
    canBorrow: !past && !canEdit,
    canOccupy: false,
    canRelease: false,
    canReleaseOthers: false,
    canApprove: false,
    canCancel: false,
    canReschedule: false
  };
}

/** 单条策略在锚点日展开为四阶段事件（push 为空则三个阶段） */
function phaseEvents(
  strategy: WeeklyStrategy,
  date: string,
  timeline: Timeline,
  opts: MapStrategyOptions,
  now: Date
): ScheduleEvent[] {
  const color = STAGE_COLORS.build;
  const permissions = permissionsOf(strategy, false, opts.user, opts.versionId);
  return PHASES.flatMap(p => {
    const range = timeline[p.key];
    if (!range) return [];
    const time = String(range.start).slice(11, 16);
    const endTime = String(range.end).slice(11, 16);
    return [
      {
        id: `strategy:${strategy.strategy_id}#${date}#${p.kind}`,
        source: "strategy" as const,
        kind: p.kind,
        date,
        time,
        endTime,
        durationMin: durationOf(time, endTime),
        title: `${p.label} · ${strategy.strategy_name}`,
        subtitle: `${strategy.branch_name} · ${strategy.template_name}`,
        branchId: strategy.branch_id,
        branchName: strategy.branch_name,
        versionId: opts.versionId ?? null,
        versionName: "",
        color: STAGE_COLORS[p.key] ?? color,
        status: strategy.push_mode,
        statusText: p.label,
        past: isPastSlot(date, time, now),
        mine: false,
        permissions,
        raw: {
          type: "strategy" as const,
          data: strategy,
          strategyId: strategy.strategy_id
        }
      }
    ];
  });
}

/** 分钟差（HH:mm），跨午夜不出现（后端禁止跨天时段） */
export function durationOf(time: string, endTime: string): number {
  const toMin = (v: string) => {
    const [h, m] = v.split(":").map(Number);
    return (h || 0) * 60 + (m || 0);
  };
  const diff = toMin(endTime) - toMin(time);
  return diff > 0 ? diff : 0;
}

/** 策略时间线 → 事件（纯函数，布局层与单测共用） */
export function mapStrategyEvents(opts: MapStrategyOptions): ScheduleEvent[] {
  const now = opts.now ?? new Date();
  const out: ScheduleEvent[] = [];
  for (const s of opts.strategies) {
    const timeline = opts.planMap.get(s.strategy_id);
    for (const date of opts.days) {
      const pastBuild = isPastSlot(date, s.build_start_time, now);
      if (timeline && date === opts.days[0]) {
        // 锚点日：展开为 build/smoke/analysis/push 四阶段（区间来自服务端）
        out.push(...phaseEvents(s, date, timeline, opts, now));
        continue;
      }
      const permissions = permissionsOf(
        s,
        pastBuild,
        opts.user,
        opts.versionId
      );
      out.push({
        id: `strategy:${s.strategy_id}#${date}#build`,
        source: "strategy",
        kind: "build",
        date,
        time: s.build_start_time,
        endTime: s.build_start_time,
        durationMin: 0,
        title: `构建 · ${s.strategy_name}`,
        subtitle: `${s.branch_name} · ${s.template_name} · ${
          pushModeMeta(s.push_mode).label
        }`,
        branchId: s.branch_id,
        branchName: s.branch_name,
        versionId: opts.versionId ?? null,
        versionName: "",
        color: opts.branchColor(s.branch_id),
        status: s.push_mode,
        statusText: "构建",
        past: pastBuild,
        mine: false,
        permissions,
        raw: { type: "strategy", data: s, strategyId: s.strategy_id }
      });
      if (s.push_start_time) {
        out.push({
          id: `strategy:${s.strategy_id}#${date}#push`,
          source: "strategy",
          kind: "push",
          date,
          time: s.push_start_time,
          endTime: s.push_start_time,
          durationMin: 0,
          title: `推送 · ${s.strategy_name}`,
          subtitle: `${s.branch_name} · ${pushModeMeta(s.push_mode).label}`,
          branchId: s.branch_id,
          branchName: s.branch_name,
          versionId: opts.versionId ?? null,
          versionName: "",
          color: opts.branchColor(s.branch_id),
          status: s.push_mode,
          statusText: "推送",
          past: isPastSlot(date, s.push_start_time, now),
          mine: false,
          permissions,
          raw: { type: "strategy", data: s, strategyId: s.strategy_id }
        });
      }
    }
  }
  return out;
}
