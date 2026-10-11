// views/constants 展示映射唯一来源单测（徽标文案/颜色语义锁定）
import { describe, expect, it } from "vitest";
import {
  borrowStatusMeta,
  branchRoleMeta,
  instanceStatusMeta,
  reportConclusionMeta,
  reportStatusMeta,
  revisionTagType,
  roleTextMap
} from "@/views/constants";

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
