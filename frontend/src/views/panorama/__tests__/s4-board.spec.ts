// S4 分组看板布局组件级测试 /panorama/board
// 重点回归：勾选只存事件 id，刷新后 events 换新对象但 id 不变 → 勾选保留；
// 条目彻底消失（翻周期后旧日期不在场）时自动剔除，不会被二次批量释放
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DOMWrapper, VueWrapper } from "@vue/test-utils";
import { flushPromises } from "@vue/test-utils";
import { ElMessage } from "element-plus";

// 只替换 ElMessageBox（确认/输入框），其余 Element Plus 组件保持真实
vi.mock("element-plus", async importOriginal => {
  const actual = await importOriginal<typeof import("element-plus")>();
  return {
    ...actual,
    ElMessageBox: {
      confirm: vi.fn().mockResolvedValue(undefined),
      prompt: vi.fn().mockResolvedValue({ value: "" })
    }
  };
});
vi.mock("@/api/weekly", () => ({ getWeekly: vi.fn() }));
vi.mock("@/api/slotBooking", () => ({
  getSlotCalendar: vi.fn(),
  releaseBooking: vi.fn()
}));
vi.mock("@/api/plan", () => ({ getPlan: vi.fn() }));
vi.mock("@/api/borrowFlow", () => ({ listBorrowFlows: vi.fn() }));
vi.mock("@/api/panorama", () => ({ getPanoramaTodos: vi.fn() }));

import { getWeekly } from "@/api/weekly";
import { getSlotCalendar, releaseBooking } from "@/api/slotBooking";
import type { CalendarDayCell } from "@/api/slotBooking";
import { getPlan } from "@/api/plan";
import { listBorrowFlows } from "@/api/borrowFlow";
import { getPanoramaTodos } from "@/api/panorama";
import PanoramaBoard from "../layouts/s4-board/index.vue";
import { mountLayout, setTestUser } from "./helpers";
import { bookingStatusMeta } from "@/views/constants";
import {
  makeBorrowFlow,
  makePlanVersions,
  makeTodos,
  makeWeekCalendar,
  makeWeeklyData
} from "./fixtures";

const weeklyMock = vi.mocked(getWeekly);
const calendarMock = vi.mocked(getSlotCalendar);
const planMock = vi.mocked(getPlan);
const borrowMock = vi.mocked(listBorrowFlows);
const todosMock = vi.mocked(getPanoramaTodos);
const releaseMock = vi.mocked(releaseBooking);

const FIXED_NOW = new Date("2026-10-13T10:00:00");

let wrapper: VueWrapper;

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  setTestUser();
  vi.useFakeTimers({
    now: FIXED_NOW,
    toFake: ["setTimeout", "clearTimeout", "Date"]
  });
  weeklyMock.mockResolvedValue(makeWeeklyData());
  // 首屏（挂载刷新）返回含本人抢占；之后的拉取返回已释放状态
  calendarMock
    .mockResolvedValueOnce(makeWeekCalendar())
    .mockResolvedValue(makeWeekCalendar({ reservedDate: null }));
  planMock.mockResolvedValue(makePlanVersions());
  borrowMock.mockResolvedValue([makeBorrowFlow()]);
  todosMock.mockResolvedValue(makeTodos());
  releaseMock.mockResolvedValue(undefined);
});

afterEach(() => {
  wrapper?.unmount();
  vi.useRealTimers();
});

/** 批量工具条文本（已选 N 项） */
function batchBarText(): string {
  return wrapper.find(".batch-bar").text();
}

/** 批量模式开关 */
async function toggleBatchMode(text: "批量模式" | "退出批量") {
  await wrapper
    .findAll("button")
    .find(b => b.text() === text)!
    .trigger("click");
}

/** 本人抢占行（副标题含「我的抢占」，全表唯一） */
function mySlotRow() {
  return wrapper.findAll(".row").find(r => r.text().includes("我的抢占"))!;
}

/**
 * 按月过滤的日历夹具：getSlotCalendar 入参为月份字符串（YYYY-MM），
 * 仅返回该月内的日期格。用于「翻周期后旧日期条目消失」——翻跨月份后
 * 原日期的抢占彻底离场（生产按请求月份聚合，本测试用同一口径）。
 */
