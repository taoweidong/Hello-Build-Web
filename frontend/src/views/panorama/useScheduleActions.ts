// 调度全景域：六动作总线（edit / borrow / occupy / release / approve / reject）
// 依据：docs/superpowers/specs/2026-10-12-scheduling-panorama-design.md §5.1.3
//
// 纪律（设计文档 §4.0「禁止事项」）：
// - 布局层不得直接 import 业务 API，一律走本总线；
// - 权限只做布尔判断，后端每个写接口独立校验（隐藏 ≠ 可靠）；
// - 成功后统一 onDirty() → data.refresh()，各布局自动同步；
// - 弹窗全部复用既有组件（StrategyEditDialog / StrategyBorrowDialog /
//   BookingDialog / SlotDetailDialog / MyBookingsDrawer），本文件只负责编排。
import { reactive } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import type { CalendarDayCell, SlotTemplateItem } from "@/api/slotBooking";
import { getStrategies } from "@/api/strategy";
import {
  approveBorrowFlow,
  cancelBorrowFlow,
  rejectBorrowFlow
} from "@/api/borrowFlow";
import { releaseBooking, rescheduleBooking } from "@/api/slotBooking";
import type { StrategyItem, WeeklyStrategy } from "@/api/types";
import type { ScheduleData } from "./types";
import type { ScheduleEvent } from "./types";

export interface ScheduleActions {
  /** 各弹窗显隐与预填（由 shared/ScheduleDialogs.vue 统一渲染） */
  ui: {
    editVisible: boolean;
    editStrategy: StrategyItem | null;
    editBranches: Array<{ branch_id: number; branch_name: string }>;
    borrowVisible: boolean;
    borrowStrategy: (WeeklyStrategy & { version_name?: string }) | null;
    borrowVersionId: number | undefined;
    occupyVisible: boolean;
    occupyDate: string;
    occupyTemplate: SlotTemplateItem | null;
    occupyHorizonEnd: string;
    detailVisible: boolean;
    detailDate: string;
    detailEntry: CalendarDayCell | null;
    detailTemplate: SlotTemplateItem | null;
    /** 详情弹窗上下文：保留事件本体，供「详情 → 改期」跳转取用权限/预填 */
    detailEvent: ScheduleEvent | null;
    detailReschedulable: boolean;
    approvalVisible: boolean;
    myBookingsVisible: boolean;
    /** 抢占改期（P2-R2）：弹窗显隐与预填 */
    rescheduleVisible: boolean;
    rescheduleEvent: ScheduleEvent | null;
    rescheduleDate: string;
    rescheduleTemplateId: number | null;
    rescheduleTemplates: SlotTemplateItem[];
    rescheduleHorizonEnd: string;
  };
  openEdit(event: ScheduleEvent): Promise<void>;
  openBorrow(event: ScheduleEvent): Promise<void>;
  openOccupy(event: ScheduleEvent): void;
  openDetail(event: ScheduleEvent): void;
  /** 从抢占详情弹窗转发到改期弹窗（先关详情，避免双层遮罩叠压） */
  rescheduleFromDetail(): void;
  openApproval(): void;
  openMyBookings(): void;
  openReschedule(event: ScheduleEvent): void;
  confirmReschedule(): Promise<void>;
  release(event: ScheduleEvent): Promise<void>;
  approve(event: ScheduleEvent): Promise<void>;
  reject(event: ScheduleEvent): Promise<void>;
  cancelBorrow(event: ScheduleEvent): Promise<void>;
  batchRelease(events: ScheduleEvent[]): Promise<void>;
  copyText(event: ScheduleEvent): Promise<void>;
}

