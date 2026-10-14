// 调度全景动作总线单测（R4-F1/F2/F5/F11）：
// - 策略详情缓存按版本键控 + invalidateStrategyCache 失效（weekly 页同款范式）
// - 批量释放含「他人抢占」时收集统一原因（后端非 owner 释放必填），汇总按成败分级
// - 复制走 utils/clipboard 封装 + borrow-flow/format 文案唯一来源
// - 改期提交在途守卫（双击仅一次 PATCH）
// 测试纪律：mock 全部业务 API 与 element-plus 弹层，不引入网络与真实后端。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";

// 弹层与提示全部换成 hoisted 替身：断言直接打在替身上，绕开 EP 严格返回类型
const { messageSuccess, messageWarning, confirmMock, promptMock } = vi.hoisted(
  () => ({
    messageSuccess: vi.fn(),
    messageWarning: vi.fn(),
    confirmMock: vi.fn(),
    promptMock: vi.fn()
  })
);

vi.mock("element-plus", () => ({
  ElMessage: {
    success: messageSuccess,
    warning: messageWarning,
    info: vi.fn(),
    error: vi.fn()
  },
  ElMessageBox: { confirm: confirmMock, prompt: promptMock, alert: vi.fn() }
}));
vi.mock("@/api/strategy", () => ({ getStrategies: vi.fn() }));
vi.mock("@/api/slotBooking", () => ({
  releaseBooking: vi.fn(),
  rescheduleBooking: vi.fn()
}));
vi.mock("@/api/borrowFlow", () => ({
  approveBorrowFlow: vi.fn(),
  cancelBorrowFlow: vi.fn(),
  rejectBorrowFlow: vi.fn()
}));
vi.mock("@/utils/clipboard", () => ({ copyText: vi.fn() }));

import { getStrategies } from "@/api/strategy";
import { releaseBooking, rescheduleBooking } from "@/api/slotBooking";
import type { BookingItem } from "@/api/slotBooking";
import type { StrategyItem } from "@/api/types";
import { copyText as clipboardCopy } from "@/utils/clipboard";
import { formatBorrowFlowText } from "@/views/borrow-flow/format";
import { useScheduleActions } from "../useScheduleActions";
import type { ScheduleData, ScheduleEvent } from "../types";
import {
  FULL_PERMISSIONS,
  makeBooking,
  makeBorrowFlow,
  makeCell,
  makeEvent,
  makeStrategy,
  makeTemplate
} from "./fixtures";

const strategiesMock = vi.mocked(getStrategies);
const releaseMock = vi.mocked(releaseBooking);
const rescheduleMock = vi.mocked(rescheduleBooking);
const clipboardMock = vi.mocked(clipboardCopy);

/** 策略详情（/strategies 契约）：weekly 骨架缺失的 template_id/enabled 在此补全 */
function makeStrategyItem(over: Partial<StrategyItem> = {}): StrategyItem {
  return {
    id: 1,
    branch_id: 10,
    branch_name: "main",
    version_id: 1,
    template_id: 7,
    template_name: "标准模板",
    name: "主链路策略",
    build_start_time: "08:00",
    push_mode: "normal",
    push_start_time: null,
    enabled: true,
    ...over
  };
}

/** 最小可用的数据中枢替身：动作总线只消费这几个字段 */
function makeFakeData(): ScheduleData {
  return {
    loading: ref(false),
    lastLoadedAt: ref<Date | null>(null),
    days: ref([]),
    events: ref<ScheduleEvent[]>([]),
    byDay: computed(() => ({})),
    agenda: computed(() => []),
    kpi: computed(() => ({
      todayBuild: 0,
      weekSlotOccupied: 0,
      weekSlotTotal: 0,
      pendingBorrow: 0,
      mySlots: 0,
      conflictCount: 0,
      occupancyRate: 0
    })),
    versionOptions: computed(() => []),
    branchOptions: computed(() => [{ branch_id: 10, branch_name: "main" }]),
    templates: computed(() => [makeTemplate()]),
    horizonDays: ref(60),
    todos: ref(null),
    slotTruncated: ref(false),
    refresh: vi.fn(async () => true)
  };
}

