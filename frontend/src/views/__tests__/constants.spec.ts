// views/constants 展示映射唯一来源单测（徽标文案/颜色语义锁定）
// 2026-10-20 页面精简：报告/分支权限/实例/修订/角色标签映射随页面下线删除，
// 本文件仅锁定全景域 + 策略配置页在用的借用状态、推送模式、抢占状态映射。
import { describe, expect, it } from "vitest";
import {
  bookingStatusMeta,
  borrowStatusMeta,
  DEFAULT_HORIZON_DAYS,
  pushModeMeta
} from "@/views/constants";

describe("默认可抢窗口常量（R4-F13/F-L4 唯一来源）", () => {
  it("DEFAULT_HORIZON_DAYS 为 60（与后端 RuntimeConfig 默认值一致）", () => {
    expect(DEFAULT_HORIZON_DAYS).toBe(60);
  });
});

describe("借用电子流状态", () => {
  it("四态命中与兜底", () => {
    expect(borrowStatusMeta("pending")).toEqual({
      text: "待审批",
      type: "warning"
    });
    expect(borrowStatusMeta("approved")).toEqual({
      text: "已通过",
      type: "success"
    });
    expect(borrowStatusMeta("rejected")).toEqual({
      text: "已驳回",
      type: "danger"
    });
    expect(borrowStatusMeta("cancelled")).toEqual({
      text: "已撤销",
      type: "info"
    });
    expect(borrowStatusMeta("x")).toEqual({ text: "x", type: "info" });
  });
});

describe("策略推送模式与抢占状态（第三轮收敛的展示映射）", () => {
  it("pushModeMeta 命中：normal/sync 各含短文案与长文案两套 label", () => {
    expect(pushModeMeta("normal")).toEqual({
      label: "正常流程",
      fullLabel: "正常流程推送"
    });
    expect(pushModeMeta("sync")).toEqual({
      label: "同步推送",
      fullLabel: "同步推送冒烟"
    });
  });

  it("pushModeMeta 未知值原样兜底、空值返回空文案", () => {
    expect(pushModeMeta("weird")).toEqual({
      label: "weird",
      fullLabel: "weird"
    });
    expect(pushModeMeta(undefined)).toEqual({ label: "", fullLabel: "" });
    expect(pushModeMeta(null)).toEqual({ label: "", fullLabel: "" });
    expect(pushModeMeta("")).toEqual({ label: "", fullLabel: "" });
  });

  it("bookingStatusMeta 覆盖日历格 available + 抢占 reserved/released（无 expired 分支）", () => {
    expect(bookingStatusMeta("available")).toEqual({
      text: "空闲",
      type: "info"
    });
    expect(bookingStatusMeta("reserved")).toEqual({
      text: "已抢占",
      type: "success"
    });
    expect(bookingStatusMeta("released")).toEqual({
      text: "已释放",
      type: "info"
    });
    expect(bookingStatusMeta("x")).toEqual({ text: "x", type: "info" });
  });
});
