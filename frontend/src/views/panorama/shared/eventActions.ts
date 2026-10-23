// 行内操作清单（S4 分组看板 / S5 时间轴流水共用）
// 权限位在归源层一次算好（ScheduleEvent.permissions），这里只做布尔映射；
// 数组顺序即展示优先级：前两个常驻行内，其余进「更多」下拉。
import type { ScheduleEvent } from "../types";
import type { ScheduleActions } from "../useScheduleActions";

export interface EventAction {
  key: string;
  label: string;
  /** 透传 el-button 语义类型；danger/warning 在下拉项里同步弱化标色 */
  type?: "primary" | "danger" | "warning";
  run: () => void | Promise<void>;
}

/** 按 permissions 派生事件操作清单（S4/S5 完全同源，避免两处各抄一遍） */
export function buildEventActions(
  e: ScheduleEvent,
  actions: ScheduleActions
): EventAction[] {
  const list: EventAction[] = [];
  if (e.permissions.canEdit)
    list.push({
      key: "edit",
      label: "修改",
      type: "primary",
      run: () => actions.openEdit(e)
    });
  if (e.permissions.canBorrow)
    list.push({
      key: "borrow",
      label: "借用",
      type: "primary",
      run: () => actions.openBorrow(e)
    });
  if (e.permissions.canOccupy)
    list.push({
      key: "occupy",
      label: "抢占",
      type: "primary",
      run: () => actions.openOccupy(e)
    });
  // canRelease（本人）与 canReleaseOthers（admin 释他人）互斥，二者任一即出
  // 「释放」项（R6-F1：此前 canReleaseOthers 算好了却无 UI 入口，admin 单条
  // 释放他人只能绕道 S4 批量模式；release() 内部已按 mine/others 分流必填原因）
  if (e.permissions.canRelease || e.permissions.canReleaseOthers)
    list.push({
      key: "release",
      label: "释放",
      type: "danger",
      run: () => actions.release(e)
    });
  if (e.permissions.canReschedule)
    list.push({
      key: "reschedule",
      label: "改期",
      type: "primary",
      run: () => actions.openReschedule(e)
    });
  if (e.permissions.canApprove) {
    list.push({
      key: "approve",
      label: "通过",
      type: "primary",
      run: () => actions.approve(e)
    });
    list.push({
      key: "reject",
      label: "驳回",
      type: "danger",
      run: () => actions.reject(e)
    });
  }
  if (e.permissions.canCancel)
    list.push({
      key: "cancel",
      label: "撤销申请",
      type: "warning",
      run: () => actions.cancelBorrow(e)
    });
  if (e.source === "slot")
    list.push({
      key: "detail",
      label: "详情",
      run: () => actions.openDetail(e)
    });
  return list;
}

/** S5 时间轴专属补充：借用事件的复制入口（S4 看板不提供） */
export function withCopyAction(
  list: EventAction[],
  e: ScheduleEvent,
  actions: ScheduleActions
): EventAction[] {
  if (e.source !== "borrow") return list;
  return [
    ...list,
    { key: "copy", label: "复制", run: () => actions.copyText(e) }
  ];
}
