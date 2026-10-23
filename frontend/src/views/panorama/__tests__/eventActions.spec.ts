// eventActions 纯函数单测（R4-F10/F-M8：panorama 域此前唯一无 spec 的纯函数模块）
// 锁定：权限位 → 操作清单的映射、数组顺序即展示优先级（前两个常驻行内，
// 其余进「更多」下拉）、run 接线、withCopyAction 仅对借用事件追加「复制」。
import { describe, expect, it, vi } from "vitest";
import { buildEventActions, withCopyAction } from "../shared/eventActions";
import type { ScheduleActions } from "../useScheduleActions";
import type { ScheduleEvent, SchedulePermissions } from "../types";
import { FULL_PERMISSIONS, makeBorrowFlow, makeEvent } from "./fixtures";

/** 全关权限包（用例按需打开单个位） */
const NO_PERMISSIONS: SchedulePermissions = {
  canEdit: false,
  canBorrow: false,
  canOccupy: false,
  canRelease: false,
  canReleaseOthers: false,
  canApprove: false,
  canCancel: false,
  canReschedule: false
};

/** 动作总线替身：只记录调用，不触发真实弹窗/接口 */
function makeFakeActions() {
  const fns = {
    openEdit: vi.fn(),
    openBorrow: vi.fn(),
    openOccupy: vi.fn(),
    openDetail: vi.fn(),
    rescheduleFromDetail: vi.fn(),
    openApproval: vi.fn(),
    openMyBookings: vi.fn(),
    openReschedule: vi.fn(),
    confirmReschedule: vi.fn(),
    release: vi.fn(),
    approve: vi.fn(),
    reject: vi.fn(),
    cancelBorrow: vi.fn(),
    batchRelease: vi.fn(),
    copyText: vi.fn(),
    invalidateStrategyCache: vi.fn()
  };
  return { fns, actions: fns as unknown as ScheduleActions };
}

function eventWith(
  permissions: Partial<SchedulePermissions>,
  over: Partial<ScheduleEvent> = {}
): ScheduleEvent {
  return makeEvent({
    permissions: { ...NO_PERMISSIONS, ...permissions },
    ...over
  });
}

/** key 序列（顺序即展示优先级） */
function keysOf(list: Array<{ key: string }>): string[] {
  return list.map(a => a.key);
}