/** 可编辑的策略事件（openEdit 入口条件：canEdit + raw.type=strategy） */
function makeStrategyEvent(
  versionId: number,
  strategyId: number
): ScheduleEvent {
  return makeEvent({
    id: `strategy:${strategyId}#2026-10-13#build`,
    versionId,
    permissions: { ...FULL_PERMISSIONS, canEdit: true },
    raw: {
      type: "strategy",
      data: makeStrategy({ strategy_id: strategyId }),
      strategyId
    }
  });
}

/** 抢占事件（批量释放消费）：默认本人 reserved */
function makeSlotEvent(
  bookingId: number,
  opts: { mine?: boolean; canReleaseOthers?: boolean } = {}
): ScheduleEvent {
  const mine = opts.mine ?? true;
  const booking = makeBooking({ id: bookingId, is_mine: mine });
  return makeEvent({
    id: `slot:2026-10-13:${bookingId}`,
    source: "slot",
    kind: "slot",
    date: "2026-10-13",
    mine,
    permissions: {
      ...FULL_PERMISSIONS,
      canEdit: false,
      canBorrow: false,
      canOccupy: false,
      canRelease: mine,
      canReleaseOthers: opts.canReleaseOthers ?? false,
      canApprove: false,
      canCancel: false,
      canReschedule: false
    },
    raw: {
      type: "slot",
      data: {
        ...makeCell({ status: "reserved", booking }),
        date: "2026-10-13"
      },
      template: makeTemplate()
    }
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  confirmMock.mockResolvedValue(undefined);
  releaseMock.mockResolvedValue(makeBooking());
  rescheduleMock.mockResolvedValue(makeBooking());
  clipboardMock.mockResolvedValue(true);
});

describe("R4-F1 策略详情缓存：版本键控 + 显式失效", () => {
  it("同版本二次打开复用缓存；invalidateStrategyCache 后重拉预填新值", async () => {
    strategiesMock.mockResolvedValue([makeStrategyItem({ name: "旧名称" })]);
    const data = makeFakeData();
    const actions = useScheduleActions(data);
    const event = makeStrategyEvent(1, 1);

    await actions.openEdit(event);
    expect(strategiesMock).toHaveBeenCalledTimes(1);
    expect(strategiesMock).toHaveBeenCalledWith({ version_id: 1 });
    expect(actions.ui.editVisible).toBe(true);
    expect(actions.ui.editStrategy?.name).toBe("旧名称");

    // 模拟保存后服务端已是新值：缓存未失效时二次打开仍预填旧值
    strategiesMock.mockResolvedValue([makeStrategyItem({ name: "新名称" })]);
    actions.ui.editVisible = false;
    await actions.openEdit(event);
    expect(strategiesMock).toHaveBeenCalledTimes(1);
    expect(actions.ui.editStrategy?.name).toBe("旧名称");

    // onSaved 路径：先失效缓存再刷新 → 重开弹窗预填新值
    actions.invalidateStrategyCache();
    actions.ui.editVisible = false;
    await actions.openEdit(event);
    expect(strategiesMock).toHaveBeenCalledTimes(2);
    expect(actions.ui.editStrategy?.name).toBe("新名称");
  });

  it("切版本后按键控自动重拉，不再误报「策略详情获取失败」", async () => {
    // 版本 1 的详情列表不含策略 5（旧实现的无键控缓存会 find 不中而误报）
    strategiesMock.mockResolvedValue([makeStrategyItem({ id: 1 })]);
    const data = makeFakeData();
    const actions = useScheduleActions(data);
    await actions.openEdit(makeStrategyEvent(1, 1));
    expect(actions.ui.editVisible).toBe(true);

    actions.ui.editVisible = false;
    strategiesMock.mockResolvedValue([
      makeStrategyItem({ id: 5, version_id: 2, name: "27B 策略" })
    ]);
    await actions.openEdit(makeStrategyEvent(2, 5));
    expect(strategiesMock).toHaveBeenCalledTimes(2);
    expect(strategiesMock).toHaveBeenLastCalledWith({ version_id: 2 });
    expect(actions.ui.editVisible).toBe(true);
    expect(actions.ui.editStrategy?.name).toBe("27B 策略");
    expect(messageWarning).not.toHaveBeenCalled();
  });

  it("详情列表缺失该策略时提示失败且不打开弹窗", async () => {
    strategiesMock.mockResolvedValue([]);
    const actions = useScheduleActions(makeFakeData());
    await actions.openEdit(makeStrategyEvent(1, 1));
    expect(messageWarning).toHaveBeenCalledWith("策略详情获取失败，请稍后重试");
    expect(actions.ui.editVisible).toBe(false);
  });
});

describe("R4-F2 批量释放：他人条目收集统一原因", () => {
  it("全部为本人条目：不弹原因输入框，reason 传空串，汇总走 success", async () => {
    const data = makeFakeData();
    const actions = useScheduleActions(data);
    await actions.batchRelease([makeSlotEvent(100), makeSlotEvent(101)]);
    expect(confirmMock).toHaveBeenCalledTimes(1);
    expect(promptMock).not.toHaveBeenCalled();
    expect(releaseMock).toHaveBeenCalledTimes(2);
    expect(releaseMock).toHaveBeenCalledWith(100, "");
    expect(releaseMock).toHaveBeenCalledWith(101, "");
    expect(messageSuccess).toHaveBeenCalledWith(
      "批量释放完成：成功 2 条，失败 0 条"
    );
    expect(data.refresh).toHaveBeenCalled();
  });

  it("含他人条目：prompt 收集统一原因（trim 后）透传 releaseBooking，本人条目仍传空串", async () => {
    promptMock.mockResolvedValue({ value: "  窗口让行  " });
    const data = makeFakeData();
    const actions = useScheduleActions(data);
    await actions.batchRelease([
      makeSlotEvent(100),
      makeSlotEvent(200, { mine: false, canReleaseOthers: true })
    ]);
    expect(promptMock).toHaveBeenCalledTimes(1);
    // inputValidator 必填口径：空串被拒
    const opts = promptMock.mock.calls[0][2] as {
      inputValidator: (v: string) => true | string;
    };
    expect(opts.inputValidator("")).toBe("请填写释放原因");
    expect(opts.inputValidator(" x ")).toBe(true);
    expect(releaseMock).toHaveBeenCalledWith(100, "");
    expect(releaseMock).toHaveBeenCalledWith(200, "窗口让行");
    expect(messageSuccess).toHaveBeenCalledWith(
      "批量释放完成：成功 2 条，失败 0 条"
    );
  });

  it("取消原因输入框：整批中止，不做部分释放", async () => {
    promptMock.mockRejectedValue(new Error("cancel"));
    const data = makeFakeData();
    const actions = useScheduleActions(data);
    await actions.batchRelease([
      makeSlotEvent(100),
      makeSlotEvent(200, { mine: false, canReleaseOthers: true })
    ]);
    expect(releaseMock).not.toHaveBeenCalled();
    expect(data.refresh).not.toHaveBeenCalled();
  });

  it("全部失败：汇总走 warning 而非 success", async () => {
    releaseMock.mockRejectedValue(new Error("40904"));
    const data = makeFakeData();
    const actions = useScheduleActions(data);
    await actions.batchRelease([makeSlotEvent(100), makeSlotEvent(101)]);
    expect(messageWarning).toHaveBeenCalledWith(
      "批量释放完成：成功 0 条，失败 2 条"
    );
    expect(messageSuccess).not.toHaveBeenCalled();
    expect(data.refresh).toHaveBeenCalled();
  });

  it("部分失败：汇总同样走 warning（存在失败即不报纯成功）", async () => {
    releaseMock
      .mockResolvedValueOnce(makeBooking())
      .mockRejectedValueOnce(new Error("40904"));
    const data = makeFakeData();
    const actions = useScheduleActions(data);
    await actions.batchRelease([makeSlotEvent(100), makeSlotEvent(101)]);
    expect(messageWarning).toHaveBeenCalledWith(
      "批量释放完成：成功 1 条，失败 1 条"
    );
    expect(messageSuccess).not.toHaveBeenCalled();
  });
});

describe("R4-F11 改期提交在途守卫", () => {
  /** 打开改期弹窗（openReschedule 入口条件：canReschedule + raw slot + booking） */
  function openDialog(actions: ReturnType<typeof useScheduleActions>) {
    const event = makeEvent({
      id: "slot:2026-10-13:100",
      source: "slot",
      kind: "slot",
      date: "2026-10-13",
      mine: true,
      permissions: { ...FULL_PERMISSIONS, canReschedule: true },
      raw: {
        type: "slot",
        data: {
          ...makeCell({
            status: "reserved",
            booking: makeBooking({ id: 100 })
          }),
          date: "2026-10-13"
        },
        template: makeTemplate()
      }
    });
    actions.openReschedule(event);
    return event;
  }

  it("双击「确定改期」仅发一次 PATCH；在途态外化到 ui.rescheduling", async () => {
    let resolvePatch!: (v: BookingItem) => void;
    rescheduleMock.mockImplementation(
      () =>
        new Promise<BookingItem>(r => {
          resolvePatch = r;
        })
    );
    const data = makeFakeData();
    const actions = useScheduleActions(data);
    openDialog(actions);
    expect(actions.ui.rescheduleVisible).toBe(true);

    const first = actions.confirmReschedule();
    const second = actions.confirmReschedule();
    expect(rescheduleMock).toHaveBeenCalledTimes(1);
    expect(rescheduleMock).toHaveBeenCalledWith(100, {
      date: "2026-10-13",
      template_id: 1
    });
    expect(actions.ui.rescheduling).toBe(true);

    resolvePatch(makeBooking());
    await Promise.all([first, second]);
    expect(actions.ui.rescheduling).toBe(false);
    expect(actions.ui.rescheduleVisible).toBe(false);
    expect(messageSuccess).toHaveBeenCalledWith("已改期");
    expect(data.refresh).toHaveBeenCalled();
  });

  it("PATCH 失败（40904）：弹窗保留供重选，loading 复位", async () => {
    rescheduleMock.mockRejectedValue(new Error("40904"));
    const data = makeFakeData();
    const actions = useScheduleActions(data);
    openDialog(actions);
    await actions.confirmReschedule();
    expect(actions.ui.rescheduleVisible).toBe(true);
    expect(actions.ui.rescheduling).toBe(false);
    expect(messageSuccess).not.toHaveBeenCalled();
  });

  it("未选新日期：提示且不发请求", async () => {
    const data = makeFakeData();
    const actions = useScheduleActions(data);
    openDialog(actions);
    actions.ui.rescheduleDate = "";
    await actions.confirmReschedule();
    expect(messageWarning).toHaveBeenCalledWith("请选择新的日期");
    expect(rescheduleMock).not.toHaveBeenCalled();
    expect(actions.ui.rescheduling).toBe(false);
  });
});

describe("R4-F5 复制借用文案：clipboard 封装 + format.ts 唯一来源", () => {
  /** 借用事件（copyText 只处理 raw.type=borrow） */
  function borrowEvent() {
    const flow = makeBorrowFlow();
    return {
      flow,
      event: makeEvent({
        id: `borrow:${flow.id}`,
        source: "borrow",
        kind: "borrow",
        raw: { type: "borrow", data: flow }
      })
    };
  }

  it("文案取 formatBorrowFlowText 唯一实现；复制成功提示", async () => {
    const data = makeFakeData();
    const actions = useScheduleActions(data);
    const { flow, event } = borrowEvent();
    await actions.copyText(event);
    expect(clipboardMock).toHaveBeenCalledTimes(1);
    expect(clipboardMock).toHaveBeenCalledWith(formatBorrowFlowText(flow));
    // 文案含审批页同款要素（不再手写副本）
    expect(clipboardMock.mock.calls[0][0]).toContain("【借用电子流】#500");
    expect(messageSuccess).toHaveBeenCalledWith("已复制借用信息");
    expect(messageWarning).not.toHaveBeenCalled();
  });

  it("剪贴板被拦截（降级仍失败）：warning 提示且不抛异常", async () => {
    clipboardMock.mockResolvedValue(false);
    const actions = useScheduleActions(makeFakeData());
    const { event } = borrowEvent();
    await actions.copyText(event);
    expect(messageWarning).toHaveBeenCalledWith("复制失败，请手动选择文本复制");
    expect(messageSuccess).not.toHaveBeenCalled();
  });

  it("非借用事件直接忽略（不触剪贴板）", async () => {
    const actions = useScheduleActions(makeFakeData());
    await actions.copyText(makeSlotEvent(100));
    expect(clipboardMock).not.toHaveBeenCalled();
  });
});