/** 由布局页调用一次，返回动作总线 */
export function useScheduleActions(data: ScheduleData): ScheduleActions {
  /** 策略详情缓存（weekly 契约不含 template_id/enabled，编辑前按需补全） */
  let strategyCache: StrategyItem[] | null = null;
  async function loadStrategyDetails(
    versionId: number | undefined
  ): Promise<StrategyItem[]> {
    if (!strategyCache) {
      strategyCache = await getStrategies({ version_id: versionId });
    }
    return strategyCache;
  }

  const ui = reactive({
    editVisible: false,
    editStrategy: null as StrategyItem | null,
    editBranches: [] as Array<{ branch_id: number; branch_name: string }>,
    borrowVisible: false,
    borrowStrategy: null as (WeeklyStrategy & { version_name?: string }) | null,
    borrowVersionId: undefined as number | undefined,
    occupyVisible: false,
    occupyDate: "",
    occupyTemplate: null as SlotTemplateItem | null,
    occupyHorizonEnd: "",
    detailVisible: false,
    detailDate: "",
    detailEntry: null as CalendarDayCell | null,
    detailTemplate: null as SlotTemplateItem | null,
    detailEvent: null as ScheduleEvent | null,
    detailReschedulable: false,
    approvalVisible: false,
    myBookingsVisible: false,
    rescheduleVisible: false,
    rescheduleEvent: null as ScheduleEvent | null,
    rescheduleDate: "",
    rescheduleTemplateId: null as number | null,
    rescheduleTemplates: [] as SlotTemplateItem[],
    rescheduleHorizonEnd: ""
  });

  async function openEdit(event: ScheduleEvent) {
    const raw = event.raw;
    if (!event.permissions.canEdit || raw.type !== "strategy") return;
    try {
      const list = await loadStrategyDetails(event.versionId ?? undefined);
      const detail = list.find(x => x.id === raw.strategyId);
      if (!detail) {
        ElMessage.warning("策略详情获取失败，请稍后重试");
        return;
      }
      ui.editStrategy = detail;
      ui.editBranches = data.branchOptions.value.map(b => ({ ...b }));
      ui.editVisible = true;
    } catch {
      // 拦截器已提示
    }
  }

  async function openBorrow(event: ScheduleEvent) {
    const raw = event.raw;
    if (!event.permissions.canBorrow || raw.type !== "strategy") return;
    ui.borrowStrategy = { ...raw.data, version_name: event.versionName };
    ui.borrowVersionId = event.versionId ?? undefined;
    ui.borrowVisible = true;
  }

  function openOccupy(event: ScheduleEvent) {
    const raw = event.raw;
    if (!event.permissions.canOccupy || raw.type !== "slot") return;
    ui.occupyDate = event.date;
    ui.occupyTemplate = raw.template;
    ui.occupyHorizonEnd = horizonEndOf();
    ui.occupyVisible = true;
  }

  function openDetail(event: ScheduleEvent) {
    const raw = event.raw;
    if (raw.type !== "slot") return;
    ui.detailDate = event.date;
    ui.detailEntry = raw.data;
    ui.detailTemplate = raw.template;
    ui.detailEvent = event;
    ui.detailReschedulable = event.permissions.canReschedule;
    ui.detailVisible = true;
  }

  /** 详情 → 改期：详情弹窗只负责转发，预填逻辑仍只实现一处（openReschedule） */
  function rescheduleFromDetail() {
    const event = ui.detailEvent;
    ui.detailVisible = false;
    if (event) openReschedule(event);
  }

  function openApproval() {
    ui.approvalVisible = true;
  }

  function openMyBookings() {
    ui.myBookingsVisible = true;
  }

  /** 打开抢占改期弹窗：预填当前日期/时段，候选时段仅启用中的 */
  function openReschedule(event: ScheduleEvent) {
    const raw = event.raw;
    if (!event.permissions.canReschedule || raw.type !== "slot") return;
    ui.rescheduleEvent = event;
    ui.rescheduleDate = event.date;
    ui.rescheduleTemplateId = raw.template.id;
    ui.rescheduleTemplates = data.templates.value.filter(t => t.enabled);
    ui.rescheduleHorizonEnd = horizonEndOf();
    ui.rescheduleVisible = true;
  }

  /** 提交改期：仅送 date/template_id，purpose 由后端沿用原值 */
  async function confirmReschedule() {
    const event = ui.rescheduleEvent;
    if (!event || event.raw.type !== "slot") return;
    const booking = event.raw.data.booking;
    if (!booking) return;
    if (!ui.rescheduleDate) {
      ElMessage.warning("请选择新的日期");
      return;
    }
    try {
      await rescheduleBooking(booking.id, {
        date: ui.rescheduleDate,
        template_id: ui.rescheduleTemplateId ?? undefined
      });
      ElMessage.success("已改期");
      ui.rescheduleVisible = false;
      await data.refresh();
    } catch {
      // 40904 目标时段被占 / 42201 越窗口或模板不适用：拦截器已提示，弹窗保留供重选
    }
  }

  /** 可抢窗口截止日（口径与 slot-booking 页一致：today + horizon_days） */
  function horizonEndOf(): string {
    const d = new Date();
    d.setDate(d.getDate() + (data.horizonDays.value || 60));
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  async function release(event: ScheduleEvent) {
    if (event.raw.type !== "slot" || !event.raw.data.booking) return;
    const { booking } = event.raw.data;
    const isOthers = !event.mine;
    let reason = "";
    try {
      if (isOthers) {
        // admin 释放他人必须填写释放原因（后端 42201 兜底）
        const { value } = await ElMessageBox.prompt(
          `确定释放 ${event.date} ${event.raw.template.start_time}-${event.raw.template.end_time}（${booking.user_name}）的抢占吗？请填写释放原因。`,
          "管理员释放他人抢占",
          {
            type: "warning",
            confirmButtonText: "确定释放",
            cancelButtonText: "取消",
            inputValidator: (v: string) =>
              v && v.trim().length > 0 ? true : "请填写释放原因"
          }
        );
        reason = String(value ?? "").trim();
      } else {
        await ElMessageBox.confirm(
          `确定释放 ${event.date} ${event.raw.template.start_time}-${event.raw.template.end_time} 的抢占吗？释放后其他成员可立即抢占该时段。`,
          "释放确认",
          {
            type: "warning",
            confirmButtonText: "确定释放",
            cancelButtonText: "取消"
          }
        );
      }
    } catch {
      return; // 用户取消
    }
    try {
      await releaseBooking(booking.id, reason);
      ElMessage.success("已释放");
      ui.detailVisible = false;
      await data.refresh();
    } catch {
      // 拦截器已提示
    }
  }

  async function approve(event: ScheduleEvent) {
    if (!event.permissions.canApprove || event.raw.type !== "borrow") return;
    const flow = event.raw.data;
    try {
      await ElMessageBox.confirm(
        `确定通过「${flow.borrower_name} 借用 ${flow.strategy_name} → ${flow.target_version_name}/${flow.target_branch_name}」的申请吗？通过后将立即在目标分支创建借用策略。`,
        "审批通过",
        { type: "warning", confirmButtonText: "通过", cancelButtonText: "取消" }
      );
    } catch {
      return;
    }
    try {
      await approveBorrowFlow(flow.id);
      ElMessage.success("已通过，借用策略已创建");
      await data.refresh();
    } catch {
      // 40901/40902 建策略冲突时电子流保持待审批（后端保证），拦截器已提示
    }
  }

  async function reject(event: ScheduleEvent) {
    if (!event.permissions.canApprove || event.raw.type !== "borrow") return;
    const flow = event.raw.data;
    let comment = "";
    try {
      const { value } = await ElMessageBox.prompt(
        `确定驳回「${flow.borrower_name} 借用 ${flow.strategy_name}」的申请吗？请填写审批意见（必填）。`,
        "审批驳回",
        {
          type: "warning",
          confirmButtonText: "驳回",
          cancelButtonText: "取消",
          inputValidator: (v: string) =>
            v && v.trim().length > 0 ? true : "请填写审批意见"
        }
      );
      comment = String(value ?? "").trim();
    } catch {
      return;
    }
    try {
      await rejectBorrowFlow(flow.id, comment);
      ElMessage.success("已驳回");
      await data.refresh();
    } catch {
      // 拦截器已提示
    }
  }

  /** 撤销借用申请（P2-R1）：仅本人 + 待审批；已处理时后端 40903 */
  async function cancelBorrow(event: ScheduleEvent) {
    if (!event.permissions.canCancel || event.raw.type !== "borrow") return;
    const flow = event.raw.data;
    try {
      await ElMessageBox.confirm(
        `确定撤销「借用 ${flow.strategy_name} → ${flow.target_version_name}/${flow.target_branch_name}」的申请吗？撤销后该申请不再出现在待审批列表。`,
        "撤销借用申请",
        {
          type: "warning",
          confirmButtonText: "确定撤销",
          cancelButtonText: "取消"
        }
      );
    } catch {
      return; // 用户取消
    }
    try {
      await cancelBorrowFlow(flow.id);
      ElMessage.success("已撤销");
      await data.refresh();
    } catch {
      // 拦截器已提示
    }
  }

  /** 批量释放：串行循环单条接口 + 逐条汇总（禁止批量端点，PRD P1-R4） */
  async function batchRelease(events: ScheduleEvent[]) {
    const releasable = events.filter(
      e => e.permissions.canRelease || e.permissions.canReleaseOthers
    );
    if (!releasable.length) {
      ElMessage.warning("所选条目中没有你可释放的抢占");
      return;
    }
    try {
      await ElMessageBox.confirm(
        `将串行释放 ${releasable.length} 条抢占记录，逐条处理并汇总结果。`,
        "批量释放确认",
        {
          type: "warning",
          confirmButtonText: "开始释放",
          cancelButtonText: "取消"
        }
      );
    } catch {
      return;
    }
    let ok = 0;
    let fail = 0;
    for (const e of releasable) {
      try {
        const booking = e.raw.type === "slot" ? e.raw.data.booking : null;
        if (!booking) {
          fail += 1;
          continue;
        }
        await releaseBooking(booking.id, "");
        ok += 1;
      } catch {
        fail += 1;
      }
    }
    ElMessage.success(`批量释放完成：成功 ${ok} 条，失败 ${fail} 条`);
    await data.refresh();
  }

  /** 复制电子流文本（仅借用事件；VNode 文本渲染，禁 dangerouslyUseHTMLString） */
  async function copyText(event: ScheduleEvent) {
    if (event.raw.type !== "borrow") return;
    const f = event.raw.data;
    const text = [
      `借用申请：${f.borrower_name} 借用「${f.strategy_name}」`,
      `来源：${f.source_version_name}/${f.source_branch_name}（${f.original_build_time}）`,
      `目标：${f.target_version_name}/${f.target_branch_name}（新构建时间 ${f.new_build_time}）`,
      `原因：${f.reason || "无"}`
    ].join("\n");
    try {
      await navigator.clipboard.writeText(text);
      ElMessage.success("已复制借用信息");
    } catch {
      ElMessage.warning("复制失败，请手动选择文本复制");
    }
  }

  return {
    ui,
    openEdit,
    openBorrow,
    openOccupy,
    openDetail,
    rescheduleFromDetail,
    openApproval,
    openMyBookings,
    openReschedule,
    confirmReschedule,
    release,
    approve,
    reject,
    cancelBorrow,
    batchRelease,
    copyText
  };
}
