// borrowFormat 单测：复制文案组装（纯函数，无网络；mock 掉真实 http 依赖链避免拉起 router）
import { describe, expect, it, vi } from "vitest";

vi.mock("@/api/http", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

import type { BorrowFlowItem } from "@/api/borrowFlow";
import {
  formatBorrowFlowText,
  formatFlowTime
} from "@/views/panorama/shared/borrowFormat";
import { formatTime } from "@/utils/business";

function makeFlow(overrides: Partial<BorrowFlowItem> = {}): BorrowFlowItem {
  return {
    id: 7,
    strategy_id: 3,
    strategy_name: "27A-TR5-晚间全量",
    source_version_id: 1,
    source_version_name: "27A",
    source_branch_id: 3,
    source_branch_name: "TR5",
    template_name: "晚间全量冒烟",
    original_build_time: "21:00",
    borrower_id: 5,
    borrower_name: "26B负责人",
    target_version_id: 3,
    target_version_name: "26B",
    target_branch_id: 8,
    target_branch_name: "TR5",
    new_build_time: "22:00",
    reason: "26B 晚间需要复用该时段",
    status: "pending",
    approver_name: null,
    handle_comment: "",
    handled_at: null,
    cancelled_at: null,
    created_at: "2026-10-11T16:30:00",
    ...overrides
  };
}

describe("formatBorrowFlowText 借用电子流复制文案", () => {
  it("待审批流程包含核心要素且不带审批行", () => {
    const text = formatBorrowFlowText(makeFlow());
    expect(text).toContain("【借用电子流】#7 待审批");
    expect(text).toContain("策略：27A-TR5-晚间全量（27A/TR5 · 晚间全量冒烟）");
    expect(text).toContain("原构建时间：21:00");
    expect(text).toContain("借用人：26B负责人");
    expect(text).toContain("借用至：26B/TR5，新构建时间 22:00");
    expect(text).toContain("借用原因：26B 晚间需要复用该时段");
    expect(text).toContain("申请时间：2026-10-11 16:30:00");
    expect(text).not.toContain("审批：");
  });

  it("已处理流程追加审批人与意见行", () => {
    const text = formatBorrowFlowText(
      makeFlow({
        status: "rejected",
        approver_name: "27A负责人",
        handle_comment: "时段已被占用",
        handled_at: "2026-10-11T17:00:00"
      })
    );
    expect(text).toContain("【借用电子流】#7 已驳回");
    expect(text).toContain(
      "审批：27A负责人 驳回（时段已被占用） 2026-10-11 17:00:00"
    );
  });

  it("未填写原因时显示占位", () => {
    const text = formatBorrowFlowText(makeFlow({ reason: "" }));
    expect(text).toContain("借用原因：（未填写）");
  });

  it("传入 detailUrl 时附带可直达的审批链接行", () => {
    const text = formatBorrowFlowText(
      makeFlow(),
      "http://localhost:8848/#/borrow-flow/index?focus=7"
    );
    expect(text).toContain(
      "审批详情链接：http://localhost:8848/#/borrow-flow/index?focus=7"
    );
  });

  it("不传 detailUrl 时不含链接行", () => {
    const text = formatBorrowFlowText(makeFlow());
    expect(text).not.toContain("审批详情链接");
  });

  it("已通过流程：审批行用「通过」文案（第三轮补 approved 分支）", () => {
    const text = formatBorrowFlowText(
      makeFlow({
        status: "approved",
        approver_name: "27A负责人",
        handle_comment: "同意借用",
        handled_at: "2026-10-11T18:30:00"
      })
    );
    expect(text).toContain("【借用电子流】#7 已通过");
    expect(text).toContain(
      "审批：27A负责人 通过（同意借用） 2026-10-11 18:30:00"
    );
  });

  it("approver_name 为 null 时审批人兜底为 -", () => {
    const text = formatBorrowFlowText(
      makeFlow({
        status: "approved",
        approver_name: null,
        handle_comment: "ok",
        handled_at: "2026-10-11T18:30:00"
      })
    );
    expect(text).toContain("审批：- 通过（ok） 2026-10-11 18:30:00");
  });

  it("handle_comment 为空时不拼括号", () => {
    const text = formatBorrowFlowText(
      makeFlow({
        status: "approved",
        approver_name: "27A负责人",
        handle_comment: "",
        handled_at: "2026-10-11T18:30:00"
      })
    );
    expect(text).toContain("审批：27A负责人 通过 2026-10-11 18:30:00");
    expect(text).not.toContain("通过（");
  });

  it("handled_at 为 null 时时间位保持空串不抛异常", () => {
    const text = formatBorrowFlowText(
      makeFlow({
        status: "rejected",
        approver_name: "27A负责人",
        handle_comment: "时段冲突",
        handled_at: null
      })
    );
    expect(text).toContain("审批：27A负责人 驳回（时段冲突） ");
    expect(text).not.toContain("Invalid Date");
  });

  it("已撤销流程：撤销行拼借用人撤销时刻，不拼审批人/意见（R5-F2 三态分支）", () => {
    const text = formatBorrowFlowText(
      makeFlow({
        status: "cancelled",
        approver_name: null,
        handle_comment: "",
        handled_at: null,
        cancelled_at: "2026-10-11T17:20:00"
      })
    );
    expect(text).toContain("【借用电子流】#7 已撤销");
    expect(text).toContain("撤销：借用人撤销于 2026-10-11 17:20:00");
    expect(text).not.toContain("审批：");
  });

  it("已撤销流程：cancelled_at 为 null 时时间位保持空串不抛异常", () => {
    const text = formatBorrowFlowText(
      makeFlow({ status: "cancelled", cancelled_at: null })
    );
    expect(text).toContain("撤销：借用人撤销于 ");
    expect(text).not.toContain("Invalid Date");
    expect(text).not.toContain("审批：");
  });
});

describe("formatFlowTime 电子流时间格式化（替代手写 replace，输出逐字节等价）", () => {
  it("合法时间串：T 分隔转空格，保留秒", () => {
    expect(formatFlowTime("2026-10-11T16:30:00")).toBe("2026-10-11 16:30:00");
  });

  it("空值（null/undefined/空串）保持空串，不输出 Invalid Date", () => {
    expect(formatFlowTime(null)).toBe("");
    expect(formatFlowTime(undefined)).toBe("");
    expect(formatFlowTime("")).toBe("");
  });

  it("R4-F7 等价性锁定：与 utils/business.formatTime 秒级格式逐字节一致（统一前置验证）", () => {
    for (const v of [
      "2026-10-11T16:30:00",
      "2026-10-11 16:30:00",
      "2026-01-01T00:00:00",
      "2026-12-31T23:59:59"
    ]) {
      expect(formatFlowTime(v)).toBe(formatTime(v, "YYYY-MM-DD HH:mm:ss"));
    }
  });
});