describe("buildEventActions 权限位 → 操作清单", () => {
  it("策略事件 + 全关权限 → 空清单（策略来源不常驻「详情」）", () => {
    const { actions } = makeFakeActions();
    expect(buildEventActions(eventWith({}), actions)).toEqual([]);
  });

  it("时段事件无权限位也常驻「详情」（slot 专属兜底入口）", () => {
    const { actions } = makeFakeActions();
    const list = buildEventActions(
      eventWith({}, { source: "slot", kind: "slot" }),
      actions
    );
    expect(keysOf(list)).toEqual(["detail"]);
    expect(list[0].label).toBe("详情");
    expect(list[0].type).toBeUndefined();
  });

  it("借用事件：审批位给出 通过+驳回（顺序固定），撤销位追加在后", () => {
    const { actions } = makeFakeActions();
    const borrow = { source: "borrow" as const, kind: "borrow" as const };
    expect(
      keysOf(
        buildEventActions(eventWith({ canApprove: true }, borrow), actions)
      )
    ).toEqual(["approve", "reject"]);
    expect(
      keysOf(
        buildEventActions(
          eventWith({ canApprove: true, canCancel: true }, borrow),
          actions
        )
      )
    ).toEqual(["approve", "reject", "cancel"]);
  });

  it("全开权限（策略）：顺序即优先级 edit→borrow→occupy→release→reschedule→approve→reject→cancel", () => {
    const { actions } = makeFakeActions();
    const list = buildEventActions(eventWith({ ...FULL_PERMISSIONS }), actions);
    expect(keysOf(list)).toEqual([
      "edit",
      "borrow",
      "occupy",
      "release",
      "reschedule",
      "approve",
      "reject",
      "cancel"
    ]);
  });

  it("全开权限（时段）：「详情」恒排末位", () => {
    const { actions } = makeFakeActions();
    const list = buildEventActions(
      eventWith({ ...FULL_PERMISSIONS }, { source: "slot", kind: "slot" }),
      actions
    );
    expect(keysOf(list).at(-1)).toBe("detail");
  });

  it("文案与语义色：修改/借用/抢占/改期 primary、释放/驳回 danger、撤销 warning", () => {
    const { actions } = makeFakeActions();
    const list = buildEventActions(eventWith({ ...FULL_PERMISSIONS }), actions);
    const byKey = Object.fromEntries(list.map(a => [a.key, a]));
    expect(byKey.edit).toMatchObject({ label: "修改", type: "primary" });
    expect(byKey.borrow).toMatchObject({ label: "借用", type: "primary" });
    expect(byKey.occupy).toMatchObject({ label: "抢占", type: "primary" });
    expect(byKey.release).toMatchObject({ label: "释放", type: "danger" });
    expect(byKey.reschedule).toMatchObject({ label: "改期", type: "primary" });
    expect(byKey.approve).toMatchObject({ label: "通过", type: "primary" });
    expect(byKey.reject).toMatchObject({ label: "驳回", type: "danger" });
    expect(byKey.cancel).toMatchObject({ label: "撤销申请", type: "warning" });
  });

  it("run 接线：每个操作调用总线对应方法且透传事件本体", async () => {
    const { fns, actions } = makeFakeActions();
    const event = eventWith(
      { ...FULL_PERMISSIONS },
      { source: "slot", kind: "slot" }
    );
    const list = buildEventActions(event, actions);
    const byKey = Object.fromEntries(list.map(a => [a.key, a]));
    await byKey.edit.run();
    await byKey.borrow.run();
    await byKey.occupy.run();
    await byKey.release.run();
    await byKey.reschedule.run();
    await byKey.approve.run();
    await byKey.reject.run();
    await byKey.cancel.run();
    await byKey.detail.run();
    expect(fns.openEdit).toHaveBeenCalledWith(event);
    expect(fns.openBorrow).toHaveBeenCalledWith(event);
    expect(fns.openOccupy).toHaveBeenCalledWith(event);
    expect(fns.release).toHaveBeenCalledWith(event);
    expect(fns.openReschedule).toHaveBeenCalledWith(event);
    expect(fns.approve).toHaveBeenCalledWith(event);
    expect(fns.reject).toHaveBeenCalledWith(event);
    expect(fns.cancelBorrow).toHaveBeenCalledWith(event);
    expect(fns.openDetail).toHaveBeenCalledWith(event);
  });

  it("R6-F1：admin 释他人位（canReleaseOthers）给出「释放」入口并接线 release", async () => {
    const { fns, actions } = makeFakeActions();
    const event = eventWith(
      { canReleaseOthers: true },
      { source: "slot", kind: "slot", mine: false }
    );
    const list = buildEventActions(event, actions);
    // slot 事件兜底「详情」恒在末位；释放项排在其前
    expect(keysOf(list)).toEqual(["release", "detail"]);
    expect(list[0]).toMatchObject({ label: "释放", type: "danger" });
    await list[0].run();
    expect(fns.release).toHaveBeenCalledWith(event);
  });

  it("canRelease 与 canReleaseOthers 互斥：全开权限也不产生重复「释放」项", () => {
    const { actions } = makeFakeActions();
    const list = buildEventActions(
      eventWith(
        { canRelease: true, canReleaseOthers: true },
        { source: "slot", kind: "slot" }
      ),
      actions
    );
    expect(keysOf(list).filter(k => k === "release")).toHaveLength(1);
  });
});

describe("withCopyAction（S5 时间轴专属补充）", () => {
  it("借用事件：末位追加「复制」，run 调 copyText", async () => {
    const { fns, actions } = makeFakeActions();
    const event = eventWith(
      { canApprove: true },
      {
        source: "borrow",
        kind: "borrow",
        raw: { type: "borrow", data: makeBorrowFlow() }
      }
    );
    const base = buildEventActions(event, actions);
    const list = withCopyAction(base, event, actions);
    expect(keysOf(list)).toEqual(["approve", "reject", "copy"]);
    expect(list.at(-1)!.label).toBe("复制");
    await list.at(-1)!.run();
    expect(fns.copyText).toHaveBeenCalledWith(event);
  });

  it("非借用事件：原样返回不追加", () => {
    const { actions } = makeFakeActions();
    const strategy = eventWith({ canEdit: true });
    const base = buildEventActions(strategy, actions);
    expect(withCopyAction(base, strategy, actions)).toBe(base);
    const slot = eventWith({}, { source: "slot", kind: "slot" });
    const slotBase = buildEventActions(slot, actions);
    expect(withCopyAction(slotBase, slot, actions)).toBe(slotBase);
  });
});
