// views/constants 展示映射唯一来源单测（徽标文案/颜色语义锁定）
import { describe, expect, it } from "vitest";
import {
  bookingStatusMeta,
  borrowStatusMeta,
  branchRoleMeta,
  DEFAULT_HORIZON_DAYS,
  instanceStatusMeta,
  pushModeMeta,
  reportConclusionMeta,
  reportStatusMeta,
  revisionTagType,
  roleTextMap,
  slotStatusText
} from "@/views/constants";

describe("默认可抢窗口常量（R4-F13/F-L4 唯一来源）", () => {
  it("DEFAULT_HORIZON_DAYS 为 60（与后端 RuntimeConfig 默认值一致）", () => {
    expect(DEFAULT_HORIZON_DAYS).toBe(60);
  });

  it("borrowStatusMeta 覆盖 cancelled（借用状态筛选项的文案来源）", () => {
    expect(borrowStatusMeta("cancelled")).toEqual({
      text: "已撤销",
      type: "info"
    });
  });
});

describe("报告结论/状态", () => {
  it("reportConclusionMeta 命中与兜底", () => {
    expect(reportConclusionMeta("pass")).toEqual({
      text: "通过",
      type: "success"
    });
    expect(reportConclusionMeta("fail").type).toBe("danger");
    expect(reportConclusionMeta("risk").type).toBe("warning");
    expect(reportConclusionMeta("weird")).toEqual({
      text: "weird",
      type: "info"
    });
  });

  it("reportStatusMeta 命中与兜底", () => {
    expect(reportStatusMeta("draft")).toEqual({ text: "草稿", type: "info" });
    expect(reportStatusMeta("published")).toEqual({
      text: "已发布",
      type: "success"
    });
    expect(reportStatusMeta("x")).toEqual({ text: "x", type: "info" });
  });
});

describe("借用电子流状态", () => {
  it("三态命中与兜底", () => {
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

  it("slotStatusText 只取文案，与 bookingStatusMeta.text 同源", () => {
    expect(slotStatusText("available")).toBe("空闲");
    expect(slotStatusText("reserved")).toBe("已抢占");
    expect(slotStatusText("released")).toBe("已释放");
    expect(slotStatusText("weird")).toBe("weird");
  });
});

describe("分支权限角色与实例状态", () => {
  it("branchRoleMeta 命中与兜底", () => {
    expect(branchRoleMeta("VIEWER")).toEqual({ text: "查看者", type: "info" });
    expect(branchRoleMeta("OPERATOR")).toEqual({
      text: "操作者",
      type: "primary"
    });
    expect(branchRoleMeta("ADMIN")).toEqual({
      text: "管理员",
      type: "warning"
    });
    expect(branchRoleMeta("x")).toEqual({ text: "x", type: "info" });
  });

  it("instanceStatusMeta 命中与兜底", () => {
    expect(instanceStatusMeta("STARTING").type).toBe("primary");
    expect(instanceStatusMeta("RUNNING")).toEqual({
      text: "运行中",
      type: "success"
    });
    expect(instanceStatusMeta("STOPPED").type).toBe("info");
    expect(instanceStatusMeta("ERROR")).toEqual({
      text: "异常",
      type: "danger"
    });
    expect(instanceStatusMeta("x")).toEqual({ text: "x", type: "info" });
  });
});

describe("修订动作与用户角色", () => {
  it("revisionTagType 命中与兜底", () => {
    expect(revisionTagType("create")).toBe("info");
    expect(revisionTagType("update")).toBe("warning");
    expect(revisionTagType("publish")).toBe("success");
    expect(revisionTagType("x")).toBe("info");
  });

  it("roleTextMap 覆盖后端全部 5 角色", () => {
    expect(roleTextMap).toEqual({
      admin: "管理员",
      pm: "版本负责人",
      builder: "构建人员",
      tester: "测试人员",
      integrator: "集成人员"
    });
  });
});
