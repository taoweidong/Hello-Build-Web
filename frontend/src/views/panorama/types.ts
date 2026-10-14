// 调度全景域：类型定义（5 个布局共用的同构事件契约）
// 依据：docs/superpowers/specs/2026-10-12-scheduling-panorama-design.md §5.1.1
// 三条互不关联的调度体系（策略时间线 / 时段抢占 / 借用电子流）在此归约为同一结构，
// 布局层只消费 ScheduleEvent[]，不再直接触碰业务 API。
import type { BorrowFlowItem } from "@/api/borrowFlow";
import type { PanoramaTodos } from "@/api/panorama";
import type { CalendarDayCell, SlotTemplateItem } from "@/api/slotBooking";
import type { WeeklyStrategy } from "@/api/types";
import type { ComputedRef, Ref } from "vue";

/** 事件来源：三条互无外键关联的调度体系 */
export type ScheduleSource = "strategy" | "slot" | "borrow";

/** 展示粒度：策略四阶段 / 时段占位 / 借用电子流 */
export type ScheduleKind =
  "build" | "smoke" | "analysis" | "push" | "slot" | "borrow";

/**
 * 六动作能力位：归源时一次性算好，页面只做布尔判断。
 * 注意：隐藏入口只是体验层，后端每个写接口仍独立校验。
 */
export interface SchedulePermissions {
  /** A 修改策略（canEditPanorama 且非 past） */
  canEdit: boolean;
  /** B 发起借用（无编辑权限且非 past） */
  canBorrow: boolean;
  /** C 抢占（非 past、时段空闲、在可抢窗口内） */
  canOccupy: boolean;
  /** C 释放本人抢占 */
  canRelease: boolean;
  /** C 释放他人抢占（仅 admin，原因必填） */
  canReleaseOthers: boolean;
  /** D 借用审批（通过/驳回） */
  canApprove: boolean;
  /** E 撤销借用申请（P2-R1：仅借用人本人 + 仅待审批） */
  canCancel: boolean;
  /** F 抢占改期（P2-R2：仅 reserved，本人或 admin） */
  canReschedule: boolean;
}

/** 原始载荷：定位弹窗预填与详情展示，页面不得反向依赖来源字段 */
export type ScheduleRaw =
  | {
      type: "strategy";
      data: WeeklyStrategy;
      /** 策略 id（WeeklyStrategy.strategy_id 的显式别名，避免布局层记混） */
      strategyId: number;
    }
  | {
      type: "slot";
      data: CalendarDayCell & { date: string };
      template: SlotTemplateItem;
    }
  | { type: "borrow"; data: BorrowFlowItem };

/** 三条来源归约后的最小渲染单元 —— 5 个布局的唯一输入 */
export interface ScheduleEvent {
  /**
   * 稳定 key，全局唯一（同策略每日循环，必须带日期，否则 S4 跨天渲染撞 key）：
   * `strategy:{strategy_id}#{date}#{kind}` / `slot:{date}:{template_id}` / `borrow:{flow_id}`
   */
  id: string;
  source: ScheduleSource;
  kind: ScheduleKind;
  /** 归属日 "YYYY-MM-DD" */
  date: string;
  /** 起止 "HH:mm"（跨午夜时段后端明确不支持，故恒同日） */
  time: string;
  endTime: string;
  /** end - start（甘特宽度 / 流水行高；点事件为 0） */
  durationMin: number;
  title: string;
  subtitle: string;
  branchId: number | null;
  branchName: string;
  versionId: number | null;
  versionName: string;
  /** 分支色(策略) / 模板色(抢占) / 状态色(借用) */
  color: string;
  /** 原始枚举：normal|sync|reserved|available|pending|approved|rejected */
  status: string;
  /** 中文文案，唯一来源 views/constants.ts */
  statusText: string;
  /** isPastSlot 惰性判定（过期只读） */
  past: boolean;
  /** is_mine / borrower 本人 */
  mine: boolean;
  permissions: SchedulePermissions;
  raw: ScheduleRaw;
}

/** 布局无关的一天（替代 useWeeklyPanorama 固定 7 天的 weekDays） */
export interface ScheduleDay {
  date: string;
  weekday: string;
  isToday: boolean;
  isPast: boolean;
}

/** 中枢入参：闭区间日期范围 + 筛选条件（空 = 全部） */
export interface ScheduleQuery {
  dateFrom: string;
  dateTo: string;
  versionId?: number;
  branchIds?: number[];
  scope?: "all" | "mine";
}

/** 聚合指标（S1 消费） */
export interface ScheduleKpi {
  todayBuild: number;
  weekSlotOccupied: number;
  weekSlotTotal: number;
  pendingBorrow: number;
  mySlots: number;
  conflictCount: number;
  occupancyRate: number;
}

/** 流水推进器（S4/S5 消费的有序列表项） */
export interface AgendaItem {
  id: string;
  source: ScheduleSource;
  kind: ScheduleKind;
  date: string;
  time: string;
  endTime: string;
  durationMin: number;
  title: string;
  subtitle: string;
  branchName: string;
  versionName: string;
  color: string;
  statusText: string;
  past: boolean;
  mine: boolean;
  permissions: SchedulePermissions;
}

/** 中枢输出（响应式引用，布局层在模板中自动解包） */
export interface ScheduleData {
  loading: Ref<boolean>;
  lastLoadedAt: Ref<Date | null>;
  days: Ref<ScheduleDay[]>;
  events: Ref<ScheduleEvent[]>;
  byDay: ComputedRef<Record<string, ScheduleEvent[]>>;
  agenda: ComputedRef<AgendaItem[]>;
  kpi: ComputedRef<ScheduleKpi>;
  versionOptions: ComputedRef<
    Array<{ version_id: number; version_name: string }>
  >;
  branchOptions: ComputedRef<Array<{ branch_id: number; branch_name: string }>>;
  templates: ComputedRef<SlotTemplateItem[]>;
  horizonDays: Ref<number>;
  /**
   * 服务端待办聚合（跨筛选准确）。为 null 表示接口不可用或尚未返回，
   * 页面据此回退前端聚合（`selectors.buildKpi`）——降级不阻断渲染。
   */
  todos: Ref<PanoramaTodos | null>;
  /**
   * 查询范围超过 3 个自然月：抢占矩阵仅覆盖前 3 个月（请求放大保护），
   * 画布层据此显式提示「范围过大」，避免用户把缺失误读为「无抢占」（R4-F13）。
   */
  slotTruncated: Ref<boolean>;
  /**
   * 手动/查询变更刷新。`silent` 供中枢轮询透传（后台请求不弹全局 toast）；
   * 返回是否成功——轮询据此决定退避计次。
   */
  refresh(silent?: boolean): Promise<boolean>;
}