function monthCalendar(month: string) {
  const base = makeWeekCalendar();
  const days: Record<string, CalendarDayCell[]> = {};
  for (const [d, cells] of Object.entries(base.days)) {
    if (d.startsWith(month)) days[d] = cells;
  }
  return { ...base, month, days };
}

/**
 * 勾选某行。
 * 真实 EP 复选框的内部 input 需 setChecked 触发 change，jsdom 下对
 * .el-checkbox 根节点 trigger("click") 不会冒泡到 input，勾选恒不成立。
 */
async function checkRow(row: DOMWrapper<Element>) {
  // 真实 EP 复选框的内部 input 需 setValue 触发 change（jsdom 下对 .el-checkbox
  // 根节点 trigger click 不冒泡）；setValue 在 checkbox 上内部即调用 setChecked
  await row.find(".el-checkbox input").setValue(true);
  await flushPromises();
}

describe("S4 分组看板", () => {
  it("按版本分组渲染，策略/时段/借用同入口可操作", async () => {
    // R7-F4 回避规则后同一借用行不再同时具备审批+撤销入口：
    // 他人单（李四）走「通过/驳回」，本人单（id=7）走「撤销申请」，双流各测一路
    borrowMock.mockResolvedValue([
      makeBorrowFlow({ borrower_id: 999 }), // 他人单：走审批路径
      makeBorrowFlow({ id: 501, borrower_id: 7, borrower_name: "本人" }) // 本人单：走撤销路径
    ]);
    ({ wrapper } = await mountLayout(PanoramaBoard, "/panorama/board"));
    // 版本分组：未关联版本（策略 + 空闲时段）/ v3.2（本人抢占）/ v4.0（借用）
    // 卡片标题为「组名 + 计数 el-tag」，断言改用前缀匹配避免被计数干扰
    const titles = wrapper
      .findAll(".group-card .biz-card-title")
      .map(t => t.text());
    expect(titles.some(t => t.startsWith("未关联版本"))).toBe(true);
    expect(titles.some(t => t.startsWith("v3.2"))).toBe(true);
    expect(titles.some(t => t.startsWith("v4.0"))).toBe(true);
    // 操作按钮按 permissions 渲染：他人借用有「通过/驳回」，抢占有「释放」；
    // 本人 reserved 带「改期」(canReschedule) —— 均在前两个，常驻行内
    const boardText = wrapper.text();
    expect(boardText).toContain("通过");
    expect(boardText).toContain("驳回");
    expect(boardText).toContain("释放");
    expect(boardText).toContain("改期");
    // 他人借用行：通过/驳回常驻行内，无撤销入口（回避规则 R5-B10/R7-F4）
    const otherBorrowRow = wrapper
      .findAll(".row")
      .find(r => r.text().includes("李四 借用"))!;
    expect(otherBorrowRow.text()).not.toContain("撤销申请");
    // 本人借用带「撤销申请」(canCancel)：回避规则下无审批入口，撤销申请
    // 常驻行内（S4 看板行内操作不含复制，与 S5 时间轴口径不同）
    const mineBorrowRow = wrapper
      .findAll(".row")
      .find(r => r.text().includes("本人 借用"))!;
    expect(mineBorrowRow.text()).not.toContain("通过");
    expect(mineBorrowRow.findAll("button").map(b => b.text())).toEqual([
      "撤销申请"
    ]);
  });

  it("批量模式：勾选后计数正确，退出批量清空勾选", async () => {
    ({ wrapper } = await mountLayout(PanoramaBoard, "/panorama/board"));
    expect(wrapper.find(".batch-bar").exists()).toBe(false);
    await toggleBatchMode("批量模式");
    expect(batchBarText()).toContain("已选 0 项");
    await checkRow(mySlotRow());
    expect(batchBarText()).toContain("已选 1 项");
    await toggleBatchMode("退出批量");
    expect(wrapper.find(".batch-bar").exists()).toBe(false);
  });

  it("批量释放走串行单条接口并汇总，刷新后不可对已释放条目二次释放", async () => {
    const successSpy = vi.spyOn(ElMessage, "success");
    const warningSpy = vi.spyOn(ElMessage, "warning");
    ({ wrapper } = await mountLayout(PanoramaBoard, "/panorama/board"));
    await toggleBatchMode("批量模式");
    await checkRow(mySlotRow());

    // 强制释放后的整表刷新返回「已释放」日历：同 id 行变为空闲可抢
    calendarMock.mockReset();
    calendarMock.mockResolvedValue(makeWeekCalendar({ reservedDate: null }));

    await wrapper
      .findAll("button")
      .find(b => b.text() === "批量释放")!
      .trigger("click");
    // 整表刷新（data.refresh）是异步的：批量释放走 ElMessageBox.confirm →
    // releaseBooking → data.refresh 多段 await，trigger 只 flush 一拍。
    // 必须显式 flushPromises（多次，确保 getWeekly/getSlotCalendar/listBorrowFlows
    // 等一连串 microtask 全部 settle，events 写回后再断言行内容
    for (let i = 0; i < 3; i++) await flushPromises();
    // 串行单条释放（禁止批量端点，PRD P1-R4）+ 汇总提示 + 整表刷新
    expect(releaseMock).toHaveBeenCalledTimes(1);
    expect(releaseMock).toHaveBeenCalledWith(100, "");
    expect(successSpy).toHaveBeenCalledWith(
      "批量释放完成：成功 1 条，失败 0 条"
    );
    // 首屏 2 次（版本回填）+ 释放后整表刷新 1 次
    expect(weeklyMock).toHaveBeenCalledTimes(3);

    // 下一轮拉取该时段已释放：同 id 行变为空闲可抢
    const row = wrapper
      .findAll(".row")
      .find(
        r => r.text().includes("2026-10-13") && r.text().includes("早间窗口")
      )!;
    expect(row.text()).toContain("空闲可抢占");
    // 空闲时段不可释放 → 再次批量释放被 releasable 过滤挡住，不会重试已释放项
    await wrapper
      .findAll("button")
      .find(b => b.text() === "批量释放")!
      .trigger("click");
    for (let i = 0; i < 3; i++) await flushPromises();
    expect(warningSpy).toHaveBeenCalledWith("所选条目中没有你可释放的抢占");
    expect(releaseMock).toHaveBeenCalledTimes(1);
  });

  it("R6-F6：批量释放在途时按钮 loading 且入口短路，串行期间不得开出第二批", async () => {
    let resolveFn!: (v: unknown) => void;
    releaseMock.mockReturnValue(
      new Promise(r => {
        resolveFn = r;
      }) as never
    );
    ({ wrapper } = await mountLayout(PanoramaBoard, "/panorama/board"));
    await toggleBatchMode("批量模式");
    await checkRow(mySlotRow());

    const batchBtn = () =>
      wrapper.findAll("button").find(b => b.text() === "批量释放")!
        .element as HTMLButtonElement;
    batchBtn().dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await flushPromises();
    // confirm/prompt 桩直接通过，进入串行释放：第一条在途 → 按钮 loading
    expect(batchBtn().classList.contains("is-loading")).toBe(true);

    // 在途期间再次点击：入口短路，不开第二批（仍只有 1 次请求）
    batchBtn().dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await flushPromises();
    expect(releaseMock).toHaveBeenCalledTimes(1);

    resolveFn(undefined);
    await flushPromises();
    for (let i = 0; i < 2; i++) await flushPromises();
    expect(batchBtn().classList.contains("is-loading")).toBe(false);
    expect(releaseMock).toHaveBeenCalledTimes(1);
  });

  it("翻周期后旧日期条目消失，勾选自动剔除", async () => {
    // 日历夹具按月返回：翻跨月份后原日期的抢占彻底离场
    calendarMock.mockImplementation(async (month: string) =>
      monthCalendar(month)
    );
    ({ wrapper } = await mountLayout(PanoramaBoard, "/panorama/board"));
    await toggleBatchMode("批量模式");
    await checkRow(mySlotRow());
    expect(batchBarText()).toContain("已选 1 项");
    // 连翻 3 个周期跨入 11 月：10-13 抢占随日历月份过滤彻底离场
    for (let i = 0; i < 3; i++) {
      await wrapper
        .findAll("button")
        .find(b => b.attributes("aria-label") === "下一周期")!
        .trigger("click");
      await flushPromises();
    }
    // 勾选应随条目离场自动剔除：翻到 11 月后原 10-13 抢占已不在 events 中
    expect(batchBarText()).toContain("已选 0 项");
    // 待审批借用是全局收件箱（hub 按「与我相关」过滤，不受日期范围影响），
    // 仍可能锚在 10-13，故不能断言「全表无 2026-10-13」。真正应消失的是被勾选的
    // 那条本人抢占时段（副标题「我的抢占」）——断言其已离场即可
    expect(
      wrapper.findAll(".row").some(r => r.text().includes("我的抢占"))
    ).toBe(false);
  });

  it("R7-F6：按状态分组组名为 statusText 文案而非英文枚举", async () => {
    ({ wrapper } = await mountLayout(PanoramaBoard, "/panorama/board"));
    // 工具条第一个 el-select 即分组维度（FilterBar 的版本下拉在其后），
    // jsdom 下拉交互不稳定，直接发 update:modelValue
    await wrapper
      .findComponent({ name: "ElSelect" })
      .vm.$emit("update:modelValue", "status");
    await flushPromises();
    const titles = wrapper.findAll(".biz-card-title").map(t => t.text());
    // 本人抢占 reserved → 「已抢占」；借用 pending → 「待审批」
    expect(titles.join("|")).toContain(bookingStatusMeta("reserved").text);
    expect(titles.join("|")).not.toMatch(/reserved|pending/);
  });

  it("刷新按钮保留仍存在的勾选（按 id 而非对象引用）", async () => {
    ({ wrapper } = await mountLayout(PanoramaBoard, "/panorama/board"));
    await toggleBatchMode("批量模式");
    await checkRow(mySlotRow());
    // 把后续拉取切回持续含抢占：刷新后 events 换新对象但 id 不变
    calendarMock.mockResolvedValue(makeWeekCalendar());
    await wrapper
      .findAll("button")
      .find(b => b.text() === "刷新")!
      .trigger("click");
    // 刷新是多段异步拉取：加载期间分组区让位给骨架、行短暂卸载，
    // 必须显式 flush 等整表写回后再断言行内容（不能对着旧 DOM 断言）
    for (let i = 0; i < 3; i++) await flushPromises();
    // 首屏 2 次（版本回填）+ 手动刷新 1 次
    expect(weeklyMock).toHaveBeenCalledTimes(3);
    expect(batchBarText()).toContain("已选 1 项");
    expect(mySlotRow().find(".el-checkbox").classes()).toContain("is-checked");
  });

  it("分组折叠态在数据刷新后保持（R5-F5：折叠态外置按 key 记录）", async () => {
    ({ wrapper } = await mountLayout(PanoramaBoard, "/panorama/board"));
    const findV4Card = () =>
      wrapper
        .findAll(".group-card")
        .find(c => c.find(".biz-card-title").text().startsWith("v4.0"))!;
    // 初始展开：行可见，按钮为「收起」
    expect(findV4Card().findAll(".row").length).toBeGreaterThan(0);
    expect(
      findV4Card().find(".row-list").attributes("style") ?? ""
    ).not.toContain("display: none");
    await findV4Card()
      .findAll("button")
      .find(b => b.text() === "收起")!
      .trigger("click");
    // v-show 折叠（jsdom 无布局引擎，isVisible 不可靠，断言内联样式）
    expect(findV4Card().find(".row-list").attributes("style")).toContain(
      "display: none"
    );
    // 整表刷新：events 换新对象、groups computed 重建——
    // 修复前折叠态挂在 computed 输出上（collapsed:false 内联），刷新即全部弹开
    calendarMock.mockResolvedValue(makeWeekCalendar());
    await wrapper
      .findAll("button")
      .find(b => b.text() === "刷新")!
      .trigger("click");
    for (let i = 0; i < 3; i++) await flushPromises();
    expect(findV4Card().find(".row-list").attributes("style")).toContain(
      "display: none"
    );
    expect(
      findV4Card()
        .findAll("button")
        .some(b => b.text() === "展开")
    ).toBe(true);
  });
});
