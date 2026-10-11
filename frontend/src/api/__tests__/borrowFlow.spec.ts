// borrowFlow API 单测：复制文案组装（纯函数，无网络；mock 掉真实 http 依赖链避免拉起 router）
import { describe, expect, it, vi } from "vitest";

vi.mock("@/api/http", () => ({ default: { get: vi.fn(), post: vi.fn() } }));

import { formatBorrowFlowText, type BorrowFlowItem } from "@/api/borrowFlow";

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
});
